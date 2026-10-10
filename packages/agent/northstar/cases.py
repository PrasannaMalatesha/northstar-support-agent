"""One open case per specialist, with the handbook draft stored on it.

ponytail: the assistant row is the trace (decision plus section ids).
Send the same fields to LangSmith when LANGSMITH_API_KEY is set.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta

from psycopg import sql

from northstar.actions import FAMILIES, PROPOSALS, Order, Proposal, Reply, family_decisions, gated, order_id as _order_id
from northstar.clock import Clock
from northstar.escalate import asks_for_person, handoff, left_message, manual_handoff
from northstar.graph import TurnTools, resume_turn, run_turn
from northstar.identity.seed import CHAT_STAFF_EMAIL
from northstar.identity.service import staff_id_for
from northstar.language import is_spanish, to_english, to_spanish
from northstar.memory import graph_for
from northstar.photo import describe
from northstar.agent_model import handbook_reply, turn_deadline
from northstar.handbook import ABSTAIN_TEXT, Draft, guard_draft
from northstar import defaults, online
from northstar.online import NO_HANDOVER, record_edit, record_judge
from northstar.preferences import recall, remember, stated
from northstar.retrieve import retrieved_answer
from northstar.privacy import SECRET_REPLY, has_secret, screen

# ponytail: 1_000 tokens stands in for one handbook draft. Replace with the
# model's reported usage when a model is called.
TOKENS_PER_TURN = 1_000
REQUEST_LIMIT_TEXT = (
    "This account has hit the request limit. The case is still here. Try again later."
)
QUOTA_TEXT = "The daily quota is reached. This case is still here."
COME_BACK_TEXT = "Come back to this chat with the same order id and email to read the reply."
LINE_REFUSED_TEXT = "No specialist can join soon. Leave a message, and a specialist will reply in this chat."
OFFERED_TEXT = "You are next in line. A specialist is about to join the chat."
# The wait is shown as a range around the estimate (R40).
WAIT_RANGE = (0.7, 1.5)
STILL_THERE_TEXT = "Are you still there?"
# The last word in a live chat (issue #142): the customer's message, or the specialist's message or
# action turn, which carry the specialist's id. Agent turns do not count. A lateral subquery on request r.
_LAST_WORD = """
    SELECT staff_id, created_at FROM case_messages
    WHERE case_id = r.case_id AND (role = 'user' OR staff_id IS NOT NULL)
    ORDER BY id DESC
    LIMIT 1
"""
# The request statuses that take one of the specialist's slots. An idle live chat does not (R44).
_TAKES_A_SLOT = "('offered', 'active')"
# Turns that did not help the customer. Enough of them in a row and the chat offers a person (R35).
FAILED_DECISIONS = ("ask_clarification", "abstain", "lookup_failed")
# The customer asked for a person in their own words (R39). The chat offers one, and the customer decides.
PERSON_REQUESTED = "person_requested"
PERSON_TEXT = "A specialist can reply in this chat. Leave a message for them below."
PERSON_TEXT_LIVE = "A specialist can join this chat. Choose Talk to a person below."
UNBOUND_ORDER_TEXT = "Pick a customer first. No order was read."
SAFE_REPLY = (
    "I can't continue with that message. "
    "If there is an order question, a specialist can take it from here."
)
_BLOCKED = (
    "ignore the handbook",
    "ignore the manual",
    "ignore the instructions",
    "ignore your instructions",
    "ignore previous",
    "ignore these rules",
    "retard",
    # Spanish, checked on the customer's own words before translation (issue #81).
    "ignora el manual",
    "ignora las reglas",
    "ignora las instrucciones",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    email text NOT NULL UNIQUE,
    phone text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS cases (
    id uuid PRIMARY KEY,
    staff_id uuid NOT NULL REFERENCES staff_users (id),
    customer_id uuid REFERENCES customers (id),
    created_at timestamptz NOT NULL
);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS customer_id uuid REFERENCES customers (id);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'Open';
ALTER TABLE cases ADD COLUMN IF NOT EXISTS draft_text text NOT NULL DEFAULT '';
ALTER TABLE cases ADD COLUMN IF NOT EXISTS final_text text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS orders (
    id text PRIMARY KEY,
    customer_id uuid NOT NULL REFERENCES customers (id),
    status text NOT NULL,
    purchased_on date NOT NULL,
    lines text NOT NULL,
    refunds text NOT NULL
);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_cents integer;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_on date;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipped_on date;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_action text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_amount_cents integer;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_citations text[] NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS tickets (
    id uuid PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES cases (id)
);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposed_by uuid REFERENCES staff_users (id);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_order_id text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposed_at timestamptz;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS rejection_reason text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS amount_cents integer;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_id uuid;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_details text NOT NULL DEFAULT '';
ALTER TABLE cases ADD COLUMN IF NOT EXISTS handoff_text text NOT NULL DEFAULT '';
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposed_amount_cents integer;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS proposal_id uuid;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS action text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS order_id text;
UPDATE tickets SET action = cases.proposal_action, order_id = cases.proposal_order_id
FROM cases WHERE tickets.case_id = cases.id AND tickets.order_id IS NULL;
DROP INDEX IF EXISTS tickets_one_per_case;
CREATE UNIQUE INDEX IF NOT EXISTS tickets_one_per_proposal ON tickets (proposal_id);
CREATE TABLE IF NOT EXISTS catalog_items (
    name text PRIMARY KEY,
    category text NOT NULL,
    price_cents integer NOT NULL,
    sizes text NOT NULL,
    in_stock boolean NOT NULL,
    final_sale boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS case_messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES cases (id),
    role text NOT NULL,
    body text NOT NULL,
    decision text,
    citations text[] NOT NULL DEFAULT '{}',
    strengths text[] NOT NULL DEFAULT '{}',
    steps text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL
);
ALTER TABLE case_messages ADD COLUMN IF NOT EXISTS strengths text[] NOT NULL DEFAULT '{}';
ALTER TABLE case_messages ADD COLUMN IF NOT EXISTS steps text[] NOT NULL DEFAULT '{}';
ALTER TABLE case_messages ADD COLUMN IF NOT EXISTS run_id text;
ALTER TABLE case_messages ADD COLUMN IF NOT EXISTS retrieved_sections text[] NOT NULL DEFAULT '{}';
ALTER TABLE case_messages ADD COLUMN IF NOT EXISTS retrieved_scores real[] NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS usage_days (
    staff_id uuid NOT NULL REFERENCES staff_users (id),
    day date NOT NULL,
    tokens integer NOT NULL,
    PRIMARY KEY (staff_id, day)
);
-- Requests and tokens per limit key and day (issue #134). It replaces usage_days and the
-- in-memory counter, so limits survive a restart and hold across server processes.
CREATE TABLE IF NOT EXISTS daily_limits (
    limit_key text NOT NULL,
    day date NOT NULL,
    requests integer NOT NULL DEFAULT 0,
    tokens integer NOT NULL DEFAULT 0,
    PRIMARY KEY (limit_key, day)
);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS assigned_to uuid REFERENCES staff_users (id);
ALTER TABLE case_messages ADD COLUMN IF NOT EXISTS staff_id uuid REFERENCES staff_users (id);
-- Live chat (issue #138, ADR 0001). The line is rows in live_chat_requests. A specialist is
-- available or away, and holds at most `capacity` offered and active live chats.
CREATE TABLE IF NOT EXISTS specialist_availability (
    staff_id uuid PRIMARY KEY REFERENCES staff_users (id),
    state text NOT NULL,
    capacity integer NOT NULL DEFAULT 2,
    last_seen timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS live_chat_requests (
    id uuid PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES cases (id),
    customer_id uuid NOT NULL REFERENCES customers (id),
    reason text NOT NULL,
    status text NOT NULL,
    staff_id uuid REFERENCES staff_users (id),
    queued_at timestamptz NOT NULL,
    offered_at timestamptz,
    accepted_at timestamptz,
    ended_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS live_chat_requests_one_open_per_case
ON live_chat_requests (case_id) WHERE status IN ('waiting', 'offered', 'active');
-- Offers that move on (issue #139). An offer expires; who declined it or let it expire is not offered it
-- again. After the last offer the request is 'unanswered' and leaves the line. Missed offers in a row
-- set a specialist to away, and auto_away_at tells them when.
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS offers integer NOT NULL DEFAULT 0;
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS missed_by uuid[] NOT NULL DEFAULT '{}';
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS offer_expires_at timestamptz;
ALTER TABLE specialist_availability ADD COLUMN IF NOT EXISTS missed_in_a_row integer NOT NULL DEFAULT 0;
ALTER TABLE specialist_availability ADD COLUMN IF NOT EXISTS auto_away_at timestamptz;
-- The customer's last chat refresh while in the line (issue #140).
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS customer_seen_at timestamptz;
-- Quiet customers (issue #142). An idle live chat frees the specialist's slot and stays open until
-- it closes, so it still counts as the case's one open request. A customer back from idle with no
-- free slot goes to the front of the line: a set returned_at puts the request ahead of the rest.
CREATE UNIQUE INDEX IF NOT EXISTS live_chat_requests_one_open_or_idle_per_case
ON live_chat_requests (case_id) WHERE status IN ('waiting', 'offered', 'active', 'idle');
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS returned_at timestamptz;
-- The offer shows why the customer is in the line and their language, 'en' or 'es' (user story 27).
-- How the request left the line or ended: resolved, escalated, closed_quiet, left, abandoned, unanswered,
-- or refused. A quiet close is Resolved like a specialist's Resolve, and end_reason tells them apart.
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS language text;
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS end_reason text;
-- When the specialist was last offered a request. A tie on spare capacity goes to the one offered
-- work longest ago, and never offered comes first (spec #131).
ALTER TABLE specialist_availability ADD COLUMN IF NOT EXISTS last_offered_at timestamptz;
"""


class CaseClosed(Exception):
    """A Resolved or Escalated case does not take another message."""


class ProposerCannotApprove(Exception):
    """The staff member who proposed a refund cannot approve it."""


class ProposalNotWaiting(Exception):
    """There is no waiting proposal on this case."""


class AmountNotEditable(Exception):
    """The waiting proposal has no amount, such as a cancel or an address change."""


class AmountOutOfBounds(Exception):
    """The edited amount is above the order total."""


class NotInInbox(Exception):
    """The case is not escalated, so the escalations inbox does not hold it."""


class AlreadyPickedUp(Exception):
    """Another specialist picked up this escalated case first."""


class NotYours(Exception):
    """Only the specialist who picked up an escalated chat case replies on it. The same for a live chat."""


class NoFollowUp(Exception):
    """The chat's follow-up is not to leave a message: the agent's last turns helped, or the case is not open."""


class NothingToTake(Exception):
    """No request in the line waits for this specialist, or they are away or have no free slot."""


class ProposalWaiting(Exception):
    """A live chat does not end while its case waits for a lead. Ending it would drop the proposal (R45)."""


