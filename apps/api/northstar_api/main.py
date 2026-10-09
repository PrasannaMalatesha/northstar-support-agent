from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Literal

from northstar.cases import (
    AlreadyPickedUp,
    AmountNotEditable,
    AmountOutOfBounds,
    CaseClosed,
    CaseStore,
    NoOffer,
    NotInInbox,
    NotYours,
    ProposerCannotApprove,
    ProposalNotWaiting,
    ProposalWaiting,
)
from northstar.clock import Clock, SystemClock
from northstar.photo import BadPhoto, checked
from northstar.identity.postgres import PostgresIdentityStore
from northstar.identity.seed import seed_staff
from northstar.identity.service import (
    Identity,
    LoginInvalid,
    LoginLocked,
    TokenInvalid,
)
from northstar_api.settings import Settings
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)
_WAITING = "A proposal on this live chat is waiting for a lead."


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=500)


class SsoBody(BaseModel):
    id_token: str = Field(min_length=20, max_length=8000)


class ChatStartBody(BaseModel):
    order_id: str = Field(min_length=3, max_length=20)
    email: str = Field(min_length=3, max_length=320)


class QuestionBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Optional damaged-item photo as a data URL (issue #80). Checked again in northstar.photo.
    photo: str | None = Field(default=None, max_length=6_000_000)


class BindBody(BaseModel):
    query: str = Field(min_length=3, max_length=200)


class CloseBody(BaseModel):
    final_text: str = Field(min_length=1, max_length=4000)


class EditAmountBody(BaseModel):
    amount_cents: int = Field(ge=0, le=10_000_000)


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReplyBody(BaseModel):
    # A reply of only spaces is empty, so the customer never sees a blank message.
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)


class AvailabilityBody(BaseModel):
    state: Literal["available", "away"]


class EscalateLiveBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    note: str = Field(min_length=1, max_length=2000)


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    pool: ConnectionPool | None = None,
) -> FastAPI:
    settings = settings or Settings()
    clock = clock or SystemClock()
    owns_pool = pool is None
    if pool is None:
        pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    store = PostgresIdentityStore(pool)
    store.ensure_schema()
    seed_staff(store)
    identity = Identity(store, clock, settings.token_secret)
    cases = CaseStore(
        pool,
        clock,
        settings.request_limit,
        settings.daily_token_budget,
        chat_turns_per_customer=settings.chat_turns_per_customer,
        chat_turns_per_day=settings.chat_turns_per_day,
        turn_seconds=settings.turn_deadline_seconds,
        failed_turns_before_offer=settings.failed_turns_before_offer,
        live_chats=settings.live_agents_enabled,
    )
    cases.ensure_schema()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owns_pool:
            pool.close()

    app = FastAPI(title="Northstar Support API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.console_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def limit_body(request, call_next):
        length = request.headers.get("content-length")
        # A message may carry a photo of up to 4 MB, about 5.6 MB as base64 (issue #80). Everything else stays small.
        limit = 6_000_000 if request.url.path == "/cases/current/messages" else 16_384
        if length is not None and int(length) > limit:
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Request is too large."}, status_code=413)
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/login")
    def login(body: LoginBody) -> dict:
        try:
            pair = identity.login(body.email, body.password)
        except LoginLocked as exc:
            raise HTTPException(
                status_code=423,
                detail="This login is locked. Try again later.",
            ) from exc
        except LoginInvalid as exc:
            raise HTTPException(
                status_code=401,
                detail="Email or password is incorrect.",
            ) from exc
        return {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "token_type": "bearer",
            "expires_in": pair.expires_in,
            "name": pair.name,
            "role": pair.role,
        }

    @app.post("/auth/refresh")
    def refresh(body: RefreshBody) -> dict:
        try:
            pair = identity.refresh(body.refresh_token)
        except TokenInvalid as exc:
            raise HTTPException(status_code=401, detail="Refresh token is not valid.") from exc
        return {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "token_type": "bearer",
            "expires_in": pair.expires_in,
            "name": pair.name,
            "role": pair.role,
        }

    @app.post("/auth/sso")
    def sso_login(body: SsoBody) -> dict:
        if not settings.google_client_id:
            raise HTTPException(status_code=404, detail="Single sign-on is off.")
        try:
            pair = identity.sso_login(body.id_token, settings.google_client_id)
        except LoginInvalid as exc:
            raise HTTPException(status_code=401, detail="This Google account cannot sign in here.") from exc
        return {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "expires_in": pair.expires_in,
            "name": pair.name,
            "role": pair.role,
        }

    @app.post("/auth/logout")
    def logout(body: RefreshBody) -> dict[str, str]:
        try:
            identity.logout(body.refresh_token)
        except TokenInvalid as exc:
            raise HTTPException(status_code=401, detail="Refresh token is not valid.") from exc
        return {"status": "logged_out"}

    @app.get("/me")
    def me(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> dict[str, str]:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        try:
            staff = identity.current_staff(credentials.credentials)
        except TokenInvalid as exc:
            raise HTTPException(status_code=401, detail="Sign in required.") from exc
        return {"name": staff.name, "role": staff.role}

    def staff_from_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ):
        if credentials is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        try:
            return identity.current_staff(credentials.credentials)
        except TokenInvalid as exc:
            raise HTTPException(status_code=401, detail="Sign in required.") from exc

    # Customer chat (issue #79). A chat token only reaches the customer's own chat, never staff routes.

    @app.post("/chat/start")
    def start_chat(body: ChatStartBody) -> dict:
        try:
            return {"chat_token": identity.start_chat(body.email, body.order_id, cases.chat_customer)}
        except LoginLocked as exc:
            raise HTTPException(status_code=423, detail="Too many tries. Try again later.") from exc
        except LoginInvalid as exc:
            # One message for every miss, so the chat does not reveal which orders or emails exist.
            raise HTTPException(status_code=401, detail="That order and email do not match.") from exc

    def customer_from_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
        if credentials is None:
            raise HTTPException(status_code=401, detail="Start the chat first.")
        try:
            return identity.chat_customer(credentials.credentials)
        except TokenInvalid as exc:
            raise HTTPException(status_code=401, detail="Start the chat first.") from exc

    @app.get("/chat")
    def chat(customer_id=Depends(customer_from_token)) -> dict:
        return cases.chat(customer_id)

    @app.post("/chat/messages")
    def chat_message(body: QuestionBody, customer_id=Depends(customer_from_token)) -> dict:
        if body.photo:
            raise HTTPException(status_code=422, detail="Photos are not taken in the chat.")
        try:
            return cases.chat_ask(customer_id, body.question)
        except CaseClosed as exc:
            raise HTTPException(status_code=409, detail="A person on our team is reviewing your request.") from exc

    @app.get("/chat/state")
    def chat_state(customer_id=Depends(customer_from_token)) -> dict:
        # What the chat offers beside the agent (R35), and the customer's live chat request (issue #138).
        live = cases.live_state(customer_id) if settings.live_agents_enabled else None
        return {"offer": cases.chat_offer(customer_id), "live_enabled": settings.live_agents_enabled, "live": live}

    @app.post("/chat/leave-message")
    def leave_message(body: ReplyBody, customer_id=Depends(customer_from_token)) -> dict:
        try:
            return cases.leave_message(customer_id, body.text)
        except NoOffer as exc:
            raise HTTPException(status_code=409, detail="Leaving a message is offered after replies that did not help.") from exc

    @app.post("/cases/current/new")
    def new_case(staff=Depends(staff_from_token)) -> dict:
        return cases.start_new(staff.id)

    @app.get("/cases/current")
    def current_case(staff=Depends(staff_from_token)) -> dict:
        return cases.current(staff.id)

    @app.post("/cases/current/messages")
    def ask_case(body: QuestionBody, staff=Depends(staff_from_token)) -> dict:
        if body.photo:
            try:
                checked(body.photo)
            except BadPhoto as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return cases.ask(staff.id, body.question, body.photo)
        except CaseClosed as exc:
            raise HTTPException(status_code=409, detail="This case is closed.") from exc

    @app.post("/cases/current/resolve")
    def resolve_case(body: CloseBody, staff=Depends(staff_from_token)) -> dict:
        try:
            return cases.close(staff.id, "Resolved", body.final_text)
        except CaseClosed as exc:
            raise HTTPException(status_code=409, detail="This case is closed.") from exc

    @app.post("/cases/current/escalate")
    def escalate_case(body: CloseBody, staff=Depends(staff_from_token)) -> dict:
        try:
            return cases.close(staff.id, "Escalated", body.final_text)
        except CaseClosed as exc:
            raise HTTPException(status_code=409, detail="This case is closed.") from exc

    def require_lead(staff=Depends(staff_from_token)):
        if staff.role != "lead":
            raise HTTPException(status_code=403, detail="A lead decides this.")
        return staff

    @app.get("/approvals")
    def waiting_approvals(staff=Depends(require_lead)) -> list:
        return cases.pending()

    @app.get("/gaps")
    def handbook_gaps(staff=Depends(require_lead)) -> list:
        return cases.gaps()

    @app.get("/cases/{case_id}")
    def read_case(case_id: str, staff=Depends(require_lead)) -> dict:
        try:
            found = cases.read(uuid.UUID(case_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="No such case.") from exc
        if found is None:
            raise HTTPException(status_code=404, detail="No such case.")
        return found

    @app.post("/approvals/{case_id}/approve")
    def approve_proposal(case_id: str, staff=Depends(require_lead)) -> dict:
        try:
            ticket_id = cases.approve(staff.id, uuid.UUID(case_id))
        except ProposerCannotApprove as exc:
            raise HTTPException(status_code=403, detail="You proposed this refund.") from exc
        except ProposalNotWaiting as exc:
            raise HTTPException(status_code=404, detail="This case is not waiting.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="This case is not waiting.") from exc
        identity.audit(staff.id, "approve", clock.now())
        return {"ticket_id": ticket_id}

    @app.post("/approvals/{case_id}/edit")
    def edit_proposal(case_id: str, body: EditAmountBody, staff=Depends(require_lead)) -> dict:
        try:
            ticket_id, amount = cases.edit_amount(staff.id, uuid.UUID(case_id), body.amount_cents)
        except ProposerCannotApprove as exc:
            raise HTTPException(status_code=403, detail="You proposed this refund.") from exc
        except ProposalNotWaiting as exc:
            raise HTTPException(status_code=404, detail="This case is not waiting.") from exc
        except AmountOutOfBounds as exc:
            raise HTTPException(status_code=422, detail="That amount is above the order.") from exc
        except AmountNotEditable as exc:
            raise HTTPException(status_code=422, detail="This action has no amount to edit.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="This case is not waiting.") from exc
        identity.audit(staff.id, "edit", clock.now())
        return {"ticket_id": ticket_id, "amount_cents": amount}

    @app.post("/approvals/{case_id}/reject")
    def reject_proposal(case_id: str, body: RejectBody, staff=Depends(require_lead)) -> dict:
        try:
            cases.reject(staff.id, uuid.UUID(case_id), body.reason)
        except ProposerCannotApprove as exc:
            raise HTTPException(status_code=403, detail="You proposed this refund.") from exc
        except ProposalNotWaiting as exc:
            raise HTTPException(status_code=404, detail="This case is not waiting.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="This case is not waiting.") from exc
        identity.audit(staff.id, "reject", clock.now())
        return {"ticket_id": None}

    # Escalations inbox (R38). Leads see every item. Specialists pick items up and reply into the chat.

    @app.get("/inbox")
    def escalations_inbox(staff=Depends(staff_from_token)) -> list:
        return cases.inbox(staff.id, lead=staff.role == "lead")

    def require_specialist(staff=Depends(staff_from_token)):
        # Leads approve. Specialists talk to customers.
        if staff.role != "specialist":
            raise HTTPException(status_code=403, detail="Specialists talk to customers. Leads approve.")
        return staff

    @app.post("/inbox/{case_id}/pick-up")
    def pick_up_escalation(case_id: str, staff=Depends(require_specialist)) -> dict:
        try:
            cases.pick_up(staff.id, uuid.UUID(case_id))
        except AlreadyPickedUp as exc:
            raise HTTPException(status_code=409, detail="Another specialist picked this up.") from exc
        except (NotInInbox, ValueError) as exc:
            raise HTTPException(status_code=404, detail="This case is not in the inbox.") from exc
        identity.audit(staff.id, "escalation_pick_up", clock.now())
        return {"case_id": case_id}

    @app.post("/inbox/{case_id}/reply")
    def reply_to_escalation(case_id: str, body: ReplyBody, staff=Depends(require_specialist)) -> dict:
        try:
            cases.reply(staff.id, uuid.UUID(case_id), body.text)
        except (NotYours, ValueError) as exc:
            raise HTTPException(status_code=403, detail="Pick up this chat case before replying.") from exc
        identity.audit(staff.id, "escalation_reply", clock.now())
        return {"case_id": case_id}

    # Live chat (issue #138). With the setting off, no live chat route exists.

    if settings.live_agents_enabled:

        @app.post("/chat/live")
        def request_live_chat(customer_id=Depends(customer_from_token)) -> dict:
            try:
                cases.request_live(customer_id)
            except CaseClosed as exc:
                raise HTTPException(status_code=409, detail="A person on our team is reviewing your request.") from exc
            return {"live": cases.live_state(customer_id)}

        @app.post("/chat/renew")
        def renew_chat(customer_id=Depends(customer_from_token)) -> dict:
            # The chat is not signed out while the customer waits for or talks to a specialist (R47).
            if cases.live_state(customer_id) is None:
                raise HTTPException(status_code=409, detail="No live chat is open.")
            return {"chat_token": identity.chat_token(customer_id)}

        @app.post("/presence")
        def set_presence(body: AvailabilityBody, staff=Depends(require_specialist)) -> dict:
            cases.set_availability(staff.id, body.state)
            return {"state": body.state}

        @app.get("/live")
        def my_live_chats(staff=Depends(require_specialist)) -> dict:
            return cases.live(staff.id)

        @app.post("/live/{request_id}/accept")
        def accept_live_chat(request_id: uuid.UUID, staff=Depends(require_specialist)) -> dict:
            try:
                cases.accept(staff.id, request_id)
            except NotYours as exc:
                raise HTTPException(status_code=403, detail="This offer is not yours.") from exc
            return {"id": str(request_id)}

        @app.post("/live/{request_id}/messages")
        def post_live_message(request_id: uuid.UUID, body: ReplyBody, staff=Depends(require_specialist)) -> dict:
            try:
                cases.live_message(staff.id, request_id, body.text)
            except NotYours as exc:
                raise HTTPException(status_code=403, detail="This live chat is not yours.") from exc
            return {"id": str(request_id)}

        @app.post("/live/{request_id}/actions")
        def raise_live_action(request_id: uuid.UUID, body: ReplyBody, staff=Depends(require_specialist)) -> dict:
            # The same turn and rules as the agent, as the specialist. A lead approves what it proposes (R45).
            try:
                cases.live_action(staff.id, request_id, body.text)
            except NotYours as exc:
                raise HTTPException(status_code=403, detail="This live chat is not yours.") from exc
            except CaseClosed as exc:
                raise HTTPException(status_code=409, detail=_WAITING) from exc
            return {"id": str(request_id)}

        @app.post("/live/{request_id}/resolve")
        def resolve_live_chat(request_id: uuid.UUID, staff=Depends(require_specialist)) -> dict:
            try:
                cases.end_live(staff.id, request_id, "Resolved")
            except NotYours as exc:
                raise HTTPException(status_code=403, detail="This live chat is not yours.") from exc
            except ProposalWaiting as exc:
                raise HTTPException(status_code=409, detail=_WAITING) from exc
            return {"id": str(request_id)}

        @app.post("/live/{request_id}/escalate")
        def escalate_live_chat(request_id: uuid.UUID, body: EscalateLiveBody, staff=Depends(require_specialist)) -> dict:
            try:
                cases.end_live(staff.id, request_id, "Escalated", body.note)
            except NotYours as exc:
                raise HTTPException(status_code=403, detail="This live chat is not yours.") from exc
            except ProposalWaiting as exc:
                raise HTTPException(status_code=409, detail=_WAITING) from exc
            return {"id": str(request_id)}

    @app.post("/cases/current/customer")
    def bind_customer(body: BindBody, staff=Depends(staff_from_token)) -> dict:
        try:
            return cases.bind(staff.id, body.query)
        except CaseClosed as exc:
            raise HTTPException(status_code=409, detail="This case is closed.") from exc

    return app


app = create_app()
