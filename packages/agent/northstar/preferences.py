"""A customer's stated preferences, remembered across cases (R20).

Only a contact channel is kept, read from words like "I prefer email". Free text is never
stored, so a payment number or a secret cannot become a preference. A preference can shape
tone or channel. It never sets an amount or answers a policy question.
https://docs.langchain.com/oss/python/langgraph/stores
"""

from __future__ import annotations

import re

_CHANNEL = re.compile(
    r"\b(prefer|prefers|rather|contact me|reach me|reply to me|get back to me)\b[^.?!]*?\b(?P<channel>email|e-mail|phone|call|text|sms)\b",
    re.IGNORECASE,
)
_CHANNELS = {"email": "email", "e-mail": "email", "phone": "phone", "call": "phone", "text": "text", "sms": "text"}
# conninfo -> (context, store). The context is kept: dropping it closes the connection.
_OPEN: dict[str, tuple[object, object]] = {}


def stated(question: str) -> dict[str, str]:
    found = _CHANNEL.search(question)
    return {"contact_channel": _CHANNELS[found.group("channel").lower()]} if found else {}


def _namespace(customer_id) -> tuple[str, ...]:
    return ("customers", str(customer_id), "prefs")


def _store(conninfo: str):
    cached = _OPEN.get(conninfo)
    if cached is not None:
        return cached[1]
    from langgraph.store.postgres import PostgresStore

    context = PostgresStore.from_conn_string(conninfo)
    store = context.__enter__()
    store.setup()
    _OPEN[conninfo] = (context, store)
    return store


def remember(conninfo: str, customer_id, prefs: dict[str, str], stated_on: str) -> None:
    for key, value in prefs.items():
        _store(conninfo).put(_namespace(customer_id), key, {"value": value, "stated_on": stated_on}, index=False)


def recall(conninfo: str, customer_id) -> dict[str, str]:
    items = _store(conninfo).search(_namespace(customer_id), limit=20)
    return {item.key: item.value["value"] for item in items}
