"""Semantic name/address similarity scoring, ported from ``semantic-similarity-llm.ts``.

Candidate capping/id-dropping and the tradingName/address blank check happen in the router
(mirrors the TS ordering). Score clamping uses the shared ``clamp_score`` guardrail. Deviation
from TS: an empty result list is a valid 200 here (the TS returns ``null`` when the list ends up
empty, since it has a local fallback path the server side doesn't need).
"""

from __future__ import annotations

import json
from typing import Any

from app.company_search.guardrails import clamp_score, read_trimmed_string
from app.providers.llm.base import LlmMessage, LlmProvider

SYSTEM_PROMPT = (
    "You judge whether company names and addresses refer to the same real-world entity, for a "
    "vendor master-data steward. Edit distance already handles typos; your job is the cases it "
    'cannot see: transliteration, romanization, abbreviation ("Intl" = "International", '
    '"MLSIPL" as an acronym of the full name), legal-suffix equivalence, "formerly known as" '
    "renames, and addresses written in a different order or with local abbreviations. "
    'Return JSON only: { "candidates": [ { "id": string, "nameScore": 0-100, "addressScore": '
    '0-100, "note": string } ] }. '
    "Score 100 only when you are confident it is the same entity; score low when the names "
    "merely share a generic industry word. Echo back the exact ids you were given. Keep each "
    "note under 20 words."
)


async def similarity_with_llm(
    provider: LlmProvider,
    *,
    trading_name: str | None,
    address: str | None,
    iso2_country_code: str | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "vendor": {
            "tradingName": read_trimmed_string(trading_name, 300),
            "address": read_trimmed_string(address, 300),
            "iso2CountryCode": iso2_country_code,
        },
        "candidates": [
            {
                "id": entry["id"],
                "companyName": read_trimmed_string(entry.get("companyName"), 300),
                "address": read_trimmed_string(entry.get("address"), 300),
            }
            for entry in candidates
        ],
    }
    messages = [
        LlmMessage(role="system", text=SYSTEM_PROMPT),
        LlmMessage(role="user", text=json.dumps(payload)),
    ]
    result = await provider.complete_json(messages, trace_name="company_search.similarity")

    raw_candidates = result.get("candidates")
    if not isinstance(raw_candidates, list):
        return {"candidates": []}

    allowed_ids = {entry["id"] for entry in candidates}
    out: list[dict[str, Any]] = []
    for entry in raw_candidates:
        if not isinstance(entry, dict):
            continue
        entry_id = read_trimmed_string(entry.get("id"), 120)
        if not entry_id or entry_id not in allowed_ids:
            continue
        name_score = clamp_score(entry.get("nameScore"))
        address_score = clamp_score(entry.get("addressScore"))
        if name_score is None and address_score is None:
            continue
        row: dict[str, Any] = {"id": entry_id}
        if name_score is not None:
            row["nameScore"] = name_score
        if address_score is not None:
            row["addressScore"] = address_score
        note = read_trimmed_string(entry.get("note"), 160)
        if note:
            row["note"] = note
        out.append(row)

    return {"candidates": out}
