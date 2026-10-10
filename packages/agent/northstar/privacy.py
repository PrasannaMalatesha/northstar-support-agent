"""Remove personal data from text the specialist will see.

screen() runs on every saved text. The same patterns back the PIIMiddleware
detectors in the graph, so the model and the traces see what the specialist sees.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}")
# Not glued to a letter or digit, so the digit runs inside an id such as a UUID stay intact.
_CARD = re.compile(r"(?<![0-9A-Za-z])(?:\d[ -]?){12,18}\d(?![0-9A-Za-z])")
_SECRET = re.compile(r"sk-[A-Za-z0-9-]{8,}|api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE)

# Northstar's own addresses, published in the handbook (FAQ-CONTACT). Not personal data, so never masked.
PUBLISHED_EMAILS = frozenset({"help@northstar.example"})

SECRET_REPLY = "This message contains a secret and was stopped."


def has_secret(text: str) -> bool:
    return _SECRET.search(text) is not None


def detector(kind: str):
    """A PIIMiddleware detector for `email`, `phone`, or `secret`, from the patterns above.

    Like screen(), the email detector leaves the published addresses alone. Redacting the support
    address from the desk's answer made the model ask the desk again, a wasted model call.
    """
    pattern = {"email": _EMAIL, "phone": _PHONE, "secret": _SECRET}[kind]

    def find(text: str) -> list[dict]:
        return [
            {"type": kind, "value": match.group(0), "start": match.start(), "end": match.end()}
            for match in pattern.finditer(text)
            if not (kind == "email" and match.group(0).lower() in PUBLISHED_EMAILS)
        ]

    return find


def screen(text: str) -> str:
    def mask_card(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if not 13 <= len(digits) <= 19:
            return match.group(0)
        return ("*" * (len(digits) - 4)) + digits[-4:]

    text = _SECRET.sub("[secret]", text)
    text = _EMAIL.sub(lambda m: m.group(0) if m.group(0).lower() in PUBLISHED_EMAILS else "[email]", text)
    text = _PHONE.sub("[phone]", text)
    return _CARD.sub(mask_card, text)
