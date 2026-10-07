"""Turn legal language or a request to bend a rule into a handoff.

The sentences are the handbook rules for ESC-LEGAL and ESC-WHEN.
"""

from __future__ import annotations

import re

from northstar.privacy import screen

_LEGAL = ("chargeback", "lawyer", "lawsuit", "regulator", "legal advice")


def handoff(question: str) -> tuple[str, str] | None:
    lowered = question.lower()
    order = re.search(r"\bNS-\d+\b", question.upper())
    asked = screen(question.strip())
    if order:
        asked = f"{asked} Order id: {order.group(0)}."
    if any(word in lowered for word in _LEGAL):
        section = "ESC-LEGAL"
        handbook = (
            "Chargebacks, lawsuits, regulator complaints, and requests for legal advice are escalated."
        )
        missing = "A person must decide. No refund is offered to stop a chargeback. No legal advice is given."
    elif "exception" in lowered:
        section = "ESC-WHEN"
        handbook = "Escalate when the customer asks for an exception to a deny rule."
        missing = "The exception is not in the handbook."
    else:
        return None
    text = f"Asked: {asked}\nHandbook: {handbook} ({section})\nMissing: {missing}"
    return section, text
