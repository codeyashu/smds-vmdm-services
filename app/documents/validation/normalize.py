"""Text normalization for cross-document comparison."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LEGAL_SUFFIXES = (
    "private limited",
    "pvt ltd",
    "pvt. ltd.",
    "limited",
    "ltd",
    "llp",
    "inc",
    "corporation",
    "corp",
)


def normalize_identifier(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "")).upper()


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = text.casefold().strip()
    for suffix in _LEGAL_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip(" ,.-")
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


def normalize_address_line(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).casefold()
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


def fuzzy_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz

        return fuzz.token_sort_ratio(a, b) / 100.0
    except ImportError:
        na, nb = normalize_name(a), normalize_name(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        if shorter in longer:
            return len(shorter) / len(longer)
        return 0.0
