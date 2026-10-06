from __future__ import annotations

from contextlib import asynccontextmanager

from northstar.cases import CaseStore
from northstar.clock import Clock, SystemClock
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
from pydantic import BaseModel, Field
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=500)


class QuestionBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


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
    cases = CaseStore(pool, clock, settings.request_limit, settings.daily_token_budget)
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
        if length is not None and int(length) > 16_384:
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

    @app.get("/cases/current")
    def current_case(staff=Depends(staff_from_token)) -> dict:
        return cases.current(staff.id)

    @app.post("/cases/current/messages")
    def ask_case(body: QuestionBody, staff=Depends(staff_from_token)) -> dict:
        return cases.ask(staff.id, body.question)

    return app


app = create_app()
