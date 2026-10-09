"""Turn legal language, fraud, a policy conflict, or a request to bend a rule into a handoff.

The sentences are the handbook rules for ESC-LEGAL, ESC-FRAUD, and ESC-WHEN. The packet
stands alone (R17): what was asked, the order, the sections read, what was tried, what is
missing, and who should own it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from northstar.privacy import screen

_LEGAL = ("chargeback", "lawyer", "lawsuit", "regulator", "legal advice")
_FRAUD = re.compile(
    r"\b(did not|didn't|never) (place|make|buy|order)\b|\bnot my order\b|\baccount (was |got |has been )?(hacked|taken over)\b",
    re.IGNORECASE,
)
_CONFLICT = re.compile(
    r"\b(website|site|web page|ad|advert|another agent|your agent|last agent|a rep|chat)\b[^.]*\b(said|says|told|promised)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Handoff:
    section: str
    asked: str
    order_id: str | None
    handbook: str
    missing: str
    owner: str
    sections: tuple[str, ...] = ()
    tried: tuple[str, ...] = ()
    # The questions and replies before a left message, so the packet stands alone.
    recent: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        sections = ", ".join(dict.fromkeys((*self.sections, self.section)))
        lines = (
            f"Asked: {self.asked}",
            f"Handbook: {self.handbook} ({self.section})",
            f"Missing: {self.missing}",
            f"Order: {self.order_id or 'none'}",
            f"Sections read: {sections}",
            f"Tried: {'; '.join(self.tried) if self.tried else 'Nothing yet.'}",
            f"Owner: {self.owner}",
        )
        return "\n".join((*lines, "Recent turns:", *self.recent) if self.recent else lines)


def _order_id(question: str) -> str | None:
    found = re.search(r"\bNS-\d+\b", question.upper())
    return found.group(0) if found else None


def _asked(question: str, order_id: str | None) -> str:
    asked = screen(question.strip())
    return f"{asked} Order id: {order_id}." if order_id else asked


def handoff(question: str, tried: tuple[str, ...] = ()) -> Handoff | None:
    lowered = question.lower()
    order_id = _order_id(question)
    if any(word in lowered for word in _LEGAL):
        section, owner = "ESC-LEGAL", "legal"
        handbook = "Chargebacks, lawsuits, regulator complaints, and requests for legal advice are escalated."
        missing = "A person must decide. No refund is offered to stop a chargeback. No legal advice is given."
    elif _FRAUD.search(question):
        section, owner = "ESC-FRAUD", "support lead"
        handbook = "Suspected account takeover or a fraudulent order escalates."
        missing = "Whether the customer placed the order. No refund, cancel, or address change before a person decides."
    elif "exception" in lowered:
        section, owner = "ESC-WHEN", "support lead"
        handbook = "Escalate when the customer asks for an exception to a deny rule."
        missing = "The exception is not in the handbook."
    elif _CONFLICT.search(question):
        section, owner = "ESC-WHEN", "policy"
        handbook = "Escalate when two sources appear to conflict. The handbook wins until a policy owner decides."
        missing = "Which rule the customer was shown. The policy owner settles the conflict."
    else:
        return None
    return Handoff(section, _asked(question, order_id), order_id, handbook, missing, owner, (), tried)


def manual_handoff(question: str, sections: tuple[str, ...], tried: tuple[str, ...], note: str) -> Handoff:
    """The packet when a specialist escalates a case by hand."""
    order_id = _order_id(question)
    return Handoff(
        "ESC-WHEN",
        _asked(question, order_id),
        order_id,
        "A person takes the case when the handbook does not settle it.",
        f"Specialist note: {screen(note.strip())}",
        "support lead",
        sections,
        tried,
    )


def left_message(
    message: str,
    tried: tuple[str, ...],
    recent: tuple[str, ...],
    why: str = "The agent's recent replies did not help.",
) -> Handoff:
    """The packet for a left message: the customer's words, why they left it, and the recent turns (R35)."""
    order_id = _order_id(message) or _order_id(" ".join(reversed(recent)))
    return Handoff(
        "ESC-WHEN",
        _asked(message, order_id),
        order_id,
        "Escalate when the handbook does not cover the question.",
        f"{why} The customer left this message for a specialist.",
        "specialist",
        (),
        tried,
        recent,
    )
