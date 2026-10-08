"""One open case per specialist, with the handbook draft stored on it.

ponytail: the assistant row is the trace (decision plus section ids).
Send the same fields to LangSmith when LANGSMITH_API_KEY is set.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from northstar.actions import FAMILIES, Order, Proposal, Reply, family_decisions, gated, order_id as _order_id
from northstar.clock import Clock
from northstar.escalate import handoff, manual_handoff
from northstar.graph import TurnTools, resume_turn, run_turn
from northstar.memory import graph_for
from northstar.agent_model import handbook_reply
from northstar.handbook import ABSTAIN_TEXT, Draft, guard_draft
from northstar.online import record_edit, record_judge
from northstar.privacy import SECRET_REPLY, has_secret, screen

# ponytail: 1_000 tokens stands in for one handbook draft. Replace with the
# model's reported usage when a model is called. Request counts are in memory.
TOKENS_PER_TURN = 1_000
REQUEST_LIMIT_TEXT = (
    "This account has hit the request limit. The case is still here. Try again later."
)
QUOTA_TEXT = "The daily quota is reached. This case is still here."
UNBOUND_ORDER_TEXT = "Pick a customer first. No order was read."
SAFE_REPLY = (
    "I can't continue with that message. "
    "If there is an order question, a specialist can take it from here."
)
_BLOCKED = (
    "ignore the handbook",
    "ignore previous",
    "ignore these rules",
    "retard",
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


class CaseStore:
    def __init__(self, pool, clock: Clock, request_limit: int = 60, token_budget: int = 20_000) -> None:
        self._pool = pool
        self._clock = clock
        self._request_limit = request_limit
        self._token_budget = token_budget
        self._requests: dict[tuple[uuid.UUID, object], int] = {}

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

    def ask(self, staff_id: uuid.UUID, question: str) -> dict:
        case_id = self._open(staff_id)
        if self._status(case_id) != "Open":
            raise CaseClosed()
        now = self._clock.now()
        day = now.date()
        key = (staff_id, day)
        if self._requests.get(key, 0) >= self._request_limit:
            return self._save(case_id, question, _plain("limit", REQUEST_LIMIT_TEXT), now)
        self._requests[key] = self._requests.get(key, 0) + 1
        if has_secret(question):
            return self._save(case_id, question, _plain("blocked", SECRET_REPLY), now)
        escalated = handoff(question, self._tried(case_id))
        if escalated is not None:
            section, text = escalated.section, escalated.text
            self._mark_escalated(case_id, text)
            # Through the graph, so the escalation has a LangGraph trace for the safety rule and the judge.
            fixed = Draft("escalate", text, (section,), {section: "strong"}, ())
            tools = TurnTools(refund=lambda _text: fixed, support=lambda _text: fixed)
            return self._save(case_id, question, self._turn(case_id, question, tools), now)
        if _blocked(question):
            return self._save(case_id, question, _plain("safe", SAFE_REPLY), now)
        tools = TurnTools(
            refund=lambda text: self._gated_draft(case_id, staff_id, text, now),
            support=lambda text: self._support_draft(case_id, staff_id, text, now),
        )
        return self._save(case_id, question, self._turn(case_id, question, tools), now)

    def _turn(self, case_id: uuid.UUID, question: str, tools: TurnTools) -> Draft:
        return run_turn(question, tools, graph=graph_for(self._pool.conninfo), thread_id=str(case_id))

    def _save(self, case_id: uuid.UUID, question: str, draft: Draft, now: datetime) -> dict:
        run_id = draft.run_id
        draft = guard_draft(draft)
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO case_messages (case_id, role, body, created_at)
                VALUES (%s, 'user', %s, %s)
                """,
                (case_id, screen(question.strip()), now),
            )
            conn.execute(
                """
                INSERT INTO case_messages
                    (case_id, role, body, decision, citations, strengths, steps, run_id,
                     retrieved_sections, retrieved_scores, created_at)
                VALUES (%s, 'assistant', %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        try:
            record_judge(draft["run_id"], question, draft["decision"] or "", text, draft["citations"], 1.0, edited=True)
        except Exception:
            # A LangSmith or judge outage must not undo a close or a ticket.
            logging.getLogger(__name__).warning("edit judge failed for run %s", draft["run_id"], exc_info=True)
        try:
            record_edit(draft["run_id"], question, draft["citations"], before, after)
        except Exception:
            logging.getLogger(__name__).warning("edit pair was not sent for run %s", draft["run_id"], exc_info=True)

    def _resume(self, case_id: uuid.UUID, decision: str) -> None:
        resume_turn(graph_for(self._pool.conninfo), str(case_id), decision)

    def _support_draft(self, case_id: uuid.UUID, staff_id: uuid.UUID, question: str, now: datetime) -> Draft:
        order_id = _order_id(question)
        if order_id or (self._customer(case_id) is None and _asks_for_an_order(question)):
            if self._customer(case_id) is None:
                return _plain("unbound", UNBOUND_ORDER_TEXT)
            if order_id:
                return self._order_draft(case_id, order_id, question)
        catalog = self._catalog_draft(question)
        if catalog is not None:
            return catalog
        day = now.date()
        if self._used(staff_id, day) + TOKENS_PER_TURN > self._token_budget:
            return _plain("quota", QUOTA_TEXT)
        self._charge(staff_id, day, TOKENS_PER_TURN)
        return handbook_reply(question)

    def _gated_draft(self, case_id: uuid.UUID, staff_id: uuid.UUID, question: str, now: datetime) -> Draft:
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
            return _plain("abstain", "I don't have that item in the catalog.")
        return None

    def _used(self, staff_id: uuid.UUID, day) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT tokens FROM usage_days WHERE staff_id = %s AND day = %s",
                (staff_id, day),
            ).fetchone()
        return int(row["tokens"]) if row else 0

    def _charge(self, staff_id: uuid.UUID, day, tokens: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO usage_days (staff_id, day, tokens)
                VALUES (%s, %s, %s)
                ON CONFLICT (staff_id, day)
                DO UPDATE SET tokens = usage_days.tokens + EXCLUDED.tokens
                """,
                (staff_id, day, tokens),
            )
            conn.commit()

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


def _plain(decision: str, text: str) -> Draft:
    return Draft(decision, text, (), {}, ())


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
_CATALOG_PHRASES = ("in stock", "how much", "price", "final sale", "what size")


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
    return re.search(r"\borders?\b", question.lower()) is not None


def _blocked(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in _BLOCKED)
