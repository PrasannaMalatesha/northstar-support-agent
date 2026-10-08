"""Postgres storage for staff accounts, login attempts, and refresh tokens."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from northstar.identity.service import Staff

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text()


class PostgresIdentityStore:
    def __init__(self, pool) -> None:
        self._pool = pool

    def ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def get_by_email(self, email: str) -> Staff | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM staff_users WHERE email = %s",
                (email,),
            ).fetchone()
        return _staff(row)

    def get_by_id(self, staff_id: uuid.UUID) -> Staff | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM staff_users WHERE id = %s",
                (staff_id,),
            ).fetchone()
        return _staff(row)

    def recent_failure_count(self, email: str, since: datetime) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS n FROM login_attempts
                WHERE email = %s AND success = false AND attempted_at >= %s
                """,
                (email, since),
            ).fetchone()
        return int(row["n"])

    def record_attempt(self, email: str, success: bool, attempted_at: datetime) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO login_attempts (email, success, attempted_at)
                VALUES (%s, %s, %s)
                """,
                (email, success, attempted_at),
            )
            conn.commit()

    def save_refresh(
        self, staff_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO refresh_tokens (id, staff_id, token_hash, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (uuid.uuid4(), staff_id, token_hash, expires_at),
            )
            conn.commit()

    def revoke_refresh(self, token_hash: str, revoked_at: datetime) -> uuid.UUID | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE refresh_tokens
                SET revoked_at = %s
                WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > %s
                RETURNING staff_id
                """,
                (revoked_at, token_hash, revoked_at),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return row["staff_id"]

    def bump_session(self, staff_id: uuid.UUID) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE staff_users
                SET session_version = session_version + 1
                WHERE id = %s
                """,
                (staff_id,),
            )
            conn.commit()

    def audit(self, staff_id: uuid.UUID | None, event: str, at: datetime) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (staff_id, event, created_at)
                VALUES (%s, %s, %s)
                """,
                (staff_id, event, at),
            )
            conn.commit()

    def upsert_staff(
        self,
        staff_id: uuid.UUID,
        email: str,
        name: str,
        password_hash: str,
        role: str,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO staff_users (id, email, name, password_hash, role)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE
                SET name = EXCLUDED.name,
                    password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role
                """,
                (staff_id, email, name, password_hash, role),
            )
            conn.commit()

    def truncate(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                TRUNCATE case_messages, cases, audit_log, refresh_tokens,
                    login_attempts, staff_users
                RESTART IDENTITY CASCADE
                """
            )
            conn.commit()


def _staff(row) -> Staff | None:
    if row is None:
        return None
    return Staff(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=row["role"],
        session_version=row["session_version"],
        password_hash=row["password_hash"],
        disabled=row["disabled_at"] is not None,
    )
