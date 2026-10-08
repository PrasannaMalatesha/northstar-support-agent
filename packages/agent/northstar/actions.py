"""Gated actions: which requests need a lead, and the handbook rule that proposes each one.

Pure rules, no I/O. The case store reads the order, checks the case customer, and
writes the proposal. A new gated action is one rule and one entry in ACTIONS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
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
    # Actions that already have a ticket on this order.
    ticket_actions: frozenset[str] = frozenset()
    # The catalog row for the line item, when there is one.
    item_sizes: tuple[str, ...] = ()
    item_in_stock: bool | None = None
    item_final_sale: bool | None = None

    @property
    def ticketed(self) -> bool:
        return bool(self.ticket_actions)

    @property
    def item(self) -> str:
        return self.lines.split(",")[0].strip()

    @property
    def size(self) -> str | None:
        found = re.search(r"\bsize\s+(\w+)", self.lines, re.IGNORECASE)
        return found.group(1).upper() if found else None


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


EXCHANGE_CATEGORIES = ("apparel and footwear", "bags and accessories")
_SIZE_WORDS = {"extra small": "XS", "small": "S", "medium": "M", "large": "L", "extra large": "XL"}
_WANTED_SIZE = re.compile(r"\bsize\s+(xs|s|m|l|xl)\b|\b(extra small|extra large|small|medium|large)\b", re.IGNORECASE)


def _wanted_size(question: str) -> str | None:
    found = _WANTED_SIZE.search(question)
    if found is None:
        return None
    return (found.group(1) or "").upper() or _SIZE_WORDS[found.group(2).lower()]


def exchange(question: str, order: Order, today: date) -> Proposal | Reply:
    lowered = question.lower()
    if order.category not in EXCHANGE_CATEGORIES:
        return Reply(
            "answer",
            f"The {order.item} is {order.category}, which is not exchanged. It follows the returns handbook. (EXC-ELIGIBILITY)",
            ("EXC-ELIGIBILITY",),
        )
    if re.search(r"\bdifferent (item|product)\b|\binstead\b", lowered):
        return Reply(
            "answer",
            "A different item is a return plus a new order the customer places. Support does not place it. (EXC-DIFFERENT-ITEM)",
            ("EXC-DIFFERENT-ITEM",),
        )
    if order.delivered_on is None:
        return Reply(
            "answer",
            f"Order {order.id} has not been delivered. An exchange starts after delivery, inside the return window. (EXC-ELIGIBILITY)",
            ("EXC-ELIGIBILITY",),
        )
    if "exchange" in order.ticket_actions:
        return Reply(
            "answer",
            f"The {order.item} was already exchanged once. A second change is a return, not another exchange. (EXC-LIMIT)",
            ("EXC-LIMIT",),
        )
    if (today - order.delivered_on).days > RETURN_DAYS[order.category]:
        return Reply(
            "answer",
            f"Order {order.id} is outside the return window, so it cannot be exchanged. (EXC-ELIGIBILITY, REF-CATEGORY)",
            ("EXC-ELIGIBILITY", "REF-CATEGORY"),
        )
    if re.search(r"\b(worn|used|washed)\b", lowered):
        return Reply(
            "answer",
            "An exchange needs the item unworn with tags on. (EXC-ELIGIBILITY)",
            ("EXC-ELIGIBILITY",),
        )
    wanted = _wanted_size(question)
    if wanted is None or wanted == order.size:
        return Reply("ask_clarification", "Which size does the customer want? Nothing is proposed.")
    if wanted not in order.item_sizes or not order.item_in_stock:
        return Reply(
            "answer",
            f"The catalog does not show the {order.item} in size {wanted} as in stock, so this is a return, not an exchange. (EXC-STOCK)",
            ("EXC-STOCK",),
        )
    return Proposal(
        "exchange",
        None,
        ("EXC-ELIGIBILITY", "EXC-PROCESS"),
        f"Exchange the {order.item} on order {order.id} from size {order.size} to size {wanted}. "
        "Shipping is free both ways, and the new size ships when the return is scanned. "
        "A person records the exchange. (EXC-ELIGIBILITY, EXC-PROCESS)",
        details=f"{order.item}: size {order.size} to size {wanted}",
    )


_EXCLUDED = re.compile(
    r"\b(stain|stained|cut|cuts|normal wear|worn out|misuse|misused|dropped|change of mind|changed my mind|don't like|dislike)\b",
    re.IGNORECASE,
)
_DEFECT = re.compile(
    r"\bdefect|\bbroke|\bstopped working\b|\bfault|\bcrack|\b(does not|doesn't|won't) (work|turn on|charge)\b|\bseam\b|\bzipper\b",
    re.IGNORECASE,
)


def warranty(question: str, order: Order, today: date) -> Proposal | Reply:
    # WAR-COVERAGE: the return window first, then 90 days for apparel and 1 year for the rest.
    if order.delivered_on is None:
        return Reply(
            "answer",
            f"Order {order.id} has not been delivered, so neither the return window nor the warranty has started. (WAR-COVERAGE)",
            ("WAR-COVERAGE",),
        )
    if order.item_final_sale or _EXCLUDED.search(question):
        return Reply(
            "answer",
            "The warranty does not cover normal wear, cuts, stains, misuse, damage after delivery, final-sale lines, "
            "or a change of mind. Those follow the returns handbook. (WAR-EXCLUSIONS)",
            ("WAR-EXCLUSIONS",),
        )
    window_end = order.delivered_on + timedelta(days=RETURN_DAYS[order.category])
    if today <= window_end:
        # Inside the return window a defect is a return, not a warranty claim.
        return refund(question, order, today)
    coverage_end = window_end + timedelta(days=90 if order.category == "apparel and footwear" else 365)
    if today > coverage_end:
        return Reply(
            "answer",
            f"Warranty coverage for the {order.item} ended on {coverage_end.isoformat()}, so the claim is denied. (WAR-COVERAGE)",
            ("WAR-COVERAGE",),
        )
    if not _DEFECT.search(question):
        return Reply("ask_clarification", "Describe the defect on the line. Nothing is drafted yet.")
    return Proposal(
        "warranty_claim",
        None,
        ("WAR-COVERAGE", "WAR-CLAIM"),
        f"Warranty claim drafted for the {order.item} on order {order.id}. Coverage runs through "
        f"{coverage_end.isoformat()}. A person submits the claim, and its outcome is not known yet. (WAR-COVERAGE, WAR-CLAIM)",
        details=f"{order.item}: {question.strip()[:300]}",
    )


# First match wins, so a narrower request sits above a broader one.
ACTIONS: tuple[GatedAction, ...] = (
    GatedAction("cancel", re.compile(r"\bcancel"), cancel, "Which order id? Nothing is cancelled."),
    GatedAction("address_change", re.compile(r"\baddress\b"), address_change, "Which order id? No address is changed."),
    GatedAction("exchange", re.compile(r"\bexchange\b|\bswap\b"), exchange, "Which order id? Nothing is exchanged."),
    GatedAction("warranty_claim", re.compile(r"\bwarranty\b|" + _DEFECT.pattern), warranty, "Which order id? No claim is drafted."),
    GatedAction("refund", re.compile(r"\brefunds?\b|\bcredit\b"), refund, "Which order id? No amount is proposed."),
)

# Every decision that is a proposal. These pause for a lead and must cite a section.
PROPOSALS = frozenset(
    {"approve_refund", "partial_credit", "deny", "cancel", "address_change", "exchange", "warranty_claim"}
)

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
