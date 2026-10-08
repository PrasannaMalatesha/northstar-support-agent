"""Spanish in, Spanish out. The desk itself still decides in English (P2, issue #81).

A Spanish question is translated to English once. Every rule, gate, and citation then runs
on that English text unchanged. The finished draft is translated back, and the English
section ids, order ids, and amounts stay exact. On any model failure the English stands.
"""

from __future__ import annotations

import os
import re

from northstar.handbook import Draft

# ponytail: a marker check, not a language model. Spanish is the one extra language (P2).
_ACCENTED = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_WORDS = re.compile(
    r"\b(el|la|los|las|del|que|por|para|pedido|devolver|devolución|reembolso|reembolsa|quiero|puedo|"
    r"cuánto|cuántos|cuantos|días|dias|mi|una|es|cómo|como|dónde|donde|hola|gracias|tienen|venden|"
    r"zapatos|ropa|cancela|cancelar|envío|envio|dirección|garantía|llegó|llego|nunca|"
    r"aprobado|aprobar|monto|centavos|cliente|primero|seleccione)\b",
    re.IGNORECASE,
)
_SECTION = re.compile(r"\b[A-Z]{2,5}(?:-[A-Z0-9]+)+\b")


def is_spanish(text: str) -> bool:
    if _ACCENTED.search(text):
        return True
    return len({word.lower() for word in _WORDS.findall(text)}) >= 2


def to_english(question: str) -> str:
    text = _translate(
        "Translate the customer's message to English. Keep order ids (like NS-1001), emails, "
        "amounts, and product names exactly. Reply with the translation only.",
        question,
    )
    return text or question


def to_spanish(draft: Draft) -> Draft:
    text = _translate(
        "Translate this support reply to Spanish. Keep every section id in parentheses "
        "(like REF-CATEGORY), order ids, amounts, and emails exactly as written. "
        "Do not add or drop a rule. Reply with the translation only.",
        draft.text,
    )
    if not text:
        return draft
    missing = [section for section in _SECTION.findall(draft.text) if section not in text]
    if missing:
        text = f"{text.rstrip()}\n({', '.join(dict.fromkeys(missing))})"
    return Draft(draft.decision, text, draft.citations, draft.match, draft.steps, draft.run_id, draft.retrieved)


def _translate(instruction: str, text: str) -> str:
    from northstar.agent_model import _load_local_env, _model, reply_text

    _load_local_env()
    if os.environ.get("PYTEST_CURRENT_TEST") or not os.environ.get("GOOGLE_API_KEY"):
        return ""
    try:
        return reply_text(_model().invoke([{"role": "system", "content": instruction}, {"role": "user", "content": text}]))
    except Exception:
        return ""
