"""LLM natural-language query parsing, ported from ``llm-parse.ts``.

Only the LLM call + zod-equivalent (pydantic) validation + one repair round-trip are ported,
plus the country-name->ISO2 and vendor-status uppercasing normalization helpers that live in
the same TS file. ``heuristic-parse.ts`` is deliberately NOT ported — it is pure deterministic
pre-filtering with no AI content and stays in the portal.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.nl_search.context import NlSearchParseContext, build_system_prompt
from app.nl_search.models import NlParseResult, NlSearchParams
from app.providers.llm.base import LlmMessage, LlmProvider

COUNTRY_NAME_TO_ISO2: dict[str, str] = {
    "india": "IN",
    "indonesia": "ID",
    "brazil": "BR",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
    "china": "CN",
    "denmark": "DK",
    "sweden": "SE",
    "norway": "NO",
    "poland": "PL",
    "romania": "RO",
    "czech": "CZ",
    "czechia": "CZ",
    "slovakia": "SK",
    "switzerland": "CH",
    "netherlands": "NL",
    "belgium": "BE",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "united kingdom": "GB",
}

_ISO2_RE = re.compile(r"^[A-Za-z]{2}$")


def _normalize_country(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if _ISO2_RE.match(trimmed):
        return trimmed.upper()
    return COUNTRY_NAME_TO_ISO2.get(trimmed.lower())


def _normalize_vendor_status(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed.upper() if trimmed else None


def _normalize_llm_raw(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    country = _normalize_country(raw.get("country"))
    if country:
        normalized["country"] = country
    vendor_status = _normalize_vendor_status(raw.get("vendorStatus"))
    if vendor_status:
        normalized["vendorStatus"] = vendor_status
    return normalized


async def parse_natural_language_with_llm(
    provider: LlmProvider,
    query: str,
    context: NlSearchParseContext | None = None,
) -> NlParseResult:
    system_prompt = build_system_prompt(context)
    messages = [
        LlmMessage(role="system", text=system_prompt),
        LlmMessage(role="user", text=query),
    ]

    raw = await provider.complete_json(messages, trace_name="nl_search.parse")

    try:
        parsed = NlSearchParams.model_validate(_normalize_llm_raw(raw))
    except ValidationError as exc:
        # One repair attempt: hand the bad output + validation error back to the model instead
        # of dropping straight to the heuristic fallback (which lives in the portal).
        repaired = await provider.complete_json(
            [
                *messages,
                LlmMessage(role="assistant", text=json.dumps(raw)),
                LlmMessage(
                    role="user",
                    text=(
                        f"That JSON did not match the required schema: {exc}. Return corrected "
                        "JSON only, same shape as instructed."
                    ),
                ),
            ],
            trace_name="nl_search.parse_repair",
        )
        parsed = NlSearchParams.model_validate(_normalize_llm_raw(repaired))

    return NlParseResult(**parsed.model_dump(), source="llm", confidence="high")
