"""The browser suite's clock: cases start from the seed's date and move in real time; tokens keep the real clock.

Without it the suite failed on 2026-10-15: NS-1011's damage window (delivered 2026-09-30, 14 days) had closed.
"""

from datetime import datetime, timedelta, timezone

from northstar.clock import StartedClock
from northstar_api.main import create_app
from northstar_api.settings import Settings

SEED_DAY = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def test_a_started_clock_begins_at_its_moment_and_runs_on():
    clock = StartedClock(SEED_DAY)
    first = clock.now()
    assert abs(first - SEED_DAY) < timedelta(seconds=1)
    assert clock.now() >= first


def test_the_setting_moves_cases_but_not_tokens(monkeypatch):
    seen = {}
    import northstar_api.main as main

    real_cases = main.CaseStore

    def cases(pool, clock, *args, **kwargs):
        seen["cases"] = clock
        return real_cases(pool, clock, *args, **kwargs)

    real_identity = main.Identity

    def identity(store, clock, *args, **kwargs):
        seen["tokens"] = clock
        return real_identity(store, clock, *args, **kwargs)

    monkeypatch.setattr(main, "CaseStore", cases)
    monkeypatch.setattr(main, "Identity", identity)
    from conftest import TEST_URL

    create_app(settings=Settings(database_url=TEST_URL, clock_start=SEED_DAY))
    assert abs(seen["cases"].now() - SEED_DAY) < timedelta(seconds=5)
    assert abs(seen["tokens"].now() - datetime.now(timezone.utc)) < timedelta(seconds=5)
    create_app(settings=Settings(database_url=TEST_URL))
    assert abs(seen["cases"].now() - datetime.now(timezone.utc)) < timedelta(seconds=5)


def test_a_deployed_environment_will_not_start_with_the_public_token_secret(monkeypatch):
    import pytest

    from conftest import TEST_URL

    monkeypatch.setenv("NORTHSTAR_ENV", "prod")
    with pytest.raises(RuntimeError, match="TOKEN_SECRET"):
        create_app(settings=Settings(database_url=TEST_URL))
    # With its own secret it starts; on a laptop the built-in one is fine.
    create_app(settings=Settings(database_url=TEST_URL, token_secret="a-real-secret-of-at-least-32-characters"))
    monkeypatch.setenv("NORTHSTAR_ENV", "local")
    create_app(settings=Settings(database_url=TEST_URL))
