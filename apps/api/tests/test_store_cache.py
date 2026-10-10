"""The process-wide Postgres store and checkpointer open once, even when first requests race."""

import threading

import northstar.memory as memory
import northstar.preferences as preferences

URL = "postgresql://race"


class _Slow:
    """Stands in for a store or saver context. Opening it is slow, so racing threads overlap."""

    opened = 0

    def __enter__(self):
        _Slow.opened += 1
        threading.Event().wait(0.05)
        return self

    def setup(self):
        pass


def _race(open_one, cache: dict) -> int:
    _Slow.opened = 0
    cache.pop(URL, None)
    barrier = threading.Barrier(8)

    def first_request():
        barrier.wait()
        open_one(URL)

    threads = [threading.Thread(target=first_request) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    cache.pop(URL, None)
    return _Slow.opened


def test_racing_first_requests_open_one_preferences_store(monkeypatch):
    import langgraph.store.postgres as postgres_store

    monkeypatch.setattr(postgres_store.PostgresStore, "from_conn_string", lambda _conninfo: _Slow())
    assert _race(preferences._store, preferences._OPEN) == 1


def test_racing_first_requests_open_one_checkpointer(monkeypatch):
    monkeypatch.setattr(memory.PostgresSaver, "from_conn_string", lambda _conninfo: _Slow())
    monkeypatch.setattr(memory, "_compile", lambda saver: object())
    assert _race(memory.graph_for, memory._OPEN) == 1
