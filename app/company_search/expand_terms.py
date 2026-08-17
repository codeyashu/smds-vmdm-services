"""Search-term expansion, ported from ``expand-search-terms-llm.ts``.

Server does the max-6-terms cap and the case-insensitive dedup against ``tradingName`` +
``alreadyTried``, exactly as the TS. Per the phase-1 contract, an empty ``terms`` list is a
valid 200 — the TS instead returns ``null`` (fall back to nothing further to try); the router
just returns the empty list directly since there's no local fallback path server-side.
"""

from __future__ import annotations

import json

from app.company_search.guardrails import read_string_list, read_trimmed_string
from app.providers.llm.base import LlmMessage, LlmProvider

# Deliberately small: each extra term is another upstream registry round trip.
MAX_TERMS = 6

SYSTEM_PROMPT = (
    "You widen a company-name search that returned no results in a national business registry. "
    "Given a trading name and country, propose alternative spellings that the registry might "
    "hold: legal-suffix variants (Pvt Ltd / Private Limited / PVT. LTD.), transliterations and "
    "romanization variants, expanded or contracted abbreviations (Intl / International), common "
    'misspellings, and the separate names inside "formerly known as" or "trading as" strings. '
    'Return JSON only: { "terms": string[], "reason": string }. '
    "Each term must be a plausible name for the SAME company — never a different company, never "
    "a generic industry word, never a city or country name on its own. Return at most 6 terms. "
    "If nothing useful can be proposed, return an empty terms array."
)


async def expand_terms_with_llm(
    provider: LlmProvider,
    *,
    trading_name: str,
    iso2_country_code: str | None = None,
    already_tried: list[str] | None = None,
) -> dict[str, object]:
    already_tried = already_tried or []
    trading_name_stripped = trading_name.strip()
    payload = {
        "tradingName": trading_name_stripped,
        "iso2CountryCode": iso2_country_code,
        "alreadyTried": already_tried[:MAX_TERMS],
    }
    messages = [
        LlmMessage(role="system", text=SYSTEM_PROMPT),
        LlmMessage(role="user", text=json.dumps(payload)),
    ]
    result = await provider.complete_json(messages, trace_name="company_search.expand_terms")

    tried = {trading_name_stripped.lower(), *(t.strip().lower() for t in already_tried)}
    terms = [
        term for term in read_string_list(result.get("terms"), MAX_TERMS) if term.lower() not in tried
    ]

    out: dict[str, object] = {"terms": terms}
    reason = read_trimmed_string(result.get("reason"))
    if reason:
        out["reason"] = reason
    return out
