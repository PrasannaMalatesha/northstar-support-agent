"""Seed the two demo staff accounts. There is no public sign-up."""

import secrets

from northstar.identity.postgres import PostgresIdentityStore
from northstar.identity.service import hash_password, staff_id_for

CHAT_STAFF_EMAIL = "chat@northstar.example"

DEMO_STAFF = (
    {
        "email": "specialist@northstar.example",
        "name": "Avery Cole",
        "role": "specialist",
        "password": "northstar-specialist",
    },
    {
        "email": "lead@northstar.example",
        "name": "Riley Chen",
        "role": "lead",
        "password": "northstar-lead",
    },
)


def seed_staff(store: PostgresIdentityStore) -> None:
    for person in DEMO_STAFF:
        store.upsert_staff(
            staff_id_for(person["email"]),
            person["email"],
            person["name"],
            hash_password(person["password"]),
            person["role"],
        )
    # Owns customer chat cases (issue #79). Disabled with a random password, so it can never sign in.
    store.upsert_staff(
        staff_id_for(CHAT_STAFF_EMAIL),
        CHAT_STAFF_EMAIL,
        "Customer chat",
        hash_password(secrets.token_urlsafe(32)),
        "specialist",
        disabled=True,
    )
