"""Seed the two demo staff accounts. There is no public sign-up."""

from northstar.identity.postgres import PostgresIdentityStore
from northstar.identity.service import hash_password, staff_id_for

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
