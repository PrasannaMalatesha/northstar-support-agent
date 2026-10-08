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
    shipped_on: date | None = None
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


def refund(question: str, order: Order, today: date) -> Proposal | Reply:
    if order.delivered_on is None:
        # The return window counts from delivery. An order that has not arrived is not a return.
        return Reply(
            "answer",
            f"Order {order.id} is {order.status} and has not been delivered, so it is not a return yet. "
            "A placed order can be cancelled instead. (ORD-CANCEL)",
            ("ORD-CANCEL",),
        )
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


def cancel(question: str, order: Order, today: date) -> Proposal | Reply:
    # ORD-CANCEL: only a placed order, refunded in full including outbound shipping.
    if order.status != "placed":
        return Reply(
            "answer",
            f"Order {order.id} is {order.status}, so it cannot be cancelled. "
            "Only a placed order can be cancelled. (ORD-CANCEL)",
            ("ORD-CANCEL",),
        )
    return Proposal(
        "cancel",
        order.total_cents,
        ("ORD-CANCEL",),
        f"Cancel order {order.id}. Refund {order.total_cents} cents in full, including shipping. "
        "A person records the cancel. (ORD-CANCEL)",
    )


# The text after the last "to", when it holds a street number.
_NEW_ADDRESS = re.compile(r".*\bto\s+(.*\d.*?)\s*\.?\s*$", re.IGNORECASE | re.DOTALL)


def address_change(question: str, order: Order, today: date) -> Proposal | Reply:
    # SHIP-ADDRESS: placed or packed only. No reroute once the package has left.
    if order.status not in ("placed", "packed"):
        return Reply(
            "answer",
            f"Order {order.id} is {order.status}, so the ship-to address cannot be changed. "
            "Northstar does not reroute a package that has left the building. (SHIP-ADDRESS)",
            ("SHIP-ADDRESS",),
        )
    found = _NEW_ADDRESS.search(question)
    if found is None:
        return Reply("ask_clarification", "What is the new ship-to address? Nothing is proposed.")
    # The draft leaves the address out. The lead sees it on the proposal.
    return Proposal(
        "address_change",
        None,
        ("SHIP-ADDRESS",),
        f"Change the ship-to address on order {order.id}. A person records the change. (SHIP-ADDRESS)",
        details=f"New address: {found.group(1).strip()}",
    )


# First match wins, so a narrower request sits above a broader one.
ACTIONS: tuple[GatedAction, ...] = (
    GatedAction("cancel", re.compile(r"\bcancel"), cancel, "Which order id? Nothing is cancelled."),
    GatedAction("address_change", re.compile(r"\baddress\b"), address_change, "Which order id? No address is changed."),
    GatedAction("refund", re.compile(r"\brefunds?\b|\bcredit\b"), refund, "Which order id? No amount is proposed."),
)

# Every decision that is a proposal. These pause for a lead and must cite a section.
PROPOSALS = frozenset({"approve_refund", "partial_credit", "deny", "cancel", "address_change"})

_ORDER_ID = re.compile(r"\bNS-\d+\b", re.IGNORECASE)
# A policy question with no order id is a handbook question, not a request to act.
_POLICY_QUESTION = re.compile(
    r"^\s*(can|could|how|what|when|why|is|are|does|do|will)\b.*\?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def order_id(question: str) -> str | None:
    match = _ORDER_ID.search(question)
    return match.group(0).upper() if match else None


def gated(question: str) -> GatedAction | None:
    if order_id(question) is None and _POLICY_QUESTION.match(question):
        return None
    lowered = question.lower()
    for action in ACTIONS:
        if action.pattern.search(lowered):
            return action
    return None
