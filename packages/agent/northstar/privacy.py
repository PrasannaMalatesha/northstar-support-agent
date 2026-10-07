"""Remove personal data from text the specialist will see.

ponytail: regex screen. Swap for PIIMiddleware when the LangGraph agent exists.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_SECRET = re.compile(r"sk-[A-Za-z0-9-]{8,}|api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE)

SECRET_REPLY = "This message contains a secret and was stopped."


def has_secret(text: str) -> bool:
    return _SECRET.search(text) is not None


def screen(text: str) -> str:
    def mask_card(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if not 13 <= len(digits) <= 19:
            return match.group(0)
        return ("*" * (len(digits) - 4)) + digits[-4:]

    text = _SECRET.sub("[secret]", text)
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    return _CARD.sub(mask_card, text)
