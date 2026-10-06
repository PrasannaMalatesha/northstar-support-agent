"""One open case per specialist, with the handbook draft stored on it.

ponytail: the assistant row is the trace (decision plus section ids).
Send the same fields to LangSmith when LANGSMITH_API_KEY is set.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from northstar.clock import Clock
from northstar.handbook import Draft, answer

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
CREATE TABLE IF NOT EXISTS usage_days (
    staff_id uuid NOT NULL REFERENCES staff_users (id),
    day date NOT NULL,
    tokens integer NOT NULL,
    PRIMARY KEY (staff_id, day)
);
"""


class CaseClosed(Exception):
    """A Resolved or Escalated case does not take another message."""


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
            conn.commit()

    def current(self, staff_id: uuid.UUID) -> dict:
        return self._view(self._open(staff_id))

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
                SET status = %s, draft_text = %s, final_text = %s
                WHERE id = %s
                """,
                (status, "" if draft is None else draft["body"], final_text.strip(), case_id),
            )
            conn.commit()
        return self._view(case_id)

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
        if _blocked(question):
            return self._save(case_id, question, _plain("safe", SAFE_REPLY), now)
        if self._customer(case_id) is None and _asks_for_an_order(question):
            return self._save(case_id, question, _plain("unbound", UNBOUND_ORDER_TEXT), now)
        if self._used(staff_id, day) + TOKENS_PER_TURN > self._token_budget:
            return self._save(case_id, question, _plain("quota", QUOTA_TEXT), now)
        draft = answer(question)
        self._charge(staff_id, day, TOKENS_PER_TURN)
        return self._save(case_id, question, draft, now)

    def _save(self, case_id: uuid.UUID, question: str, draft: Draft, now: datetime) -> dict:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO case_messages (case_id, role, body, created_at)
                VALUES (%s, 'user', %s, %s)
                """,
                (case_id, question.strip(), now),
            )
            conn.execute(
                """
                INSERT INTO case_messages
                    (case_id, role, body, decision, citations, strengths, steps, created_at)
                VALUES (%s, 'assistant', %s, %s, %s, %s, %s, %s)
                """,
                (
                    case_id,
                    draft.text,
                    draft.decision,
                    list(draft.citations),
                    [draft.match[section_id] for section_id in draft.citations],
                    list(draft.steps),
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
        }

    def _status(self, case_id: uuid.UUID) -> str:
        return self._case_row(case_id)["status"]

    def _case_row(self, case_id: uuid.UUID):
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT cases.status, cases.draft_text, cases.final_text,
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
                ORDER BY created_at DESC
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


def _asks_for_an_order(question: str) -> bool:
    return re.search(r"\borders?\b", question.lower()) is not None


def _blocked(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in _BLOCKED)
