"""Gated actions: which requests need a lead, and the handbook rule that proposes each one.

Pure rules, no I/O. The case store reads the order, checks the case customer, and
writes the proposal. A new gated action is one rule and one entry in ACTIONS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable


@dataclass(frozen=True)
class Order:
    """The order record a rule may read. Nothing else about the order is known."""

    id: str
    status: str
    purchased_on: date
    delivered_on: date | None
    category: str
    lines: str
    refunds: str
    total_cents: int
    # A ticket already exists for this order.
    ticketed: bool = False


@dataclass(frozen=True)
class Proposal:
    """A gated action waiting for a lead. Nothing is recorded until a lead decides."""

    action: str
    amount_cents: int | None
    citations: tuple[str, ...]
    text: str
    details: str = ""


@dataclass(frozen=True)
class Reply:
    """A cited answer that proposes nothing, such as a refusal the handbook requires."""

    decision: str
    text: str
    citations: tuple[str, ...] = ()


Rule = Callable[[str, Order, date], "Proposal | Reply"]


@dataclass(frozen=True)
class GatedAction:
    kind: str
    pattern: re.Pattern[str]
    rule: Rule
    missing_order: str


RETURN_DAYS = {
    "apparel and footwear": 30,
    "bags and accessories": 30,
    "home and kitchen": 30,
    "small electronics": 15,
}


def refund(question: str, order: Order, today: date) -> Proposal:
    if order.refunds != "none" or order.ticketed:
        return Proposal("deny", 0, ("REF-DENY",), "Deny. Amount: 0 cents. The line was already refunded. (REF-DENY)")
    age = (today - order.delivered_on).days
    if age > RETURN_DAYS[order.category]:
        return Proposal(
            "deny",
            0,
            ("REF-DENY", "REF-CATEGORY"),
            "Deny. Amount: 0 cents. The request is outside the return window. (REF-DENY, REF-CATEGORY)",
        )
    if re.search(r"\b(used|washed)\b", question.lower()):
        amount = order.total_cents // 2
        return Proposal("partial_credit", amount, ("REF-PARTIAL",), f"Partial credit. Amount: {amount} cents. (REF-PARTIAL)")
    amount = order.total_cents
    return Proposal(
        "approve_refund",
        amount,
        ("REF-ELIGIBILITY", "REF-CATEGORY"),
        f"Approve. Amount: {amount} cents. (REF-ELIGIBILITY, REF-CATEGORY)",
    )


# First match wins, so a narrower request sits above a broader one.
ACTIONS: tuple[GatedAction, ...] = (
    GatedAction("refund", re.compile(r"\brefunds?\b|\bcredit\b"), refund, "Which order id? No amount is proposed."),
)

# Every decision that is a proposal. These pause for a lead and must cite a section.
PROPOSALS = frozenset({"approve_refund", "partial_credit", "deny"})


def gated(question: str) -> GatedAction | None:
    lowered = question.lower()
    for action in ACTIONS:
        if action.pattern.search(lowered):
            return action
    return None
