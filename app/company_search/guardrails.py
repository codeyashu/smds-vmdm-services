"""Shared safety rails for the company-search LLM helpers, ported from the portal's
``src/lib/company-search/llm-guardrails.ts``.

The portal version wraps calls in a soft timeout that degrades to ``null`` on any failure —
that behavior belongs to the caller here (the ``app/api/v1/company_search.py`` router turns
any exception into a 502), so only the pure value-shaping helpers are ported: score clamping,
trimmed-string reading, and deduplicated/capped string lists.
"""

from __future__ import annotations

import math
from typing import Any

# Upper bound on how many registry hits are ever sent to the model in one call.
LLM_CANDIDATE_CAP = 10


def _round_half_up(value: float) -> int:
    """Match JS ``Math.round`` (rounds .5 away from zero on the positive side), rather than
    Python's banker's rounding (``round(2.5) == 2``)."""
    return math.floor(value + 0.5)


def clamp_score(value: Any) -> int | None:
    """Coerce anything the model returns into an integer 0-100, or ``None``."""
    if isinstance(value, bool):
        return None
    numeric: float
    if isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return None
    elif isinstance(value, (int, float)):
        numeric = float(value)
    else:
        return None
    if not math.isfinite(numeric):
        return None
    return max(0, min(100, _round_half_up(numeric)))


def read_trimmed_string(value: Any, max_length: int = 200) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:max_length]


def read_string_list(value: Any, limit: int, max_length: int = 200) -> list[str]:
    """Deduplicated (case-insensitive), trimmed, length-capped string list."""
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for entry in value:
        text = read_trimmed_string(entry, max_length)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out
