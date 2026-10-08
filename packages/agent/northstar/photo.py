"""Describe a damaged-item photo for the lead (P2, issue #80).

The photo is evidence, never a decision: the action still comes from the specialist's
words and the handbook rules, and the lead still decides. Only the screened description
is kept. The image is not saved, not put in memory or the handbook index, and the
vision call is left out of tracing.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
from dataclasses import dataclass

from northstar.privacy import screen

MAX_BYTES = 4 * 1024 * 1024
_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\s]+)$")


class BadPhoto(ValueError):
    """Not a PNG, JPEG, or WebP data URL, or larger than MAX_BYTES."""


@dataclass(frozen=True)
class Photo:
    shows_item: bool
    visible_damage: bool
    description: str

    @property
    def line(self) -> str:
        """One line for the draft and the proposal, so the lead reads the verdict first."""
        if not self.shows_item:
            verdict = "does not show the item"
        elif self.visible_damage:
            verdict = "visible damage"
        else:
            verdict = "no visible damage"
        return f"Photo: {verdict}. {self.description}".strip()


def checked(data_url: str) -> tuple[str, bytes]:
    """The media type and bytes of a photo, or BadPhoto."""
    match = _DATA_URL.match(data_url.strip())
    if not match:
        raise BadPhoto("Attach a PNG, JPEG, or WebP image.")
    try:
        raw = base64.b64decode(match.group(2), validate=False)
    except (binascii.Error, ValueError) as error:
        raise BadPhoto("The image could not be read.") from error
    if not raw or len(raw) > MAX_BYTES:
        raise BadPhoto("The image must be under 4 MB.")
    return match.group(1), raw


def describe(data_url: str, note: str) -> Photo | None:
    """What the photo shows, judged against the specialist's note. None when no model is set up."""
    from northstar.agent_model import _load_local_env

    media_type, raw = checked(data_url)
    _load_local_env()
    if os.environ.get("PYTEST_CURRENT_TEST") or not os.environ.get("GOOGLE_API_KEY"):
        return None
    try:
        verdict = _ask_model(media_type, base64.b64encode(raw).decode(), note)
    except Exception:
        return None
    return Photo(bool(verdict["shows_item"]), bool(verdict["visible_damage"]), screen(str(verdict["description"]))[:400])


def _ask_model(media_type: str, encoded: str, note: str) -> dict:
    from langsmith import tracing_context
    from typing_extensions import TypedDict

    from northstar.agent_model import _model

    class Verdict(TypedDict):
        shows_item: bool
        visible_damage: bool
        description: str

    message = [
        {
            "role": "system",
            "content": (
                "You look at a customer's photo for a support specialist. Say whether it shows the product the "
                "specialist's note is about, and whether damage is visible on it. Describe only what is visible, "
                "in at most two sentences. Do not transcribe names, addresses, or labels. Do not decide a refund."
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Specialist's note: {screen(note)[:500]}"},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
            ],
        },
    ]
    # The image stays out of LangSmith traces.
    with tracing_context(enabled=False):
        return _model().with_structured_output(Verdict).invoke(message)
