from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from northstar.clock import SystemClock
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from northstar_api.main import create_app
from northstar_api.settings import Settings

ADMIN_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar",
)
TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://northstar:northstar@localhost:5433/northstar_test",
)
SECRET = "test-token-secret-at-least-32-characters"


class FakeClock(SystemClock):
    def __init__(self) -> None:
        from datetime import datetime, timezone

        self.moment = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)

    def now(self):
        return self.moment

    def advance(self, **kwargs) -> None:
        from datetime import timedelta

        self.moment = self.moment + timedelta(**kwargs)


def _ensure_test_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'northstar_test'"
        ).fetchone()
        if exists is None:
            conn.execute("CREATE DATABASE northstar_test")


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def client(clock: FakeClock, request: pytest.FixtureRequest):
    _ensure_test_database()
    pool = ConnectionPool(
        TEST_URL,
        min_size=1,
        max_size=2,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    overrides = getattr(request, "param", None) or {}
    app = create_app(
        settings=Settings(database_url=TEST_URL, token_secret=SECRET, **overrides),
        clock=clock,
        pool=pool,
    )
    from northstar.identity.postgres import PostgresIdentityStore

    PostgresIdentityStore(pool).truncate()
    from northstar.identity.seed import seed_staff

    seed_staff(PostgresIdentityStore(pool))
    with TestClient(app) as test_client:
        yield test_client
    pool.close()
