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
from northstar.escalate import handoff, left_message, manual_handoff
from northstar.graph import TurnTools, resume_turn, run_turn
from northstar.identity.seed import CHAT_STAFF_EMAIL
from northstar.identity.service import staff_id_for
from northstar.language import is_spanish, to_english, to_spanish
from northstar.memory import graph_for
from northstar.photo import describe
from northstar.agent_model import handbook_reply, turn_deadline
from northstar.handbook import ABSTAIN_TEXT, Draft, guard_draft
from northstar import online
from northstar.online import record_edit, record_judge
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
# Turns that did not help the customer. Enough of them in a row and the chat offers a person (R35).
FAILED_DECISIONS = ("ask_clarification", "abstain", "lookup_failed")
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
-- The customer's last chat refresh while in the line (issue #140).
ALTER TABLE live_chat_requests ADD COLUMN IF NOT EXISTS customer_seen_at timestamptz;
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


class NoOffer(Exception):
    """The chat is not offering to leave a message: the agent's last turns helped, or the case is not open."""


class ProposalWaiting(Exception):
    """A live chat does not end while its case waits for a lead. Ending it would drop the proposal (R45)."""


class CaseStore:
    def __init__(
        self,
        pool,
        clock: Clock,
        request_limit: int = 60,
        token_budget: int = 20_000,
        chat_turns_per_customer: int = 10,
        chat_turns_per_day: int = 500,
        turn_seconds: float = 45,
        failed_turns_before_offer: int = 3,
        live_chats: bool = False,
        line_gone_minutes: float = 2,
        longest_wait_minutes: float = 20,
        wait_history_days: int = 7,
        wait_history_chats: int = 5,
    ) -> None:
        self._pool = pool
        self._clock = clock
        self._request_limit = request_limit
        self._token_budget = token_budget
        self._chat_turns_per_customer = chat_turns_per_customer
        self._chat_turns_per_day = chat_turns_per_day
        self._turn_seconds = turn_seconds
        self._failed_turns = failed_turns_before_offer
        self._live_chats = live_chats
        self._line_gone_minutes = line_gone_minutes
        self._longest_wait = longest_wait_minutes
        self._wait_history_days = wait_history_days
        self._wait_history_chats = wait_history_chats

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
    ) -> dict:
        # Each turn has a deadline. Optional model steps are skipped when it is close (R36).
        with turn_deadline(self._clock, self._turn_seconds):
            return self._ask(staff_id, question, photo, case_id, chat_customer, staff_id if staff_turn else None)

    def _ask(
        self,
        staff_id: uuid.UUID,
        question: str,
        photo: str | None,
        case_id: uuid.UUID | None,
        chat_customer: uuid.UUID | None,
        by: uuid.UUID | None = None,
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
        escalated = handoff(asked, self._tried(case_id))
        if escalated is not None:
            section, text = escalated.section, escalated.text
            self._mark_escalated(case_id, text)
            # Through the graph, so the escalation has a LangGraph trace for the safety rule and the judge.
            fixed = Draft("escalate", text, (section,), {section: "strong"}, ())
            tools = TurnTools(refund=lambda _text: fixed, support=lambda _text: fixed)
            return self._save(case_id, asked_with, reply(_noted(self._turn(case_id, asked, tools), note)), now, by)
        if _blocked(question) or _blocked(asked):
            return self._save(case_id, asked_with, reply(_plain("safe", SAFE_REPLY)), now, by)
        tools = TurnTools(
            refund=lambda text: self._gated_draft(case_id, staff_id, text, now, note),
            support=lambda text: self._support_draft(case_id, key, text, now),
        )
        return self._save(case_id, asked_with, reply(_noted(self._turn(case_id, asked, tools), note)), now, by)

    def _turn(self, case_id: uuid.UUID, question: str, tools: TurnTools) -> Draft:
        return run_turn(question, tools, graph=graph_for(self._pool.conninfo), thread_id=str(case_id))

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
        if self._live_chats:
            self._refreshed(case_id)
        return self._chat_view(case_id)

    def chat_ask(self, customer_id: uuid.UUID, question: str) -> dict:
        case_id = self._chat_case(customer_id)
        if self._live_chats and self._held(case_id):
            # A specialist holds this chat. The agent is quiet: no model call, no limit or budget charge (R46).
            with self._pool.connection() as conn:
                conn.execute(
                    "INSERT INTO case_messages (case_id, role, body, created_at) VALUES (%s, 'user', %s, %s)",
                    (case_id, screen(question.strip()), self._clock.now()),
                )
                conn.commit()
            return self._chat_view(case_id)
        case_id = self._writable(customer_id, case_id)
        # Limits are per customer, so one customer cannot use up the chat for everyone.
        self.ask(staff_id_for(CHAT_STAFF_EMAIL), question, case_id=case_id, chat_customer=customer_id)
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
        elif ticket:
            status = f"Our team approved your request. Reference {ticket}."
        elif row["rejection_reason"]:
            status = "Our team could not approve that request."
        elif row["status"] == "Resolved":
            status = "This chat is closed. Write again to start a new one."
        else:
            status = ""
        if self._live_chats and row["status"] == "Open":
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

    def chat_offer(self, customer_id: uuid.UUID) -> str | None:
        """What the chat offers beside the agent: "leave_message" after failed turns in a row (R35), or
        when the line turned the customer away (R41). Else None."""
        return "leave_message" if self._offers_message(self._chat_case(customer_id)) else None

    def _offers_message(self, case_id: uuid.UUID) -> bool:
        return self._failing(case_id) or (self._live_chats and self._refused(case_id))

    def leave_message(self, customer_id: uuid.UUID, text: str) -> dict:
        """The customer's message for a specialist, while the offer stands.

        The chat case becomes Escalated with a handoff that stands alone, so it lands in the
        escalations inbox. The specialist's reply reaches this chat through the inbox (R38).
        """
        case_id = self._chat_case(customer_id)
        if not self._offers_message(case_id):
            raise NoOffer()
        message = screen(text.strip())
        packet = self._left_message_packet(case_id, message)
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
                raise NoOffer()
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

    def _failing(self, case_id: uuid.UUID) -> bool:
        """The case is open and its last agent turns all failed. One turn that helped resets the count.

        Not while the case is in the line or in a live chat: a person is already on the way (issue #138).
        """
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT m.decision FROM case_messages m JOIN cases c ON c.id = m.case_id
                WHERE m.case_id = %s AND m.role = 'assistant' AND c.status = 'Open'
                  AND NOT EXISTS (
                      SELECT 1 FROM live_chat_requests r
                      WHERE r.case_id = c.id AND r.status IN ('waiting', 'offered', 'active')
                  )
                ORDER BY m.id DESC
                LIMIT %s
                """,
                (case_id, self._failed_turns),
            ).fetchall()
        return len(rows) == self._failed_turns and all(row["decision"] in FAILED_DECISIONS for row in rows)

    def _left_message_packet(self, case_id: uuid.UUID, message: str) -> str:
        """The handoff for a left message, with the questions and replies of the turns that failed."""
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
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO specialist_availability (staff_id, state, last_seen) VALUES (%s, %s, %s)
                ON CONFLICT (staff_id) DO UPDATE SET state = EXCLUDED.state, last_seen = EXCLUDED.last_seen
                """,
                (staff_id, state, self._clock.now()),
            )
            conn.commit()
        if state == "available":
            self._assign()

    def request_live(self, customer_id: uuid.UUID, reason: str = "requested") -> bool:
        """Put the customer's chat in the line, unless no specialist is available or the wait is too long.

        Turned away, the customer is offered to leave a message instead (R41). Asking again while a
        request is open changes nothing. True when the chat is in the line or with a specialist.
        """
        case_id = self._writable(customer_id, self._chat_case(customer_id))
        self._sweep()
        joined = self._join(case_id, customer_id, reason)
        self._assign()
        return joined

    def _join(self, case_id: uuid.UUID, customer_id: uuid.UUID, reason: str) -> bool:
        """Join at the back of the line: escalated requests go behind other escalated ones only (R42).

        A free slot takes the request at once. Otherwise the estimate must be under the cap. With too
        little history there is no number, and the request joins.
        """
        with self._pool.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM live_chat_requests WHERE case_id = %s AND status IN ('waiting', 'offered', 'active')",
                (case_id,),
            ).fetchone():
                return True
            ahead = conn.execute(
                """
                SELECT count(*) AS n FROM live_chat_requests
                WHERE status = 'waiting' AND (reason = 'escalated' OR %s <> 'escalated')
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
        now = self._clock.now()
        with self._pool.connection() as conn:
            # A turned-away request is kept as 'refused', so the chat offers to leave a message.
            queued = conn.execute(
                """
                INSERT INTO live_chat_requests (id, case_id, customer_id, reason, status, queued_at, customer_seen_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (uuid.uuid4(), case_id, customer_id, reason, "waiting" if joined else "refused", now, now),
            ).fetchone()
            if queued is not None and joined:
                _audit(conn, None, "live_chat_requested", now)
            conn.commit()
        return joined

    def leave_line(self, customer_id: uuid.UUID) -> bool:
        """The customer leaves the line and goes back to the agent. An offer not yet accepted is withdrawn."""
        with self._pool.connection() as conn:
            left = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'left', ended_at = %s
                WHERE case_id = %s AND status IN ('waiting', 'offered')
                RETURNING id
                """,
                (self._clock.now(), self._chat_case(customer_id)),
            ).fetchone()
            conn.commit()
        if left is None:
            return False
        # A withdrawn offer frees the specialist's slot.
        self._assign()
        return True

    def _line(self) -> tuple[int, int, float | None]:
        """The available specialists' slots, the free ones, and the median live chat length in minutes.

        The median is from accepted to ended over the last days, None with too few live chats (R40).
        """
        since = self._clock.now() - timedelta(days=self._wait_history_days)
        with self._pool.connection() as conn:
            slots = conn.execute(
                """
                SELECT coalesce(sum(a.capacity), 0) AS slots, coalesce(sum(greatest(a.capacity - (
                    SELECT count(*) FROM live_chat_requests r
                    WHERE r.staff_id = a.staff_id AND r.status IN ('offered', 'active')
                ), 0)), 0) AS free
                FROM specialist_availability a WHERE a.state = 'available'
                """
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
                      AND (o.reason <> 'escalated', o.queued_at, o.id) <= (me.reason <> 'escalated', me.queued_at, me.id)
                ) AS place
                FROM live_chat_requests me
                WHERE me.case_id = %s AND me.status IN ('waiting', 'offered')
                """,
                (case_id,),
            ).fetchone()
        if row is None:
            return LINE_REFUSED_TEXT if self._refused(case_id) else ""
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

    def _refused(self, case_id: uuid.UUID) -> bool:
        """The line turned this open chat away last, and it has not joined since."""
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.status FROM live_chat_requests r JOIN cases c ON c.id = r.case_id
                WHERE r.case_id = %s AND c.status = 'Open'
                  AND NOT EXISTS (
                      SELECT 1 FROM live_chat_requests o
                      WHERE o.case_id = r.case_id AND o.status IN ('waiting', 'offered', 'active')
                  )
                ORDER BY r.queued_at DESC, r.id DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        return row is not None and row["status"] == "refused"

    def _sweep(self) -> None:
        """A waiting customer whose chat has not refreshed for a while leaves the line (R41).

        Noticed on read, with no scheduler. SKIP LOCKED, so a sweep never waits on an offer being made.
        """
        now = self._clock.now()
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE live_chat_requests SET status = 'abandoned', ended_at = %s
                WHERE id IN (
                    SELECT id FROM live_chat_requests
                    WHERE status = 'waiting' AND coalesce(customer_seen_at, queued_at) <= %s
                    FOR UPDATE SKIP LOCKED
                )
                """,
                (now, now - timedelta(minutes=self._line_gone_minutes)),
            )
            conn.commit()

    def _refreshed(self, case_id: uuid.UUID) -> None:
        """The customer's chat refreshed. A customer who left the line by not refreshing rejoins at the back."""
        self._sweep()
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
        case_id = self._chat_case(customer_id)
        self._refreshed(case_id)
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.status, split_part(staff_users.name, ' ', 1) AS name
                FROM live_chat_requests r
                LEFT JOIN staff_users ON staff_users.id = r.staff_id
                WHERE r.case_id = %s AND r.status IN ('waiting', 'offered', 'active')
                """,
                (case_id,),
            ).fetchone()
        if row is None:
            return None
        return {"status": row["status"], "specialist": row["name"] if row["status"] == "active" else None}

    def live(self, staff_id: uuid.UUID) -> dict:
        """A specialist's state, offers, and live chats. A live chat shows the conversation as the customer sees it."""
        with self._pool.connection() as conn:
            state = conn.execute(
                "SELECT state FROM specialist_availability WHERE staff_id = %s",
                (staff_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT r.id, r.case_id, r.status, customers.name AS customer
                FROM live_chat_requests r
                JOIN customers ON customers.id = r.customer_id
                WHERE r.staff_id = %s AND r.status IN ('offered', 'active')
                ORDER BY r.queued_at, r.id
                """,
                (staff_id,),
            ).fetchall()
        return {
            "state": "away" if state is None else state["state"],
            "offers": [
                {"id": str(row["id"]), "customer": row["customer"]} for row in rows if row["status"] == "offered"
            ],
            "chats": [self._live_chat(row) for row in rows if row["status"] == "active"],
        }

    def _live_chat(self, row) -> dict:
        """One live chat for its specialist: the conversation, their action turns, and what the customer's status says."""
        view = self._chat_view(row["case_id"], staff=True)
        said = [m["text"] for m in view["messages"] if m["role"] == "user"]
        return {
            "id": str(row["id"]),
            "case_id": str(row["case_id"]),
            "customer": row["customer"],
            "messages": view["messages"],
            "status": view["status"],
            # The specialist replies in Spanish themselves. Nothing translates a person's words (R45).
            "spanish": bool(said) and is_spanish(said[-1]),
        }

    def accept(self, staff_id: uuid.UUID, request_id: uuid.UUID) -> None:
        now = self._clock.now()
        with self._pool.connection() as conn:
            accepted = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'active', accepted_at = %s
                WHERE id = %s AND status = 'offered' AND staff_id = %s
                RETURNING id
                """,
                (now, request_id, staff_id),
            ).fetchone()
            if accepted is None:
                raise NotYours()
            _audit(conn, staff_id, "live_chat_accepted", now)
            conn.commit()

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
        with self._pool.connection() as conn:
            live = conn.execute(
                "SELECT case_id FROM live_chat_requests WHERE id = %s AND status = 'active' AND staff_id = %s",
                (request_id, staff_id),
            ).fetchone()
        if live is None:
            raise NotYours()
        self.ask(staff_id, text, case_id=live["case_id"], staff_turn=True)

    def end_live(self, staff_id: uuid.UUID, request_id: uuid.UUID, status: str, note: str = "") -> None:
        """End a live chat as Resolved, or as Escalated with a handoff, which puts it in the escalations inbox."""
        with self._pool.connection() as conn:
            live = conn.execute(
                "SELECT case_id FROM live_chat_requests WHERE id = %s AND status = 'active' AND staff_id = %s",
                (request_id, staff_id),
            ).fetchone()
        if live is None:
            raise NotYours()
        if self._status(live["case_id"]) == "Waiting for approval":
            # As on the desk, a case waiting for a lead does not close. The lead decides first.
            raise ProposalWaiting()
        packet = self._manual_packet(live["case_id"], note) if status == "Escalated" else ""
        now = self._clock.now()
        with self._pool.connection() as conn:
            ended = conn.execute(
                """
                UPDATE live_chat_requests SET status = 'ended', ended_at = %s
                WHERE id = %s AND status = 'active' AND staff_id = %s
                RETURNING case_id
                """,
                (now, request_id, staff_id),
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
        self._assign()

    def _held(self, case_id: uuid.UUID) -> bool:
        """A specialist holds this chat case in a live chat."""
        with self._pool.connection() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM live_chat_requests WHERE case_id = %s AND status = 'active'",
                    (case_id,),
                ).fetchone()
                is not None
            )

    def _assign(self) -> None:
        """Make offers until no request waits or no available specialist has a free slot."""
        self._sweep()
        while self._offer_next():
            pass

    def _offer_next(self) -> bool:
        """Offer the next waiting request to the available specialist with the most spare capacity.

        The line is escalated requests first, then oldest first (R42).

        One transaction (ADR 0001). The available specialists' rows are locked first, always in the same
        order, so two runs never deadlock, and a run that waits on them then sees the request, the free
        slot, or the specialist that made it wait. The request is claimed with SKIP LOCKED, and live chats
        are counted only under the locks, so two offers never both take a specialist's last slot.
        """
        now = self._clock.now()
        with self._pool.connection() as conn:
            locked = conn.execute(
                "SELECT staff_id FROM specialist_availability WHERE state = 'available' ORDER BY staff_id FOR UPDATE"
            ).fetchall()
            if not locked:
                return False
            request = conn.execute(
                """
                SELECT id FROM live_chat_requests WHERE status = 'waiting'
                ORDER BY reason <> 'escalated', queued_at, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if request is None:
                return False
            # A new statement after the locks, so the count includes every offer committed before them.
            chosen = conn.execute(
                """
                SELECT a.staff_id FROM specialist_availability a
                LEFT JOIN live_chat_requests r ON r.staff_id = a.staff_id AND r.status IN ('offered', 'active')
                WHERE a.staff_id = ANY(%s)
                GROUP BY a.staff_id, a.capacity
                HAVING count(r.id) < a.capacity
                ORDER BY a.capacity - count(r.id) DESC, a.staff_id
                LIMIT 1
                """,
                ([row["staff_id"] for row in locked],),
            ).fetchone()
            if chosen is None:
                return False
            conn.execute(
                "UPDATE live_chat_requests SET status = 'offered', staff_id = %s, offered_at = %s WHERE id = %s",
                (chosen["staff_id"], now, request["id"]),
            )
            _audit(conn, chosen["staff_id"], "live_chat_offered", now)
            conn.commit()
        return True

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

    def _gated_draft(self, case_id: uuid.UUID, staff_id: uuid.UUID, question: str, now: datetime, note: str = "") -> Draft:
        """Any request that waits for a lead. The handbook rule for each action lives in northstar.actions."""
        action = gated(question)
        if action is None:
            return _plain("ask_clarification", "Which action and which order id? Nothing is proposed.")
        order_id = _order_id(question)
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


def _audit(conn, staff_id: uuid.UUID | None, event: str, at: datetime) -> None:
    """An audit event in the caller's transaction, so it is recorded only with the change it describes."""
    conn.execute("INSERT INTO audit_log (staff_id, event, created_at) VALUES (%s, %s, %s)", (staff_id, event, at))


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