class CaseStore:
    def __init__(
        self,
        pool,
        clock: Clock,
        request_limit: int = defaults.REQUEST_LIMIT,
        token_budget: int = defaults.DAILY_TOKEN_BUDGET,
        chat_turns_per_customer: int = defaults.CHAT_TURNS_PER_CUSTOMER,
        chat_turns_per_day: int = defaults.CHAT_TURNS_PER_DAY,
        turn_seconds: float = defaults.TURN_DEADLINE_SECONDS,
        failed_turns_before_follow_up: int = defaults.FAILED_TURNS_BEFORE_FOLLOW_UP,
        live_chat: bool = defaults.LIVE_CHAT_ENABLED,
        chats_per_specialist: int = defaults.LIVE_CHATS_PER_SPECIALIST,
        offer_seconds: float = defaults.OFFER_ACCEPT_SECONDS,
        offers_before_message: int = defaults.OFFERS_BEFORE_LEAVE_MESSAGE,
        missed_offers_before_away: int = defaults.MISSED_OFFERS_BEFORE_AWAY,
        check_in_seconds: float = defaults.DESK_CHECK_IN_SECONDS,
        line_gone_minutes: float = defaults.LINE_GONE_MINUTES,
        longest_wait_minutes: float = defaults.LONGEST_WAIT_MINUTES,
        wait_history_days: int = defaults.WAIT_HISTORY_DAYS,
        wait_history_chats: int = defaults.WAIT_HISTORY_CHATS,
        quiet_minutes: tuple[float, float, float] = (
            defaults.QUIET_NUDGE_MINUTES,
            defaults.QUIET_IDLE_MINUTES,
            defaults.QUIET_CLOSE_MINUTES,
        ),
        quiet_specialist_minutes: float = defaults.QUIET_SPECIALIST_MINUTES,
    ) -> None:
        self._pool = pool
        self._clock = clock
        self._request_limit = request_limit
        self._token_budget = token_budget
        self._chat_turns_per_customer = chat_turns_per_customer
        self._chat_turns_per_day = chat_turns_per_day
        self._turn_seconds = turn_seconds
        self._failed_turns = failed_turns_before_follow_up
        self._live_chat_enabled = live_chat
        # The capacity a specialist starts with when they first set Available (user story 61).
        self._chats_per_specialist = chats_per_specialist
        self._offer_window = timedelta(seconds=offer_seconds)
        self._offers_before_message = offers_before_message
        self._missed_before_away = missed_offers_before_away
        self._check_in_window = timedelta(seconds=check_in_seconds)
        self._line_gone_minutes = line_gone_minutes
        self._longest_wait = longest_wait_minutes
        self._wait_history_days = wait_history_days
        self._wait_history_chats = wait_history_chats
        # Minutes of customer quiet before the nudge, idle, and close (R44).
        self._nudge, self._idle, self._close = (timedelta(minutes=m) for m in quiet_minutes)
        # A customer waiting longer than this for the specialist's reply is flagged to leads (R49).
        self._quiet_specialist = timedelta(minutes=quiet_specialist_minutes)

    def ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)
            for name, email, phone in _CUSTOMERS:
                conn.execute(
                    """
                    INSERT INTO customers (id, name, email, phone)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (uuid.uuid5(uuid.NAMESPACE_URL, f"northstar-customer:{email}"), name, email, phone),
                )
            for order_id, email, status, purchased_on, lines, refunds, total_cents, delivered_on, category, shipped_on in _ORDERS:
                conn.execute(
                    """
                    INSERT INTO orders (
                        id, customer_id, status, purchased_on, lines, refunds,
                        total_cents, delivered_on, category, shipped_on
                    )
                    VALUES (
                        %s, (SELECT id FROM customers WHERE email = %s), %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        shipped_on = EXCLUDED.shipped_on,
                        total_cents = EXCLUDED.total_cents,
                        delivered_on = EXCLUDED.delivered_on,
                        category = EXCLUDED.category,
                        refunds = EXCLUDED.refunds
                    """,
                    (order_id, email, status, purchased_on, lines, refunds, total_cents, delivered_on, category, shipped_on),
                )
            for name, category, price_cents, sizes, in_stock, final_sale in _CATALOG:
                conn.execute(
                    """
                    INSERT INTO catalog_items
                        (name, category, price_cents, sizes, in_stock, final_sale)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    (name, category, price_cents, sizes, in_stock, final_sale),
                )
            conn.commit()

    def current(self, staff_id: uuid.UUID) -> dict:
        return self._view(self._open(staff_id))

    def read(self, case_id: uuid.UUID) -> dict | None:
        """Any case, read-only, for a lead deciding from the queue."""
        if self._case_row(case_id) is None:
            return None
        return self._view(case_id)

    def start_new(self, staff_id: uuid.UUID) -> dict:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT id, status FROM cases
                WHERE staff_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (staff_id,),
            ).fetchone()
            if row is not None and row["status"] in ("Open", "Waiting for approval"):
                case_id = row["id"]
            else:
                case_id = uuid.uuid4()
                conn.execute(
                    "INSERT INTO cases (id, staff_id, created_at) VALUES (%s, %s, %s)",
                    (case_id, staff_id, self._clock.now()),
                )
                conn.commit()
        return self._view(case_id)

    def bind(self, staff_id: uuid.UUID, query: str) -> dict:
        case_id = self._open(staff_id)
        if self._status(case_id) != "Open":
            raise CaseClosed()
        found = self._find_customer(query)
        if found is not None:
            with self._pool.connection() as conn:
                conn.execute(
                    "UPDATE cases SET customer_id = %s WHERE id = %s",
                    (found, case_id),
                )
                conn.commit()
        return self._view(case_id)

    def close(self, staff_id: uuid.UUID, status: str, final_text: str) -> dict:
        case_id = self._open(staff_id)
        if self._status(case_id) != "Open":
            raise CaseClosed()
        packet = self._manual_packet(case_id, final_text) if status == "Escalated" else ""
        with self._pool.connection() as conn:
            draft = conn.execute(
                """
                SELECT body FROM case_messages
                WHERE case_id = %s AND role = 'assistant'
                ORDER BY id DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            conn.execute(
                """
                UPDATE cases
                SET status = %s, draft_text = %s, final_text = %s, handoff_text = %s
                WHERE id = %s
                """,
                (status, "" if draft is None else draft["body"], final_text.strip(), packet, case_id),
            )
            conn.commit()
        if draft is not None and final_text.strip() != draft["body"]:
            self._judge_edit(case_id, final_text=final_text.strip())
        return self._view(case_id)

    def _mark_escalated(self, case_id: uuid.UUID, handoff_text: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE cases
                SET status = 'Escalated', draft_text = %s, handoff_text = %s
                WHERE id = %s
                """,
                (handoff_text, handoff_text, case_id),
            )
            conn.commit()

    def _escalate_live(self, case_id: uuid.UUID, customer_id: uuid.UUID, handoff_text: str, spanish: bool) -> bool:
        """With live chat on, a chat escalation joins the line ahead of requested chats (R39, R42).

        The case stays Open for the live chat and keeps its handoff, so the specialist who accepts reads it.
        The agent is quiet from here (see `_held`). Leaving the line any way but with a specialist puts the
        case in the escalations inbox. False when the line turns it away: it goes to the inbox now.
        """
        with self._pool.connection() as conn:
            conn.execute("UPDATE cases SET handoff_text = %s WHERE id = %s", (handoff_text, case_id))
            # A customer already waiting moves up with the escalation.
            conn.execute(
                "UPDATE live_chat_requests SET reason = 'escalated' WHERE case_id = %s AND status IN ('waiting', 'offered')",
                (case_id,),
            )
            conn.commit()
        # The customer's escalating message is not saved yet, so its language comes with it.
        return self.request_live(customer_id, reason="escalated", spanish=spanish)

    def _customer_id(self, case_id: uuid.UUID) -> uuid.UUID | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT customer_id FROM cases WHERE id = %s", (case_id,)).fetchone()
        return None if row is None else row["customer_id"]

    def _remember_preferences(self, case_id: uuid.UUID, question: str, now: datetime) -> None:
        prefs = stated(question)
        customer_id = self._customer_id(case_id) if prefs else None
        if customer_id is not None:
            remember(self._pool.conninfo, customer_id, prefs, _iso(now))

    def _tried(self, case_id: uuid.UUID) -> tuple[str, ...]:
        """What the agent already did on this case, for the handoff packet."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT decision, citations FROM case_messages
                WHERE case_id = %s AND role = 'assistant' AND decision IS NOT NULL
                ORDER BY id
                """,
                (case_id,),
            ).fetchall()
        return tuple(
            row["decision"] + (f" ({', '.join(row['citations'])})" if row["citations"] else "") for row in rows
        )

    def _manual_packet(self, case_id: uuid.UUID, note: str) -> str:
        with self._pool.connection() as conn:
            asked = conn.execute(
                "SELECT body FROM case_messages WHERE case_id = %s AND role = 'user' ORDER BY id DESC LIMIT 1",
                (case_id,),
            ).fetchone()
            cited = conn.execute(
                """
                SELECT DISTINCT unnest(citations) AS section FROM case_messages
                WHERE case_id = %s AND role = 'assistant'
                """,
                (case_id,),
            ).fetchall()
        sections = tuple(sorted(row["section"] for row in cited))
        question = "" if asked is None else asked["body"]
        return manual_handoff(question, sections, self._tried(case_id), note).text

    def ask(
        self,
        staff_id: uuid.UUID,
        question: str,
        photo: str | None = None,
        *,
        case_id: uuid.UUID | None = None,
        chat_customer: uuid.UUID | None = None,
        staff_turn: bool = False,
        chat_order: str | None = None,
    ) -> dict:
        # Each turn has a deadline. Optional model steps are skipped when it is close (R36).
        with turn_deadline(self._clock, self._turn_seconds):
            return self._ask(staff_id, question, photo, case_id, chat_customer, staff_id if staff_turn else None, chat_order)

    def _ask(
        self,
        staff_id: uuid.UUID,
        question: str,
        photo: str | None,
        case_id: uuid.UUID | None,
        chat_customer: uuid.UUID | None,
        by: uuid.UUID | None = None,
        chat_order: str | None = None,
    ) -> dict:
        case_id = case_id or self._open(staff_id)
        if self._status(case_id) != "Open":
            raise CaseClosed()
        now = self._clock.now()
        if chat_customer is None:
            key = f"staff:{staff_id}"
            limits = {key: self._request_limit}
        else:
            # Each chat customer has their own turns. The total across customers is the cost ceiling.
            key = f"chat:{chat_customer}"
            limits = {key: self._chat_turns_per_customer, "chat": self._chat_turns_per_day}
        if not self._take(now.date(), "requests", 1, limits):
            return self._save(case_id, question, _plain("limit", REQUEST_LIMIT_TEXT), now, by)
        if has_secret(question):
            return self._save(case_id, question, _plain("blocked", SECRET_REPLY), now, by)
        # A Spanish question is decided in English and answered in Spanish (issue #81).
        spanish = is_spanish(question)
        asked = to_english(screen(question)) if spanish else question
        reply = (lambda draft: to_spanish(draft)) if spanish else (lambda draft: draft)
        # A photo is described for the lead. It never chooses the action (issue #80).
        seen = describe(photo, asked) if photo else None
        note = seen.line if seen else ("Photo: attached, but it could not be described." if photo else "")
        asked_with = f"{question}\n[Photo attached]" if photo else question
        self._remember_preferences(case_id, asked, now)
        # A customer chat turn records why it handed over on its root run (issue #145). A desk turn does not:
        # a specialist reads every desk draft, so a person is always there.
        handover = (lambda decision: self._handover_reason(case_id, decision)) if chat_customer is not None else None
        escalated = handoff(asked, self._tried(case_id))
        if escalated is not None:
            section, text = escalated.section, escalated.text
            if not (self._live_chat_enabled and chat_customer is not None and self._escalate_live(case_id, chat_customer, text, spanish)):
                self._mark_escalated(case_id, text)
            # Through the graph, so the escalation has a LangGraph trace for the safety rule and the judge.
            fixed = Draft("escalate", text, (section,), {section: "strong"}, ())
            tools = TurnTools(refund=lambda _text: fixed, support=lambda _text: fixed)
            return self._save(case_id, asked_with, reply(_noted(self._turn(case_id, asked, tools, handover), note)), now, by)
        if _blocked(question) or _blocked(asked):
            return self._save(case_id, asked_with, reply(_plain("safe", SAFE_REPLY)), now, by)
        if chat_customer is not None and asks_for_person(asked):
            # The chat offers a person, as after failed turns (R35, R39). Through the graph, like an escalation,
            # so the root run records the hand-over.
            fixed = _plain(PERSON_REQUESTED, PERSON_TEXT_LIVE if self._live_chat_enabled else PERSON_TEXT)
            tools = TurnTools(refund=lambda _text: fixed, support=lambda _text: fixed)
            return self._save(case_id, asked_with, reply(self._turn(case_id, asked, tools, handover)), now, by)
        tools = TurnTools(
            refund=lambda text: self._gated_draft(case_id, staff_id, text, now, note, chat_order),
            support=lambda text: self._support_draft(case_id, key, text, now),
        )
        return self._save(case_id, asked_with, reply(_noted(self._turn(case_id, asked, tools, handover), note)), now, by)

    def _turn(self, case_id: uuid.UUID, question: str, tools: TurnTools, handover=None) -> Draft:
        return run_turn(question, tools, graph=graph_for(self._pool.conninfo), thread_id=str(case_id), handover=handover)

    def _handover_reason(self, case_id: uuid.UUID, decision: str) -> str:
        """Why the agent handed this chat turn's customer to a person, or "none" (issue #145).

        "escalated" for a handbook escalation. "requested" or "three_failures" when the chat offers a person
        after this turn, which is not saved yet. A press of a chat button has no turn: the line row keeps its
        reason, and a left message is its own decision on the case.
        """
        if decision == "escalate":
            return "escalated"
        return self._person_follow_up(case_id, decision) or NO_HANDOVER

    def _save(self, case_id: uuid.UUID, question: str, draft: Draft, now: datetime, by: uuid.UUID | None = None) -> dict:
        """Save the question and the draft. `by` marks a specialist's turn on a chat case, which the customer does not see."""
        run_id = draft.run_id
        draft = guard_draft(draft)
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO case_messages (case_id, role, body, staff_id, created_at)
                VALUES (%s, 'user', %s, %s, %s)
                """,
                (case_id, screen(question.strip()), by, now),
            )
            conn.execute(
                """
                INSERT INTO case_messages
                    (case_id, role, body, decision, citations, strengths, steps, run_id,
                     retrieved_sections, retrieved_scores, staff_id, created_at)
                VALUES (%s, 'assistant', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    case_id,
                    screen(draft.text),
                    draft.decision,
                    list(draft.citations),
                    [draft.match[section_id] for section_id in draft.citations],
                    list(draft.steps),
                    run_id,
                    [section_id for section_id, _ in draft.retrieved],
                    [score for _, score in draft.retrieved],
                    by,
                    now,
                ),
            )
            conn.commit()
        return self._view(case_id)

    def _view(self, case_id: uuid.UUID) -> dict:
        row = self._case_row(case_id)
        customer = None if row["name"] is None else {"name": row["name"], "email": row["email"]}
        return {
            "id": str(case_id),
            "status": row["status"],
            "draft_text": row["draft_text"],
            "final_text": row["final_text"],
            "customer": customer,
            "messages": self._messages(case_id),
            "action": row["proposal_action"],
            "refund_amount_cents": row["proposal_amount_cents"],
            "proposed_amount_cents": row["proposed_amount_cents"],
            "proposal_details": row["proposal_details"],
            "handoff": row["handoff_text"],
            "policy_citations": list(row["proposal_citations"] or []),
            "ticket_id": self._ticket_id(case_id),
            "stale": row["status"] == "Waiting for approval" and _is_stale(row["proposed_at"], self._clock.now()),
            "rejection_reason": row["rejection_reason"],
            "history": self._history(case_id),
            "preferences": self._preferences(case_id),
        }

    def _history(self, case_id: uuid.UUID) -> list[dict]:
        with self._pool.connection() as conn:
            customer = conn.execute(
                "SELECT customer_id FROM cases WHERE id = %s",
                (case_id,),
            ).fetchone()
            if customer is None or customer["customer_id"] is None:
                return []
            rows = conn.execute(
                """
                SELECT cases.id, cases.status, cases.rejection_reason,
                       EXISTS (SELECT 1 FROM tickets WHERE tickets.case_id = cases.id) AS ticketed,
                       orders.refunds
                FROM cases
                LEFT JOIN orders ON orders.id = cases.proposal_order_id
                WHERE cases.customer_id = %s AND cases.id <> %s
                ORDER BY cases.created_at DESC, cases.id DESC
                LIMIT 5
                """,
                (customer["customer_id"], case_id),
            ).fetchall()
        history = []
        for row in rows:
            if row["ticketed"]:
                outcome = "Ticket"
            elif row["rejection_reason"]:
                outcome = "Rejected"
            else:
                outcome = row["status"]
            refunds = row["refunds"]
            history.append(
                {
                    "id": str(row["id"]),
                    "status": row["status"],
                    "outcome": outcome,
                    "refunded_lines": [] if not refunds or refunds == "none" else [refunds],
                }
            )
        return history

    def _preferences(self, case_id: uuid.UUID) -> dict[str, str]:
        customer_id = self._customer_id(case_id)
        return {} if customer_id is None else recall(self._pool.conninfo, customer_id)

    def _status(self, case_id: uuid.UUID) -> str:
        return self._case_row(case_id)["status"]

    def _case_row(self, case_id: uuid.UUID):
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT cases.status, cases.draft_text, cases.final_text,
                       cases.proposal_action, cases.proposal_amount_cents,
                       cases.proposal_citations, cases.proposal_details, cases.proposed_at,
                       cases.rejection_reason, cases.handoff_text, cases.proposed_amount_cents,
                       customers.name, customers.email
                FROM cases
                LEFT JOIN customers ON customers.id = cases.customer_id
                WHERE cases.id = %s
                """,
                (case_id,),
            ).fetchone()

    def _customer(self, case_id: uuid.UUID) -> dict | None:
        row = self._case_row(case_id)
        if row["name"] is None:
            return None
        return {"name": row["name"], "email": row["email"]}

    def _find_customer(self, query: str) -> uuid.UUID | None:
        text = query.strip().lower()
        with self._pool.connection() as conn:
            if "@" in text:
                row = conn.execute(
                    "SELECT id FROM customers WHERE email = %s",
                    (text,),
                ).fetchone()
            else:
                digits = re.sub(r"\D", "", text)
                row = conn.execute(
                    "SELECT id FROM customers WHERE phone = right(%s, 10)",
                    (digits,),
                ).fetchone() if len(digits) >= 10 else None
        return row["id"] if row else None

    def _order_draft(self, case_id: uuid.UUID, order_id: str, question: str) -> Draft:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT orders.status, orders.purchased_on, orders.lines, orders.refunds,
                       orders.customer_id = cases.customer_id AS owned
                FROM cases
                LEFT JOIN orders ON orders.id = %s
                WHERE cases.id = %s
                """,
                (order_id, case_id),
            ).fetchone()
        if row is None or row["status"] is None:
            return _plain("unknown", "That order id is unknown.")
        if not row["owned"]:
            return _plain("not_found", "Not found for this customer.")
        text = (
            f"Status: {row['status']}. "
            f"Purchased: {row['purchased_on']}. "
            f"Lines: {row['lines']}. "
            f"Prior refunds: {row['refunds']}."
        )
        if re.search(r"\btracking\b", question.lower()):
            text += " The order record does not include tracking."
        return _plain("order", text)

    def _lock_waiting(self, conn, lead_id: uuid.UUID, case_id: uuid.UUID):
        row = conn.execute(
            """
            SELECT status, proposed_by, proposal_amount_cents, proposal_order_id
            FROM cases WHERE id = %s
            """,
            (case_id,),
        ).fetchone()
        if row is None or row["status"] != "Waiting for approval":
            raise ProposalNotWaiting()
        if row["proposed_by"] == lead_id:
            raise ProposerCannotApprove()
        return row

    def _write_ticket(self, conn, case_id: uuid.UUID, amount_cents: int | None) -> uuid.UUID:
        # One ticket per proposal. The ticket keeps the action and order it records.
        ticket_id = uuid.uuid4()
        conn.execute(
            """
            INSERT INTO tickets (id, case_id, amount_cents, proposal_id, action, order_id)
            SELECT %s, id, %s, proposal_id, proposal_action, proposal_order_id
            FROM cases WHERE id = %s
            """,
            (ticket_id, amount_cents, case_id),
        )
        return ticket_id

    def _current_ticket(self, case_id: uuid.UUID):
        """The ticket for the case's latest proposal, or None."""
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT tickets.id, tickets.amount_cents
                FROM tickets
                JOIN cases ON cases.id = tickets.case_id
                WHERE tickets.case_id = %s
                  AND tickets.proposal_id IS NOT DISTINCT FROM cases.proposal_id
                """,
                (case_id,),
            ).fetchone()

    def _ticket_amount(self, case_id: uuid.UUID) -> tuple[str, int | None] | None:
        row = self._current_ticket(case_id)
        if row is None:
            return None
        return str(row["id"]), row["amount_cents"]

    def _ticket_actions(self, order_id: str) -> frozenset[str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT action FROM tickets WHERE order_id = %s",
                (order_id,),
            ).fetchall()
        return frozenset(row["action"] or "" for row in rows)

    def _catalog_row(self, item: str):
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT sizes, in_stock, final_sale FROM catalog_items WHERE lower(name) = lower(%s)",
                (item,),
            ).fetchone()

    def _ticket_id(self, case_id: uuid.UUID) -> str | None:
        row = self._current_ticket(case_id)
        return None if row is None else str(row["id"])

    def gaps(self) -> list[dict]:
        """Handbook questions that ended in abstain, most frequent first (R19). Read-only."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT asked.body AS question, answer.retrieved_sections, answer.retrieved_scores,
                       answer.created_at
                FROM case_messages answer
                JOIN LATERAL (
                    SELECT body FROM case_messages
                    WHERE case_id = answer.case_id AND role = 'user' AND id < answer.id
                    ORDER BY id DESC
                    LIMIT 1
                ) asked ON true
                WHERE answer.role = 'assistant' AND answer.decision = 'abstain' AND answer.body = %s
                """,
                (screen(ABSTAIN_TEXT),),
            ).fetchall()
        grouped: dict[str, dict] = {}
        for row in rows:
            key = " ".join(row["question"].lower().split()).rstrip("?.! ")
            gap = grouped.setdefault(key, {"question": row["question"], "count": 0, "last_seen": row["created_at"], "sections": {}})
            gap["count"] += 1
            gap["last_seen"] = max(gap["last_seen"], row["created_at"])
            for section_id, score in zip(row["retrieved_sections"], row["retrieved_scores"], strict=False):
                gap["sections"][section_id] = max(score, gap["sections"].get(section_id, 0.0))
        ordered = sorted(grouped.values(), key=lambda gap: (-gap["count"], -gap["last_seen"].timestamp()))
        return [
            {
                "question": gap["question"],
                "count": gap["count"],
                "last_seen": _iso(gap["last_seen"]),
                "sections": [
                    {"section_id": section_id, "score": round(score, 3)}
                    for section_id, score in sorted(gap["sections"].items(), key=lambda item: -item[1])
                ],
            }
            for gap in ordered
        ]

    def pending(self) -> list[dict]:
        now = self._clock.now()
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT cases.id, cases.proposal_action, cases.proposal_amount_cents,
                       cases.proposal_order_id, cases.proposal_details, cases.proposed_at,
                       cases.proposal_citations, orders.lines, orders.status AS order_status,
                       orders.total_cents,
                       (SELECT body FROM case_messages
                        WHERE case_id = cases.id AND role = 'user'
                        ORDER BY id DESC LIMIT 1) AS question,
                       (SELECT body FROM case_messages
                        WHERE case_id = cases.id AND role = 'assistant'
                        ORDER BY id DESC LIMIT 1) AS draft
                FROM cases
                LEFT JOIN orders ON orders.id = cases.proposal_order_id
                WHERE cases.status = 'Waiting for approval'
                ORDER BY cases.proposed_at
                """
            ).fetchall()
        waiting = []
        for row in rows:
            proposed_at = row["proposed_at"]
            age = 0 if proposed_at is None else int((now - proposed_at).total_seconds())
            waiting.append(
                {
                    "case_id": str(row["id"]),
                    "action": row["proposal_action"],
                    "amount_cents": row["proposal_amount_cents"],
                    "order_id": row["proposal_order_id"],
                    "details": row["proposal_details"],
                    "citations": list(row["proposal_citations"] or []),
                    "order_summary": (
                        ""
                        if row["lines"] is None
                        else f"{row['lines']}. Status: {row['order_status']}. Total: {row['total_cents']} cents."
                    ),
                    "age_seconds": age,
                    "stale": _is_stale(proposed_at, now),
                    "question": row["question"] or "",
                    "draft": row["draft"] or "",
                }
            )
        return waiting

    def approve(self, lead_id: uuid.UUID, case_id: uuid.UUID) -> str:
        existing = self._ticket_id(case_id)
        if existing:
            return existing
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT status, proposed_by, proposal_amount_cents FROM cases WHERE id = %s",
                (case_id,),
            ).fetchone()
            if row is None or row["status"] != "Waiting for approval":
                raise ProposalNotWaiting()
            if row["proposed_by"] == lead_id:
                raise ProposerCannotApprove()
            ticket_id = self._write_ticket(conn, case_id, row["proposal_amount_cents"])
            conn.execute("UPDATE cases SET status = 'Open' WHERE id = %s", (case_id,))
            conn.commit()
        self._resume(case_id, "approve")
        return str(ticket_id)

    def edit_amount(self, lead_id: uuid.UUID, case_id: uuid.UUID, amount_cents: int) -> tuple[str, int]:
        existing = self._ticket_amount(case_id)
        if existing is not None:
            return existing
        with self._pool.connection() as conn:
            proposal = self._lock_waiting(conn, lead_id, case_id)
            if proposal["proposal_amount_cents"] is None:
                raise AmountNotEditable()
            total = conn.execute(
                "SELECT total_cents FROM orders WHERE id = %s",
                (proposal["proposal_order_id"],),
            ).fetchone()
            cap = None if total is None else total["total_cents"]
            if cap is None or amount_cents > cap:
                raise AmountOutOfBounds()
            ticket_id = self._write_ticket(conn, case_id, amount_cents)
            conn.execute(
                """
                UPDATE cases
                SET status = 'Open', proposal_amount_cents = %s
                WHERE id = %s
                """,
                (amount_cents, case_id),
            )
            conn.commit()
        self._resume(case_id, "edit")
        if amount_cents != proposal["proposal_amount_cents"]:
            self._judge_edit(case_id, amount_cents=amount_cents, proposed_cents=proposal["proposal_amount_cents"])
        return str(ticket_id), amount_cents

    def reject(self, lead_id: uuid.UUID, case_id: uuid.UUID, reason: str) -> None:
        with self._pool.connection() as conn:
            self._lock_waiting(conn, lead_id, case_id)
            conn.execute(
                """
                UPDATE cases
                SET status = 'Open', rejection_reason = %s
                WHERE id = %s
                """,
                (reason.strip(), case_id),
            )
            conn.commit()
        self._resume(case_id, "reject")

    def _judge_edit(
        self,
        case_id: uuid.UUID,
        final_text: str | None = None,
        amount_cents: int | None = None,
        proposed_cents: int | None = None,
    ) -> None:
        """Score the turn a person edited, and send the edit pair for review (AGENTS.md, R18)."""
        with self._pool.connection() as conn:
            draft = conn.execute(
                """
                SELECT id, body, decision, citations, run_id FROM case_messages
                WHERE case_id = %s AND role = 'assistant'
                ORDER BY id DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            if draft is None or draft["run_id"] is None:
                return
            asked = conn.execute(
                """
                SELECT body FROM case_messages
                WHERE case_id = %s AND role = 'user' AND id < %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (case_id, draft["id"]),
            ).fetchone()
        text = final_text or f"{draft['body']}\nThe lead changed the amount to {amount_cents} cents."
        question = "" if asked is None else asked["body"]
        before = draft["body"] if final_text else f"{proposed_cents} cents"
        after = final_text if final_text else f"{amount_cents} cents"
        # After the close or the ticket returns. A LangSmith or judge outage is logged, never raised.
        citations = list(draft["citations"])
        online.background(record_judge, draft["run_id"], question, draft["decision"] or "", text, citations, 1.0, edited=True)
        online.background(record_edit, draft["run_id"], question, citations, before, after)

    # Customer chat (issue #79): the same turn and the same gates, a different identity and view.

    def chat_customer(self, order_id: str, email: str) -> uuid.UUID | None:
        """The customer who owns this order, when the email is theirs. The chat sign-in check."""
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT customers.id FROM orders JOIN customers ON customers.id = orders.customer_id
                WHERE upper(orders.id) = upper(%s) AND lower(customers.email) = lower(%s)
                """,
                (order_id.strip(), email.strip()),
            ).fetchone()
        return None if row is None else row["id"]

    def chat(self, customer_id: uuid.UUID) -> dict:
        case_id = self._chat_case(customer_id)
        self._tick()
        if self._live_chat_enabled:
            self._refreshed(case_id)
        return self._chat_view(case_id)

    def chat_ask(self, customer_id: uuid.UUID, question: str, order_id: str | None = None) -> dict:
        self._tick()
        case_id = self._chat_case(customer_id)
        if self._live_chat_enabled and self._held(case_id):
            # A specialist holds this chat, or an escalation waits for one. The agent is quiet: no model call,
            # no limit or budget charge (R46).
            with self._pool.connection() as conn:
                conn.execute(
                    "INSERT INTO case_messages (case_id, role, body, created_at) VALUES (%s, 'user', %s, %s)",
                    (case_id, screen(question.strip()), self._clock.now()),
                )
                conn.commit()
            # A customer back from idle returns to their specialist or to the front of the line.
            self._tick()
            return self._chat_view(case_id)
        case_id = self._writable(customer_id, case_id)
        # Limits are per customer, so one customer cannot use up the chat for everyone.
        self.ask(staff_id_for(CHAT_STAFF_EMAIL), question, case_id=case_id, chat_customer=customer_id, chat_order=order_id)
        return self._chat_view(case_id)

    def _writable(self, customer_id: uuid.UUID, case_id: uuid.UUID) -> uuid.UUID:
        """The chat case a new message or live chat request goes on.

        An escalated case is a specialist's now, and a resolved one is closed. Either starts a new case.
        """
        status = self._status(case_id)
        if status in ("Escalated", "Resolved"):
            return self._new_chat_case(customer_id)
        if status != "Open":
            raise CaseClosed()
        return case_id

    def _chat_case(self, customer_id: uuid.UUID) -> uuid.UUID:
        """The customer's latest chat case, bound to them, or a new one.

        A resolved case is still shown, so the customer reads how their live chat ended.
        """
        chat_staff = staff_id_for(CHAT_STAFF_EMAIL)
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM cases WHERE staff_id = %s AND customer_id = %s
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (chat_staff, customer_id),
            ).fetchone()
            if row is not None:
                return row["id"]
        return self._new_chat_case(customer_id)

    def _new_chat_case(self, customer_id: uuid.UUID) -> uuid.UUID:
        case_id = uuid.uuid4()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO cases (id, staff_id, customer_id, created_at) VALUES (%s, %s, %s, %s)",
                (case_id, staff_id_for(CHAT_STAFF_EMAIL), customer_id, self._clock.now()),
            )
            conn.commit()
        return case_id

    def _chat_view(self, case_id: uuid.UUID, staff: bool = False) -> dict:
        """What a customer may see: their own words and checked replies. No draft, amount, packet, or history.

        `staff` adds the specialist's action turns, for the specialist's own live chat page.
        """
        row = self._case_row(case_id)
        ticket = self._ticket_id(case_id)
        if row["status"] == "Waiting for approval":
            status = "A person on our team is reviewing your request. Nothing is approved yet."
        elif row["status"] == "Escalated":
            status = f"A specialist will follow up with you. {COME_BACK_TEXT}"
        elif self._live_chat_enabled and self._still_there(case_id):
            status = STILL_THERE_TEXT
        elif ticket:
            status = f"Our team approved your request. Reference {ticket}."
        elif row["rejection_reason"]:
            status = "Our team could not approve that request."
        elif row["status"] == "Resolved":
            status = "This chat is closed. Write again to start a new one."
        else:
            status = ""
        if self._live_chat_enabled and row["status"] == "Open":
            status = self._line_text(case_id) or status
        messages, spanish = [], False
        for m in self._chat_messages(case_id):
            if m["role"] != "specialist" and m["staff_id"] is not None:
                # A specialist's action turn (R45). The customer sees only the status, never the ask, amount, or rule.
                if staff:
                    messages.append({"role": "action" if m["role"] == "user" else "desk", "text": m["body"]})
                continue
            if m["role"] == "user":
                spanish = is_spanish(m["body"])
                messages.append({"role": "user", "text": m["body"]})
            elif m["role"] == "specialist":
                # A person's words, screened when saved. Never swapped for a fixed text.
                messages.append({"role": "specialist", "name": m["name"], "text": m["body"]})
            else:
                messages.append({"role": m["role"], "text": _for_customer(m["decision"], m["body"], spanish)})
        return {"status": status, "messages": messages}

    def chat_follow_up(self, customer_id: uuid.UUID) -> str | None:
        self._tick()
        return self._follow_up(self._chat_case(customer_id))

    def _follow_up(self, case_id: uuid.UUID) -> str | None:
        """The chat's follow-up: what it offers the customer beside the agent, or None.

        "leave_message" when the line turned the customer away (R41) or no specialist accepted the last
        offer of a live chat (issue #139). After failed turns in a row (R35), or when the customer asked for a
        person (R39): "talk_to_person" with live chat on (issue #141), else "leave_message".
        """
        if self._left_line(case_id) in ("refused", "unanswered"):
            return "leave_message"
        if self._person_follow_up(case_id):
            return "talk_to_person" if self._live_chat_enabled else "leave_message"
        return None

    def leave_message(self, customer_id: uuid.UUID, text: str) -> dict:
        """The customer's message for a specialist, while the follow-up stands.

        The chat case becomes Escalated with a handoff that stands alone, so it lands in the
        escalations inbox. The specialist's reply reaches this chat through the inbox (R38).
        """
        case_id = self._chat_case(customer_id)
        if self._follow_up(case_id) != "leave_message":
            raise NoFollowUp()
        unanswered = self._left_line(case_id) == "unanswered"
        message = screen(text.strip())
        packet = self._left_message_packet(case_id, message, unanswered, self._person_follow_up(case_id) == "requested")
        now = self._clock.now()
        with self._pool.connection() as conn:
            # The status check is in the update, so a message is left once even when two arrive together.
            escalated = conn.execute(
                """
                UPDATE cases SET status = 'Escalated', draft_text = %s, handoff_text = %s
                WHERE id = %s AND status = 'Open'
                RETURNING id
                """,
                (packet, packet, case_id),
            ).fetchone()
            if escalated is None:
                conn.rollback()
                raise NoFollowUp()
            conn.execute(
                "INSERT INTO case_messages (case_id, role, body, created_at) VALUES (%s, 'user', %s, %s)",
                (case_id, message, now),
            )
            conn.execute(
                """
                INSERT INTO case_messages (case_id, role, body, decision, created_at)
                VALUES (%s, 'assistant', %s, 'left_message', %s)
                """,
                (case_id, _CHAT_TEXT["left_message"], now),
            )
            conn.commit()
        return self._chat_view(case_id)

    def _person_follow_up(self, case_id: uuid.UUID, latest: str | None = None) -> str | None:
        """Why the open case offers a person after the agent's turns, or None.

        "requested" when the last turn was the customer asking for a person (R39). "three_failures" when the
        last turns all failed (R35); one turn that helped resets the count. `latest` is the decision of a turn
        not saved yet. Not while the case is in the line or in a live chat, idle included: a person is
        already on the way (issues #138 and #142).
        """
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT c.status = 'Open' AND NOT EXISTS (
                           SELECT 1 FROM live_chat_requests r
                           WHERE r.case_id = c.id AND r.status IN ('waiting', 'offered', 'active', 'idle')
                       ) AS free,
                       ARRAY(
                           SELECT m.decision FROM case_messages m
                           WHERE m.case_id = c.id AND m.role = 'assistant'
                           ORDER BY m.id DESC
                           LIMIT %s
                       ) AS decisions
                FROM cases c WHERE c.id = %s
                """,
                (self._failed_turns, case_id),
            ).fetchone()
        if row is None or not row["free"]:
            return None
        recent = ([latest] if latest else []) + list(row["decisions"])
        if recent[:1] == [PERSON_REQUESTED]:
            return "requested"
        recent = recent[: self._failed_turns]
        if len(recent) == self._failed_turns and all(decision in FAILED_DECISIONS for decision in recent):
            return "three_failures"
        return None

    def _left_message_packet(self, case_id: uuid.UUID, message: str, unanswered: bool = False, asked: bool = False) -> str:
        """The handoff for a left message, with the questions and replies of the turns before it."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT role, body FROM (
                    SELECT id, role, body FROM case_messages
                    WHERE case_id = %s AND role IN ('user', 'assistant')
                    ORDER BY id DESC
                    LIMIT %s
                ) recent
                ORDER BY id
                """,
                (case_id, 2 * self._failed_turns),
            ).fetchall()
        recent = tuple(f"{'Customer' if row['role'] == 'user' else 'Agent'}: {row['body']}" for row in rows)
        if unanswered:
            why = f"The customer asked for a person, and no specialist accepted after {self._offers_before_message} offers."
            return left_message(message, self._tried(case_id), recent, why).text
        if asked:
            return left_message(message, self._tried(case_id), recent, "The customer asked for a person.").text
        return left_message(message, self._tried(case_id), recent).text

    def _chat_messages(self, case_id: uuid.UUID) -> list:
        """The case's messages, plus specialist replies on the customer's other chat cases.

        A customer who wrote again after an escalation is on a new case, and still sees the reply.
        """
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT m.role, m.body, m.decision, m.staff_id, split_part(staff_users.name, ' ', 1) AS name
                FROM case_messages m
                JOIN cases c ON c.id = m.case_id
                JOIN cases this ON this.id = %s
                LEFT JOIN staff_users ON staff_users.id = m.staff_id
                WHERE m.case_id = this.id
                   OR (m.role = 'specialist' AND c.customer_id = this.customer_id AND c.staff_id = this.staff_id)
                ORDER BY m.id
                """,
                (case_id,),
            ).fetchall()

    # Escalations inbox (R38): every escalated case with its handoff, from the desk or the chat.
    # A left message becomes an escalated chat case, so it lands here too.

    def inbox(self, staff_id: uuid.UUID, lead: bool) -> list[dict]:
        """Leads see every item. A specialist sees the items nobody picked up, and their own."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT cases.id, cases.staff_id = %s AS chat, cases.handoff_text, cases.created_at,
                       cases.assigned_to, owner.name AS owner, customers.name AS customer
                FROM cases
                LEFT JOIN staff_users owner ON owner.id = cases.assigned_to
                LEFT JOIN customers ON customers.id = cases.customer_id
                WHERE cases.status = 'Escalated'
                  AND (%s OR cases.assigned_to IS NULL OR cases.assigned_to = %s)
                ORDER BY cases.created_at, cases.id
                """,
                (staff_id_for(CHAT_STAFF_EMAIL), lead, staff_id),
            ).fetchall()
            replies = conn.execute(
                """
                SELECT case_id, body, created_at FROM case_messages
                WHERE role = 'specialist' AND case_id = ANY(%s)
                ORDER BY id
                """,
                ([row["id"] for row in rows],),
            ).fetchall()
        return [
            {
                "case_id": str(row["id"]),
                "source": "chat" if row["chat"] else "desk",
                "customer": row["customer"],
                "handoff": row["handoff_text"],
                "opened_at": _iso(row["created_at"]),
                "assigned_to": row["owner"],
                "mine": row["assigned_to"] == staff_id,
                "replies": [
                    {"text": reply["body"], "created_at": _iso(reply["created_at"])}
                    for reply in replies
                    if reply["case_id"] == row["id"]
                ],
            }
            for row in rows
        ]

    def pick_up(self, staff_id: uuid.UUID, case_id: uuid.UUID) -> None:
        """Assign an escalated case to one specialist. The check is in the update, so only one can win."""
        with self._pool.connection() as conn:
            won = conn.execute(
                """
                UPDATE cases SET assigned_to = %s
                WHERE id = %s AND status = 'Escalated' AND (assigned_to IS NULL OR assigned_to = %s)
                RETURNING id
                """,
                (staff_id, case_id, staff_id),
            ).fetchone()
            conn.commit()
        if won is None:
            row = self._case_row(case_id)
            raise AlreadyPickedUp() if row is not None and row["status"] == "Escalated" else NotInInbox()

    def reply(self, staff_id: uuid.UUID, case_id: uuid.UUID, text: str) -> None:
        """A specialist's reply on a chat case they picked up. It is screened and shown to the customer as written.

        The case stays Escalated, so no agent turn or proposal follows on it (R30).
        """
        with self._pool.connection() as conn:
            saved = conn.execute(
                """
                INSERT INTO case_messages (case_id, role, body, staff_id, created_at)
                SELECT id, 'specialist', %s, %s, %s FROM cases
                WHERE id = %s AND status = 'Escalated' AND assigned_to = %s AND staff_id = %s
                RETURNING id
                """,
                (screen(text.strip()), staff_id, self._clock.now(), case_id, staff_id, staff_id_for(CHAT_STAFF_EMAIL)),
            ).fetchone()
            conn.commit()
        if saved is None:
            raise NotYours()

    # Live chat (issue #138, ADR 0001): the line is rows in live_chat_requests. One function makes offers.

    def set_availability(self, staff_id: uuid.UUID, state: str) -> None:
        """The specialist's own choice. It clears missed offers and the note that they were set to away.

        A specialist's first choice starts their capacity at the chats-per-specialist setting.
        """
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO specialist_availability (staff_id, state, capacity, last_seen) VALUES (%s, %s, %s, %s)
                ON CONFLICT (staff_id) DO UPDATE SET state = EXCLUDED.state, last_seen = EXCLUDED.last_seen,
                    missed_in_a_row = 0, auto_away_at = NULL
                """,
                (staff_id, state, self._chats_per_specialist, self._clock.now()),
            )
            conn.commit()
        if state == "available":
            self._tick()

    def request_live(self, customer_id: uuid.UUID, reason: str = "requested", spanish: bool | None = None) -> bool:
        """Put the customer's chat in the line, unless no specialist is available or the wait is too long.

        Turned away, the customer is offered to leave a message instead (R41). Asking again while a
        request is open changes nothing. True when the chat is in the line or with a specialist.
        """
        case_id = self._writable(customer_id, self._chat_case(customer_id))
        # The timers first, so the line counts the specialists who are still available (issue #139).
        self._tick(offers=False)
        joined = self._join(case_id, customer_id, reason, spanish)
        self._assign()
        return joined

    def _join(self, case_id: uuid.UUID, customer_id: uuid.UUID, reason: str, spanish: bool | None = None) -> bool:
        """Join at the back of the line: escalated requests go behind other escalated ones only (R42), and
        every request goes behind customers back from idle (issue #142).

        A free slot takes the request at once. Otherwise the estimate must be under the cap. With too
        little history there is no number, and the request joins. The language is the customer's latest
        message's, unless `spanish` says it.
        """
        with self._pool.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM live_chat_requests WHERE case_id = %s AND status IN ('waiting', 'offered', 'active', 'idle')",
                (case_id,),
            ).fetchone():
                return True
            ahead = conn.execute(
                """
                SELECT count(*) AS n FROM live_chat_requests
                WHERE status = 'waiting' AND (returned_at IS NOT NULL OR reason = 'escalated' OR %s <> 'escalated')
                """,
                (reason,),
            ).fetchone()["n"]
        slots, free, length = self._line()
        if slots == 0:
            joined = False
        elif free > ahead or length is None:
            joined = True
        else:
            joined = wait_minutes(ahead + 1, length, slots) <= self._longest_wait
        if spanish is None:
            spanish = self._writes_spanish(case_id)
        now = self._clock.now()
        with self._pool.connection() as conn:
            # A turned-away request is kept as 'refused', so the chat offers to leave a message.
            queued = conn.execute(
                """
                INSERT INTO live_chat_requests
                    (id, case_id, customer_id, reason, status, queued_at, customer_seen_at, language, end_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    uuid.uuid4(),
                    case_id,
                    customer_id,
                    reason,
                    "waiting" if joined else "refused",
                    now,
                    now,
                    "es" if spanish else "en",
                    None if joined else "refused",
                ),
            ).fetchone()
            if queued is not None and joined:
                _audit(conn, None, "live_chat_requested", now)
            conn.commit()
        return joined

    def _writes_spanish(self, case_id: uuid.UUID) -> bool:
        """The customer's latest message on the case is in Spanish. Action turns carry a specialist's id, so they do not count."""
        with self._pool.connection() as conn:
            said = conn.execute(
                """
                SELECT body FROM case_messages WHERE case_id = %s AND role = 'user' AND staff_id IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        return said is not None and is_spanish(said["body"])

    def leave_line(self, customer_id: uuid.UUID) -> bool:
        """The customer leaves the line and goes back to the agent. An offer not yet accepted is withdrawn.

        An escalation does not go back to the agent: it goes to the escalations inbox.
        """
        with self._pool.connection() as conn:
            left = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'left', ended_at = %s, end_reason = 'left'
                WHERE case_id = %s AND status IN ('waiting', 'offered')
                RETURNING case_id, reason
                """,
                (self._clock.now(), self._chat_case(customer_id)),
            ).fetchone()
            if left is not None and left["reason"] == "escalated":
                _to_inbox(conn, [left["case_id"]])
            conn.commit()
        if left is None:
            return False
        # A withdrawn offer frees the specialist's slot.
        self._tick()
        return True

    def _line(self) -> tuple[int, int, float | None]:
        """The available specialists' slots, the free ones, and the median live chat length in minutes.

        The median is from accepted to ended over the last days, None with too few live chats (R40).
        """
        since = self._clock.now() - timedelta(days=self._wait_history_days)
        with self._pool.connection() as conn:
            slots = conn.execute(
                f"""
                SELECT coalesce(sum(a.capacity), 0) AS slots, coalesce(sum(greatest(a.capacity - (
                    SELECT count(*) FROM live_chat_requests r
                    WHERE r.staff_id = a.staff_id AND r.status IN {_TAKES_A_SLOT}
                ), 0)), 0) AS free
                FROM specialist_availability a WHERE a.state = 'available' AND a.last_seen >= %s
                """,
                (self._clock.now() - self._check_in_window,),
            ).fetchone()
            history = conn.execute(
                """
                SELECT count(*) AS chats, percentile_cont(0.5) WITHIN GROUP (ORDER BY ended_at - accepted_at) AS length
                FROM live_chat_requests WHERE accepted_at IS NOT NULL AND ended_at >= %s
                """,
                (since,),
            ).fetchone()
        length = history["length"].total_seconds() / 60 if history["chats"] >= self._wait_history_chats else None
        return slots["slots"], slots["free"], length

    def _line_text(self, case_id: uuid.UUID) -> str:
        """The customer's place in the line and the estimated wait as a range (R40), or why they were turned away."""
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT me.status, (
                    SELECT count(*) FROM live_chat_requests o
                    WHERE o.status = 'waiting'
                      AND (o.returned_at IS NULL, o.reason <> 'escalated', o.queued_at, o.id)
                          <= (me.returned_at IS NULL, me.reason <> 'escalated', me.queued_at, me.id)
                ) AS place
                FROM live_chat_requests me
                WHERE me.case_id = %s AND me.status IN ('waiting', 'offered')
                """,
                (case_id,),
            ).fetchone()
        if row is None:
            return LINE_REFUSED_TEXT if self._left_line(case_id) in ("refused", "unanswered") else ""
        if row["status"] == "offered":
            return OFFERED_TEXT
        place = f"You are number {row['place']} in line."
        slots, _, length = self._line()
        if slots == 0:
            return f"{place} No specialist is available right now."
        if length is None:
            return f"{place} The wait is a few minutes."
        low, high = wait_range(wait_minutes(row["place"], length, slots))
        return f"{place} The wait is about {low} minute." if high == 1 else f"{place} The wait is about {low} to {high} minutes."

    def _left_line(self, case_id: uuid.UUID) -> str | None:
        """How this open chat's last live chat request left the line, while it has not joined since.

        'refused' when the line turned it away (R41), 'unanswered' when no specialist accepted its last
        offer (issue #139). Either way the chat offers to leave a message. None with live chat off.
        """
        if not self._live_chat_enabled:
            return None
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.status FROM live_chat_requests r JOIN cases c ON c.id = r.case_id
                WHERE r.case_id = %s AND c.status = 'Open'
                  AND NOT EXISTS (
                      SELECT 1 FROM live_chat_requests o
                      WHERE o.case_id = r.case_id AND o.status IN ('waiting', 'offered', 'active', 'idle')
                  )
                ORDER BY r.queued_at DESC, r.id DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        return None if row is None else row["status"]

    def _sweep(self) -> None:
        """A waiting customer whose chat has not refreshed for a while leaves the line (R41).

        Noticed on read, with no scheduler. SKIP LOCKED, so a sweep never waits on an offer being made.
        An escalation that leaves the line this way goes to the escalations inbox, so it is not lost.
        """
        now = self._clock.now()
        with self._pool.connection() as conn:
            gone = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'abandoned', ended_at = %s, end_reason = 'abandoned'
                WHERE id IN (
                    SELECT id FROM live_chat_requests
                    WHERE status = 'waiting' AND coalesce(customer_seen_at, queued_at) <= %s
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING case_id, reason
                """,
                (now, now - timedelta(minutes=self._line_gone_minutes)),
            ).fetchall()
            _to_inbox(conn, [row["case_id"] for row in gone if row["reason"] == "escalated"])
            conn.commit()

    def _refreshed(self, case_id: uuid.UUID) -> None:
        """The customer's chat refreshed. A customer who left the line by not refreshing rejoins at the back.

        It runs right after a tick, whose sweep has already taken a customer gone too long out of the line.
        """
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE live_chat_requests SET customer_seen_at = %s
                WHERE case_id = %s AND status IN ('waiting', 'offered', 'active')
                """,
                (self._clock.now(), case_id),
            )
            last = conn.execute(
                """
                SELECT r.customer_id, r.reason, r.status FROM live_chat_requests r JOIN cases c ON c.id = r.case_id
                WHERE r.case_id = %s AND c.status IN ('Open', 'Waiting for approval')
                ORDER BY r.queued_at DESC, r.id DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            conn.commit()
        if last is not None and last["status"] == "abandoned":
            self._join(case_id, last["customer_id"], last["reason"])
            self._assign()

    def live_state(self, customer_id: uuid.UUID) -> dict | None:
        """The open request on the customer's chat. The specialist's first name shows once they join."""
        self._tick()
        case_id = self._chat_case(customer_id)
        self._refreshed(case_id)
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.status, split_part(staff_users.name, ' ', 1) AS name
                FROM live_chat_requests r
                LEFT JOIN staff_users ON staff_users.id = r.staff_id
                WHERE r.case_id = %s AND r.status IN ('waiting', 'offered', 'active', 'idle')
                """,
                (case_id,),
            ).fetchone()
        if row is None:
            return None
        return {"status": row["status"], "specialist": row["name"] if row["status"] == "active" else None}

    def live(self, staff_id: uuid.UUID) -> dict:
        """A specialist's state, offers, and live chats. A live chat shows the conversation as the customer sees it.

        An idle live chat is listed with `idle` set: the customer went quiet, so it does not take a slot (R44).
        The desk reads this every few seconds, so a read is also the desk's check-in (issue #139).
        """
        self._check_in(staff_id)
        self._tick()
        with self._pool.connection() as conn:
            state = conn.execute(
                "SELECT state, auto_away_at FROM specialist_availability WHERE staff_id = %s",
                (staff_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT r.id, r.case_id, r.status, r.reason, r.language, customers.name AS customer
                FROM live_chat_requests r
                JOIN customers ON customers.id = r.customer_id
                WHERE r.staff_id = %s AND r.status IN ('offered', 'active', 'idle')
                ORDER BY r.queued_at, r.id
                """,
                (staff_id,),
            ).fetchall()
        return {
            "state": "away" if state is None else state["state"],
            # When missed offers set the specialist to away, until they choose a state themselves.
            "auto_away_at": _iso(state["auto_away_at"]) if state and state["auto_away_at"] else None,
            # Why the customer is in the line (requested or escalated) and their language (user story 27).
            "offers": [
                {"id": str(row["id"]), "customer": row["customer"], "reason": row["reason"], "language": row["language"]}
                for row in rows
                if row["status"] == "offered"
            ],
            "chats": [self._live_chat(row) for row in rows if row["status"] in ("active", "idle")],
        }

    def _live_chat(self, row) -> dict:
        """One live chat for its specialist: the conversation, their action turns, and what the customer's status says.

        Beside it, the customer's orders and the history panel the case desk shows, so the specialist answers
        without searching (user story 32).
        """
        view = self._chat_view(row["case_id"], staff=True)
        said = [m["text"] for m in view["messages"] if m["role"] == "user"]
        return {
            "id": str(row["id"]),
            "case_id": str(row["case_id"]),
            "customer": row["customer"],
            "idle": row["status"] == "idle",
            "messages": view["messages"],
            "status": view["status"],
            # The agent's handoff when its escalation joined the line, else empty (issue #141).
            "handoff": self._case_row(row["case_id"])["handoff_text"],
            # The specialist replies in Spanish themselves. Nothing translates a person's words (R45).
            "spanish": bool(said) and is_spanish(said[-1]),
            "orders": self._orders(row["case_id"]),
            "history": self._history(row["case_id"]),
        }

    def _orders(self, case_id: uuid.UUID) -> list[dict]:
        """The case customer's orders, newest first, with the order summary the waiting list shows."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT orders.id, orders.lines, orders.status, orders.purchased_on, orders.total_cents, orders.refunds
                FROM cases JOIN orders ON orders.customer_id = cases.customer_id
                WHERE cases.id = %s
                ORDER BY orders.purchased_on DESC, orders.id DESC
                """,
                (case_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "summary": f"{row['lines']}. Status: {row['status']}. Total: {row['total_cents']} cents.",
                "purchased_on": row["purchased_on"].isoformat(),
                "refunds": row["refunds"],
            }
            for row in rows
        ]

    def accept(self, staff_id: uuid.UUID, request_id: uuid.UUID) -> None:
        """Take an offer while it stands. It ends a run of missed offers."""
        now = self._clock.now()
        with self._pool.connection() as conn:
            accepted = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'active', accepted_at = %s
                WHERE id = %s AND status = 'offered' AND staff_id = %s AND offer_expires_at > %s
                RETURNING id
                """,
                (now, request_id, staff_id, now),
            ).fetchone()
            if accepted is None:
                raise NotYours()
            conn.execute("UPDATE specialist_availability SET missed_in_a_row = 0 WHERE staff_id = %s", (staff_id,))
            _audit(conn, staff_id, "live_chat_accepted", now)
            conn.commit()

    def decline(self, staff_id: uuid.UUID, request_id: uuid.UUID) -> None:
        """Turn an offer down. The request goes to the next specialist, and never back to this one.

        A decline is not a missed offer: the specialist is at the desk, so it ends a run of missed offers.
        After the last offer, the request leaves the line and the customer may leave a message.
        """
        now = self._clock.now()
        with self._pool.connection() as conn:
            declined = conn.execute(
                """
                UPDATE live_chat_requests
                SET status = CASE WHEN offers >= %(last)s THEN 'unanswered' ELSE 'waiting' END,
                    end_reason = CASE WHEN offers >= %(last)s THEN 'unanswered' END,
                    staff_id = NULL, offer_expires_at = NULL, missed_by = array_append(missed_by, %(staff)s)
                WHERE id = %(request)s AND status = 'offered' AND staff_id = %(staff)s AND offer_expires_at > %(now)s
                RETURNING status, case_id, reason
                """,
                {"last": self._offers_before_message, "staff": staff_id, "request": request_id, "now": now},
            ).fetchone()
            if declined is None:
                raise NotYours()
            conn.execute("UPDATE specialist_availability SET missed_in_a_row = 0 WHERE staff_id = %s", (staff_id,))
            _audit(conn, staff_id, "live_chat_declined", now)
            if declined["status"] == "unanswered":
                _audit(conn, None, "live_chat_unanswered", now)
                if declined["reason"] == "escalated":
                    _to_inbox(conn, [declined["case_id"]])
            conn.commit()
        self._tick()

    def live_message(self, staff_id: uuid.UUID, request_id: uuid.UUID, text: str) -> None:
        """A specialist's message in their own live chat: screened, saved as theirs, and audited (R46)."""
        now = self._clock.now()
        with self._pool.connection() as conn:
            saved = conn.execute(
                """
                INSERT INTO case_messages (case_id, role, body, staff_id, created_at)
                SELECT case_id, 'specialist', %s, %s, %s FROM live_chat_requests
                WHERE id = %s AND status = 'active' AND staff_id = %s
                RETURNING id
                """,
                (screen(text.strip()), staff_id, now, request_id, staff_id),
            ).fetchone()
            if saved is None:
                raise NotYours()
            _audit(conn, staff_id, "live_chat_message", now)
            conn.commit()

    def live_action(self, staff_id: uuid.UUID, request_id: uuid.UUID, text: str) -> None:
        """A refund, cancel, exchange, address change, or warranty claim raised in the specialist's live chat (R45).

        The agent's own turn, run as the specialist: the handbook rule and the amount come from code, the
        duplicate guard and the specialist's request limit apply, and the specialist is the proposer, so only
        a lead approves. The turn is saved as theirs, so the customer sees only that nothing is approved yet.
        """
        self.ask(staff_id, text, case_id=self._own_live_case(staff_id, request_id), staff_turn=True)

    def end_live(self, staff_id: uuid.UUID, request_id: uuid.UUID, status: str, note: str = "") -> None:
        """End a live chat as Resolved, or as Escalated with a handoff, which puts it in the escalations inbox."""
        case_id = self._own_live_case(staff_id, request_id)
        if _waits_for_lead(self._status(case_id)):
            raise ProposalWaiting()
        packet = self._manual_packet(case_id, note) if status == "Escalated" else ""
        now = self._clock.now()
        with self._pool.connection() as conn:
            ended = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'ended', ended_at = %s, end_reason = %s
                WHERE id = %s AND status = 'active' AND staff_id = %s
                RETURNING case_id
                """,
                (now, "escalated" if status == "Escalated" else "resolved", request_id, staff_id),
            ).fetchone()
            if ended is None:
                raise NotYours()
            if status == "Escalated":
                conn.execute(
                    "UPDATE cases SET status = 'Escalated', draft_text = %s, handoff_text = %s WHERE id = %s",
                    (packet, packet, ended["case_id"]),
                )
            else:
                conn.execute("UPDATE cases SET status = 'Resolved' WHERE id = %s", (ended["case_id"],))
            _audit(conn, staff_id, "live_chat_ended", now)
            conn.commit()
        # A slot is free.
        self._tick()

    def _own_live_case(self, staff_id: uuid.UUID, request_id: uuid.UUID) -> uuid.UUID:
        """The case of the specialist's own active live chat. Anyone else's, or one not active, is NotYours."""
        with self._pool.connection() as conn:
            live = conn.execute(
                "SELECT case_id FROM live_chat_requests WHERE id = %s AND status = 'active' AND staff_id = %s",
                (request_id, staff_id),
            ).fetchone()
        if live is None:
            raise NotYours()
        return live["case_id"]

    def _held(self, case_id: uuid.UUID) -> bool:
        """A specialist holds this chat case in a live chat, or held it until the customer went quiet, or the
        agent's escalation waits in the line for one.

        Either way the agent has handed over: an escalated chat takes no agent turn or proposal (R30).
        """
        with self._pool.connection() as conn:
            return (
                conn.execute(
                    """
                    SELECT 1 FROM live_chat_requests
                    WHERE case_id = %s
                      AND (status IN ('active', 'idle') OR (reason = 'escalated' AND status IN ('waiting', 'offered')))
                    """,
                    (case_id,),
                ).fetchone()
                is not None
            )

    # Quiet customers (R44, issue #142). The clock runs from the specialist's last message, and only
    # while the customer has not answered it. Timers apply when a chat, a live view, or the line is
    # read. There is no scheduler.

    def _quiet(self) -> None:
        """Idle the live chats quiet past the idle time, freeing the slot, and close those quiet past the close time.

        A chat whose case waits for a lead is not closed until the lead decides. A customer who wrote during
        idle comes back. Each request row is locked with SKIP LOCKED, so two
        reads at once change it once.
        """
        now = self._clock.now()
        back = []
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT r.id, r.case_id, r.status, r.staff_id, cases.status AS case_status,
                       last.staff_id AS last_by, last.created_at
                FROM live_chat_requests r
                JOIN cases ON cases.id = r.case_id
                CROSS JOIN LATERAL ({_LAST_WORD}) last
                WHERE r.status IN ('active', 'idle')
                  AND ((last.staff_id IS NOT NULL AND last.created_at <= %s) OR (r.status = 'idle' AND last.staff_id IS NULL))
                FOR UPDATE OF r SKIP LOCKED
                """,
                (now - min(self._idle, self._close),),
            ).fetchall()
            for row in rows:
                if row["last_by"] is None:
                    back.append(row)
                elif now - row["created_at"] >= self._close and not _waits_for_lead(row["case_status"]):
                    # Closed like a resolved chat, with the conversation kept. While a proposal waits, the chat
                    # only goes idle, and it closes once the lead has decided.
                    conn.execute(
                        "UPDATE live_chat_requests SET status = 'ended', ended_at = %s, end_reason = 'closed_quiet' WHERE id = %s",
                        (now, row["id"]),
                    )
                    conn.execute("UPDATE cases SET status = 'Resolved' WHERE id = %s AND status = 'Open'", (row["case_id"],))
                    _audit(conn, row["staff_id"], "live_chat_closed", now)
                elif now - row["created_at"] >= self._idle and row["status"] == "active":
                    conn.execute("UPDATE live_chat_requests SET status = 'idle' WHERE id = %s", (row["id"],))
                    _audit(conn, row["staff_id"], "live_chat_idle", now)
            conn.commit()
        for row in back:
            self._come_back(row["id"], row["staff_id"])

    def _come_back(self, request_id: uuid.UUID, staff_id: uuid.UUID) -> None:
        """Back to the same specialist when they are available with a free slot, otherwise to the front of the line."""
        now = self._clock.now()
        with self._pool.connection() as conn:
            # The specialist's row first, as in _offer_next, and the slot counted in a new statement after the lock.
            # Available means the desk checked in recently, as for offers (issue #139).
            available = conn.execute(
                """
                SELECT capacity FROM specialist_availability
                WHERE staff_id = %s AND state = 'available' AND last_seen >= %s
                FOR UPDATE
                """,
                (staff_id, now - self._check_in_window),
            ).fetchone()
            busy = conn.execute(
                f"SELECT count(*) AS n FROM live_chat_requests WHERE staff_id = %s AND status IN {_TAKES_A_SLOT}",
                (staff_id,),
            ).fetchone()["n"]
            if available is not None and busy < available["capacity"]:
                moved = conn.execute(
                    """
                    UPDATE live_chat_requests SET status = 'active', customer_seen_at = %s
                    WHERE id = %s AND status = 'idle'
                    RETURNING id
                    """,
                    (now, request_id),
                ).fetchone()
            else:
                # The customer just wrote, so the line's sweep does not count them as gone. Back in the line,
                # the request starts a new round of offers.
                moved = conn.execute(
                    """
                    UPDATE live_chat_requests
                    SET status = 'waiting', staff_id = NULL, returned_at = %s, customer_seen_at = %s, offers = 0, missed_by = '{}'
                    WHERE id = %s AND status = 'idle'
                    RETURNING id
                    """,
                    (now, now, request_id),
                ).fetchone()
            if moved is not None:
                _audit(conn, staff_id, "live_chat_returned", now)
            conn.commit()

    def _still_there(self, case_id: uuid.UUID) -> bool:
        """The specialist had the last word in this live chat at least the nudge time ago."""
        with self._pool.connection() as conn:
            row = conn.execute(
                f"""
                SELECT 1 FROM live_chat_requests r
                CROSS JOIN LATERAL ({_LAST_WORD}) last
                WHERE r.case_id = %s AND r.status IN ('active', 'idle')
                  AND last.staff_id IS NOT NULL AND last.created_at <= %s
                """,
                (case_id, self._clock.now() - self._nudge),
            ).fetchone()
        return row is not None

    def _tick(self, offers: bool = True) -> None:
        """The line's timers in one fixed order, run on every read and after every change (ADR 0001: no scheduler).

        Waiting customers who stopped refreshing leave the line. Then expired offers move on, which may set a
        specialist to away. Then quiet live chats go idle or close, and customers back from idle return to
        their specialist or the front of the line. Last, unless `offers` is False, free slots get offers.
        Each step locks its rows with SKIP LOCKED, so reads at once apply a timer once. Nothing runs with
        live chat off.
        """
        if not self._live_chat_enabled:
            return
        self._sweep()
        self._expire()
        self._quiet()
        if offers:
            self._assign()

    def _check_in(self, staff_id: uuid.UUID) -> None:
        """The desk checked in, so an available specialist gets offers and counts as a slot (issue #139)."""
        with self._pool.connection() as conn:
            conn.execute("UPDATE specialist_availability SET last_seen = %s WHERE staff_id = %s", (self._clock.now(), staff_id))
            conn.commit()

    def _expire(self) -> None:
        """Offers past their window go back to the line, or leave it after the last offer (issue #139).

        The specialist is not offered that request again, and missed offers in a row set them to away.
        """
        now = self._clock.now()
        with self._pool.connection() as conn:
            expired = conn.execute(
                """
                WITH due AS (
                    SELECT id, staff_id FROM live_chat_requests
                    WHERE status = 'offered' AND offer_expires_at <= %(now)s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE live_chat_requests r
                SET status = CASE WHEN r.offers >= %(last)s THEN 'unanswered' ELSE 'waiting' END,
                    end_reason = CASE WHEN r.offers >= %(last)s THEN 'unanswered' END,
                    staff_id = NULL, offer_expires_at = NULL, missed_by = array_append(r.missed_by, due.staff_id)
                FROM due
                WHERE r.id = due.id
                RETURNING due.staff_id, r.status, r.case_id, r.reason
                """,
                {"now": now, "last": self._offers_before_message},
            ).fetchall()
            for row in expired:
                _audit(conn, row["staff_id"], "live_chat_expired", now)
                if row["status"] == "unanswered":
                    _audit(conn, None, "live_chat_unanswered", now)
            _to_inbox(conn, [row["case_id"] for row in expired if row["status"] == "unanswered" and row["reason"] == "escalated"])
            # One specialist at a time and always in the same order, so two runs never deadlock.
            for staff_id in sorted({row["staff_id"] for row in expired}):
                seen = conn.execute(
                    "SELECT state, missed_in_a_row FROM specialist_availability WHERE staff_id = %s FOR UPDATE",
                    (staff_id,),
                ).fetchone()
                missed = seen["missed_in_a_row"] + sum(row["staff_id"] == staff_id for row in expired)
                if seen["state"] == "available" and missed >= self._missed_before_away:
                    conn.execute(
                        """
                        UPDATE specialist_availability SET state = 'away', missed_in_a_row = %s, auto_away_at = %s
                        WHERE staff_id = %s
                        """,
                        (missed, now, staff_id),
                    )
                    _audit(conn, staff_id, "live_chat_auto_away", now)
                else:
                    conn.execute(
                        "UPDATE specialist_availability SET missed_in_a_row = %s WHERE staff_id = %s",
                        (missed, staff_id),
                    )
            conn.commit()

    def _assign(self) -> None:
        """Make offers until no request waits or no available specialist has a free slot. `_tick` runs the timers first."""
        while self._offer_next():
            pass

    def take_next(self, staff_id: uuid.UUID) -> uuid.UUID:
        """The specialist takes the next request in line now: it is offered to them before anyone else (spec #131).

        The rules and locks of every offer: the line's order, never a request they missed, and only while
        they are available with a free slot. The timers run first, so an offer that expired or a slot that
        freed just now counts. NothingToTake when no request waits for them or they cannot take one.
        """
        self._check_in(staff_id)
        self._tick(offers=False)
        offered = self._offer_next(only=staff_id)
        # The rest of the line, for the other specialists.
        self._assign()
        if offered is None:
            raise NothingToTake()
        return offered

    def _offer_next(self, only: uuid.UUID | None = None) -> uuid.UUID | None:
        """Offer the next waiting request to the available specialist with the most spare capacity, or to `only`.

        The line is escalated requests first, then oldest first (R42). A customer back from idle goes
        ahead of both (issue #142). A tie on spare capacity goes to whoever was offered work longest ago,
        and never offered comes first (spec #131).

        One transaction (ADR 0001). The available specialists' rows are locked first, always in the same
        order, so two runs never deadlock, and a run that waits on them then sees the request, the free
        slot, or the specialist that made it wait. Live chats are counted only under the locks, so two
        offers never both take a specialist's last slot, and the request is claimed with SKIP LOCKED.
        Available means the desk checked in recently, and nobody is offered a request they missed (issue #139).
        Returns the offered request's id, or None when nothing was offered.
        """
        now = self._clock.now()
        with self._pool.connection() as conn:
            locked = conn.execute(
                """
                SELECT staff_id FROM specialist_availability
                WHERE state = 'available' AND last_seen >= %s AND (%s::uuid IS NULL OR staff_id = %s)
                ORDER BY staff_id FOR UPDATE
                """,
                (now - self._check_in_window, only, only),
            ).fetchall()
            if not locked:
                return None
            # A new statement after the locks, so the count includes every offer committed before them.
            free = conn.execute(
                f"""
                SELECT a.staff_id, a.last_offered_at, a.capacity - count(r.id) AS spare FROM specialist_availability a
                LEFT JOIN live_chat_requests r ON r.staff_id = a.staff_id AND r.status IN {_TAKES_A_SLOT}
                WHERE a.staff_id = ANY(%s)
                GROUP BY a.staff_id, a.capacity, a.last_offered_at
                HAVING count(r.id) < a.capacity
                """,
                ([row["staff_id"] for row in locked],),
            ).fetchall()
            if not free:
                return None
            # The next request in line that at least one of them has not missed.
            request = conn.execute(
                """
                SELECT id, missed_by FROM live_chat_requests
                WHERE status = 'waiting' AND NOT missed_by @> %s
                ORDER BY returned_at IS NULL, reason <> 'escalated', queued_at, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                ([row["staff_id"] for row in free],),
            ).fetchone()
            if request is None:
                return None
            chosen = min(
                (row for row in free if row["staff_id"] not in request["missed_by"]),
                key=lambda row: (-row["spare"], row["last_offered_at"] is not None, row["last_offered_at"], row["staff_id"]),
            )
            conn.execute(
                """
                UPDATE live_chat_requests
                SET status = 'offered', staff_id = %s, offered_at = %s, offer_expires_at = %s, offers = offers + 1
                WHERE id = %s
                """,
                (chosen["staff_id"], now, now + self._offer_window, request["id"]),
            )
            conn.execute(
                "UPDATE specialist_availability SET last_offered_at = %s WHERE staff_id = %s",
                (now, chosen["staff_id"]),
            )
            _audit(conn, chosen["staff_id"], "live_chat_offered", now)
            conn.commit()
        return request["id"]

    # The lead's view of the line (R49, issue #144). Read-only: nothing is reassigned from here.

    def line(self) -> dict:
        """Specialists available, the line's length and longest wait, the average chat length, and alerts.

        Available is the rule offers use: Available, with a desk check-in inside the window. The line is
        every request not yet accepted, offered ones included. The average chat length is the median the
        wait estimate uses, None with too few live chats (R40). Timers apply on this read too.

        Two alerts. A request no specialist accepted after the last offer (issue #139), until a person picks
        the customer up: the chat offers to leave a message, or the case waits in the escalations inbox with
        nobody on it (a left message, or an escalation, issue #141). Asking again clears it too. And a live
        chat whose customer has waited more than the quiet specialist time for a reply: the customer had the
        last word, or nothing was said since the specialist accepted. The wait starts at the later of the two.
        """
        self._tick()
        now = self._clock.now()
        _, _, chat_minutes = self._line()
        with self._pool.connection() as conn:
            available = conn.execute(
                "SELECT count(*) AS n FROM specialist_availability WHERE state = 'available' AND last_seen >= %s",
                (now - self._check_in_window,),
            ).fetchone()["n"]
            waiting = conn.execute(
                """
                SELECT count(*) AS n, min(coalesce(returned_at, queued_at)) AS since
                FROM live_chat_requests WHERE status IN ('waiting', 'offered')
                """
            ).fetchone()
            unanswered = conn.execute(
                """
                SELECT r.case_id, r.offers, customers.name AS customer, c.status = 'Escalated' AS inbox
                FROM live_chat_requests r
                JOIN cases c ON c.id = r.case_id
                JOIN customers ON customers.id = r.customer_id
                WHERE r.status = 'unanswered'
                  AND (c.status = 'Open' OR (c.status = 'Escalated' AND c.assigned_to IS NULL))
                  AND NOT EXISTS (
                      SELECT 1 FROM live_chat_requests o
                      WHERE o.case_id = r.case_id AND (o.queued_at, o.id) > (r.queued_at, r.id)
                  )
                ORDER BY r.queued_at, r.id
                """
            ).fetchall()
            # Action turns carry the specialist's id, so they count as the specialist's word (issue #143).
            no_reply = conn.execute(
                f"""
                SELECT r.case_id, customers.name AS customer, split_part(staff_users.name, ' ', 1) AS specialist,
                       greatest(last.created_at, r.accepted_at) AS since
                FROM live_chat_requests r
                JOIN customers ON customers.id = r.customer_id
                JOIN staff_users ON staff_users.id = r.staff_id
                LEFT JOIN LATERAL ({_LAST_WORD}) last ON true
                WHERE r.status = 'active' AND last.staff_id IS NULL
                  AND greatest(last.created_at, r.accepted_at) < %s
                ORDER BY since, r.queued_at, r.id
                """,
                (now - self._quiet_specialist,),
            ).fetchall()
        return {
            "available": available,
            "line_length": waiting["n"],
            "longest_wait_seconds": None if waiting["since"] is None else int((now - waiting["since"]).total_seconds()),
            "average_chat_minutes": None if chat_minutes is None else round(chat_minutes, 1),
            "alerts": [
                {
                    "kind": "unanswered",
                    "case_id": str(row["case_id"]),
                    "customer": row["customer"],
                    "offers": row["offers"],
                    "inbox": row["inbox"],
                }
                for row in unanswered
            ]
            + [
                {
                    "kind": "no_reply",
                    "case_id": str(row["case_id"]),
                    "customer": row["customer"],
                    "specialist": row["specialist"],
                    "waiting_seconds": int((now - row["since"]).total_seconds()),
                }
                for row in no_reply
            ],
        }

    def _resume(self, case_id: uuid.UUID, decision: str) -> None:
        resume_turn(graph_for(self._pool.conninfo), str(case_id), decision)

    def _support_draft(self, case_id: uuid.UUID, limit_key: str, question: str, now: datetime) -> Draft:
        order_id = _order_id(question)
        if order_id or (self._customer(case_id) is None and _asks_for_an_order(question)):
            if self._customer(case_id) is None:
                return _plain("unbound", UNBOUND_ORDER_TEXT)
            if order_id:
                return self._order_draft(case_id, order_id, question)
        catalog = self._catalog_draft(question)
        if catalog is not None:
            return catalog
        if not self._take(now.date(), "tokens", TOKENS_PER_TURN, {limit_key: self._token_budget}):
            return _plain("quota", QUOTA_TEXT)
        return handbook_reply(question)

    def _gated_draft(
        self, case_id: uuid.UUID, staff_id: uuid.UUID, question: str, now: datetime, note: str = "", chat_order: str | None = None
    ) -> Draft:
        """Any request that waits for a lead. The handbook rule for each action lives in northstar.actions.

        In a customer chat, the order the chat was started with stands in when the request names none.
        """
        action = gated(question)
        if action is None:
            return _plain("ask_clarification", "Which action and which order id? Nothing is proposed.")
        order_id = _order_id(question) or chat_order
        if order_id is None:
            return _plain("ask_clarification", action.missing_order)
        if self._customer(case_id) is None:
            return _plain("unbound", UNBOUND_ORDER_TEXT)
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT orders.id, orders.status, orders.purchased_on, orders.delivered_on,
                       orders.shipped_on, orders.category, orders.lines, orders.refunds,
                       orders.total_cents,
                       orders.customer_id = cases.customer_id AS owned
                FROM cases
                LEFT JOIN orders ON orders.id = %s
                WHERE cases.id = %s
                """,
                (order_id, case_id),
            ).fetchone()
        if row is None or row["id"] is None or row["total_cents"] is None:
            return _plain("unknown", "That order id is unknown.")
        if not row["owned"]:
            return _plain("not_found", "Not found for this customer.")
        item = row["lines"].split(",")[0].strip()
        catalog = self._catalog_row(item)
        order = Order(
            id=row["id"],
            status=row["status"],
            purchased_on=row["purchased_on"],
            delivered_on=row["delivered_on"],
            category=row["category"],
            lines=row["lines"],
            refunds=row["refunds"],
            total_cents=row["total_cents"],
            shipped_on=row["shipped_on"],
            ticket_actions=self._ticket_actions(order_id),
            item_sizes=tuple(size.strip().upper() for size in catalog["sizes"].split(",")) if catalog else (),
            item_in_stock=catalog["in_stock"] if catalog else None,
            item_final_sale=catalog["final_sale"] if catalog else None,
        )
        planned = action.rule(question, order, now.date())
        if isinstance(planned, Reply):
            match = {section_id: "strong" for section_id in planned.citations}
            return Draft(planned.decision, planned.text, planned.citations, match, ())
        existing = self._existing(case_id, order_id, planned.action)
        if existing is not None:
            return _plain("duplicate", existing)
        if note:
            planned = replace(planned, details=" ".join(part for part in (planned.details, note) if part))
        return self._propose(case_id, staff_id, order_id, planned, now)

    def _existing(self, case_id: uuid.UUID, order_id: str, decision: str) -> str | None:
        """An open or completed ticket, or a proposal waiting elsewhere, for this order and action family (R15)."""
        family = FAMILIES[decision]
        decisions = family_decisions(decision)
        with self._pool.connection() as conn:
            ticket = conn.execute(
                "SELECT id FROM tickets WHERE order_id = %s AND action = ANY(%s) LIMIT 1",
                (order_id, decisions),
            ).fetchone()
            waiting = conn.execute(
                """
                SELECT id FROM cases
                WHERE status = 'Waiting for approval' AND proposal_order_id = %s
                  AND proposal_action = ANY(%s) AND id <> %s
                LIMIT 1
                """,
                (order_id, decisions, case_id),
            ).fetchone()
        if ticket is not None:
            return f"Order {order_id} already has a {family} ticket: {ticket['id']}. No new proposal was made."
        if waiting is not None:
            return f"Order {order_id} already has a {family} proposal waiting for a lead on case {waiting['id']}. No new proposal was made."
        return None

    def _propose(
        self,
        case_id: uuid.UUID,
        staff_id: uuid.UUID,
        order_id: str,
        proposal: Proposal,
        now: datetime,
    ) -> Draft:
        checked = guard_draft(Draft(proposal.action, proposal.text, proposal.citations, {}, ()))
        if checked.decision != proposal.action:
            return checked
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE cases
                SET status = 'Waiting for approval',
                    proposal_id = %s,
                    proposal_action = %s,
                    proposal_amount_cents = %s,
                    proposed_amount_cents = %s,
                    proposal_citations = %s,
                    proposal_details = %s,
                    proposed_by = %s,
                    proposal_order_id = %s,
                    proposed_at = %s,
                    rejection_reason = NULL
                WHERE id = %s
                """,
                (
                    uuid.uuid4(),
                    proposal.action,
                    proposal.amount_cents,
                    proposal.amount_cents,
                    list(proposal.citations),
                    proposal.details,
                    staff_id,
                    order_id,
                    now,
                    case_id,
                ),
            )
            conn.commit()
        match = {section_id: "strong" for section_id in proposal.citations}
        return Draft(proposal.action, proposal.text, proposal.citations, match, ())

    def _catalog_draft(self, question: str) -> Draft | None:
        lowered = question.lower()
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT name, category, price_cents, sizes, in_stock, final_sale FROM catalog_items"
            ).fetchall()
        named = [row for row in rows if row["name"].lower() in lowered]
        if named and any(word in lowered for word in _MISSING_FIELDS):
            return _plain("abstain", "The catalog row does not have that field.")
        if named:
            return _plain("catalog", "\n".join(_catalog_line(row) for row in named))
        if any(phrase in lowered for phrase in _CATALOG_PHRASES):
            # "How much is standard shipping?" names no item. A handbook section answers it.
            if retrieved_answer(question).decision == "answer":
                return None
            return _plain("abstain", "I don't have that item in the catalog.")
        return None

    def _take(self, day, column: str, amount: int, limits: dict[str, int]) -> bool:
        """Add amount under every limit, or under none. False when any limit would be passed.

        One statement per key: the row lock makes concurrent requests count exactly.
        """
        if any(amount > limit for limit in limits.values()):
            return False
        counted = sql.SQL(
            """
            INSERT INTO daily_limits (limit_key, day, {column}) VALUES (%s, %s, %s)
            ON CONFLICT (limit_key, day)
            DO UPDATE SET {column} = daily_limits.{column} + EXCLUDED.{column}
            WHERE daily_limits.{column} + EXCLUDED.{column} <= %s
            RETURNING limit_key
            """
        ).format(column=sql.Identifier(column))
        with self._pool.connection() as conn:
            for key, limit in limits.items():
                if conn.execute(counted, (key, day, amount, limit)).fetchone() is None:
                    conn.rollback()
                    return False
            conn.commit()
        return True

    def _open(self, staff_id: uuid.UUID) -> uuid.UUID:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM cases
                WHERE staff_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (staff_id,),
            ).fetchone()
            if row is not None:
                return row["id"]
            case_id = uuid.uuid4()
            conn.execute(
                "INSERT INTO cases (id, staff_id, created_at) VALUES (%s, %s, %s)",
                (case_id, staff_id, self._clock.now()),
            )
            conn.commit()
        return case_id

    def _messages(self, case_id: uuid.UUID) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT role, body, decision, citations, strengths, steps, created_at
                FROM case_messages
                WHERE case_id = %s
                ORDER BY id
                """,
                (case_id,),
            ).fetchall()
        return [_message(row) for row in rows]


def _message(row) -> dict:
    citations = list(row["citations"] or [])
    strengths = list(row["strengths"] or [])
    return {
        "role": row["role"],
        "body": row["body"],
        "decision": row["decision"],
        "citations": citations,
        "match": {
            section_id: strength
            for section_id, strength in zip(citations, strengths, strict=False)
        },
        "steps": list(row["steps"] or []),
        "created_at": _iso(row["created_at"]),
    }


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def wait_minutes(place: int, chat_minutes: float, slots: int) -> float:
    """Place × average chat length ÷ available slots (R40). Place 1 is next.

    With every slot busy, place p waits for p chat endings at the combined rate of all slots: the
    M/M/c result for a first-come-first-served line, so an estimate.
    """
    return place * chat_minutes / slots


def wait_range(minutes: float) -> tuple[int, int]:
    """The estimate shown as a range of whole minutes, about 0.7x to 1.5x."""
    low, high = WAIT_RANGE
    return max(1, round(minutes * low)), max(1, round(minutes * high))


def _to_inbox(conn, case_ids: list) -> None:
    """Escalated chats that left the line without a specialist go to the escalations inbox with their handoff (issue #141)."""
    if case_ids:
        conn.execute(
            "UPDATE cases SET status = 'Escalated', draft_text = handoff_text WHERE id = ANY(%s) AND status = 'Open'",
            (case_ids,),
        )


def _audit(conn, staff_id: uuid.UUID | None, event: str, at: datetime) -> None:
    """An audit event in the caller's transaction, so it is recorded only with the change it describes."""
    conn.execute("INSERT INTO audit_log (staff_id, event, created_at) VALUES (%s, %s, %s)", (staff_id, event, at))


def _waits_for_lead(case_status: str) -> bool:
    """As on the desk, a case waiting for a lead does not close. The lead decides first (R45)."""
    return case_status == "Waiting for approval"


def _plain(decision: str, text: str) -> Draft:
    return Draft(decision, text, (), {}, ())


_CHAT_TEXT = {
    "proposal": "Thanks. A person on our team will review this request. Nothing is approved yet.",
    "escalate": "A specialist will follow up with you about this.",
    "duplicate": "This request is already with our team.",
    "left_message": "Your message is with our team. A specialist will reply in this chat.",
}
# The same fixed texts for a customer who wrote in Spanish (issue #81).
_CHAT_TEXT_ES = {
    "proposal": "Gracias. Una persona de nuestro equipo revisará esta solicitud. Todavía no hay nada aprobado.",
    "escalate": "Un especialista se pondrá en contacto con usted sobre esto.",
    "duplicate": "Esta solicitud ya está con nuestro equipo.",
    "left_message": "Su mensaje está con nuestro equipo. Un especialista responderá en este chat.",
}


def _for_customer(decision: str | None, body: str, spanish: bool = False) -> str:
    """The checked reply a customer sees. A proposal or a handoff packet is never shown as is."""
    key = "proposal" if decision in PROPOSALS else (decision or "")
    return (_CHAT_TEXT_ES if spanish else _CHAT_TEXT).get(key, body)


def _noted(draft: Draft, note: str) -> Draft:
    """The photo line under the draft, for the specialist and the lead."""
    return replace(draft, text=f"{draft.text}\n{note}") if note else draft


_CUSTOMERS = (
    ("Mira Shah", "mira.shah@northstar.example", "5125550142"),
    ("Jon Hale", "jon.hale@northstar.example", "5125550198"),
)


# id, customer, status, purchased, lines, refunds, total cents, delivered, category, shipped.
# Statuses follow the handbook: placed, packed, shipped, delivered.
_ORDERS = (
    ("NS-1001", "mira.shah@northstar.example", "delivered", "2026-09-01", "Wool coat, size M", "none", 12800, "2026-09-20", "apparel and footwear", "2026-09-02"),
    ("NS-1002", "jon.hale@northstar.example", "shipped", "2026-09-12", "Canvas tote", "none", 4800, "2026-09-12", "bags and accessories", "2026-09-12"),
    ("NS-1003", "mira.shah@northstar.example", "delivered", "2026-09-01", "Wool scarf", "refunded", 2000, "2026-09-20", "apparel and footwear", "2026-09-02"),
    ("NS-1004", "mira.shah@northstar.example", "placed", "2026-10-06", "Enamel kettle", "none", 6400, None, "home and kitchen", None),
    ("NS-1005", "mira.shah@northstar.example", "packed", "2026-10-05", "Canvas tote", "none", 4800, None, "bags and accessories", None),
    ("NS-1006", "mira.shah@northstar.example", "delivered", "2026-09-27", "Rain jacket, size S", "none", 9600, "2026-10-01", "apparel and footwear", "2026-09-28"),
    ("NS-1007", "mira.shah@northstar.example", "delivered", "2026-07-28", "Desk speaker", "none", 8900, "2026-08-01", "small electronics", "2026-07-29"),
    ("NS-1008", "mira.shah@northstar.example", "delivered", "2026-02-25", "Linen shirt, size M", "none", 5400, "2026-03-01", "apparel and footwear", "2026-02-26"),
    ("NS-1009", "mira.shah@northstar.example", "shipped", "2026-09-15", "Canvas tote", "none", 4800, None, "bags and accessories", "2026-09-16"),
    ("NS-1010", "mira.shah@northstar.example", "shipped", "2026-10-04", "Linen shirt, size L", "none", 5400, None, "apparel and footwear", "2026-10-05"),
    # Delivered six days before the tests' clock: inside the REF-DAMAGED 14-day window (issue #80).
    ("NS-1011", "mira.shah@northstar.example", "delivered", "2026-09-26", "Desk lamp", "none", 4200, "2026-09-30", "home and kitchen", "2026-09-27"),
)


_CATALOG = (
    ("Wool coat", "apparel and footwear", 12800, "S, M, L", True, False),
    ("Canvas tote", "bags and accessories", 4800, "one size", True, False),
    ("Trail earbuds", "small electronics", 7900, "one size", False, True),
    ("Rain jacket", "apparel and footwear", 9600, "S, M, L", False, False),
    ("Desk speaker", "small electronics", 8900, "one size", True, False),
    ("Linen shirt", "apparel and footwear", 5400, "S, M, L", True, False),
)
_MISSING_FIELDS = ("material", "review", "rating", "weight", "fabric", "color")
_CATALOG_PHRASES = ("in stock", "how much", "price", "final sale", "what size", "do you sell", "do you carry", "do you stock", "do you have")


def _catalog_line(row) -> str:
    stock = "yes" if row["in_stock"] else "no"
    final_sale = "yes" if row["final_sale"] else "no"
    return (
        f"{row['name']}. Category: {row['category']}. "
        f"Price: ${row['price_cents'] / 100:.2f}. Sizes: {row['sizes']}. "
        f"In stock: {stock}. Final sale: {final_sale}."
    )


def _is_stale(proposed_at: datetime | None, now: datetime) -> bool:
    if proposed_at is None:
        return False
    return (now - proposed_at).total_seconds() > 24 * 60 * 60


def _asks_for_an_order(question: str) -> bool:
    """A particular order ("my order", "order 1001"), not a policy question that says "the order"."""
    return _ONE_ORDER.search(question) is not None


_ONE_ORDER = re.compile(r"\b(my|our|your|his|her|their|this|that)\s+orders?\b|\borders?\s*(#|no\.?|number)?\s*\d", re.IGNORECASE)


def _blocked(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in _BLOCKED)
