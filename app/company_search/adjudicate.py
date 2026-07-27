"""Second-opinion match adjudication, ported from ``adjudicate-matches-llm.ts``.

Candidate capping/id-dropping happens in the router (mirrors the TS
``input.candidates.slice(0, LLM_CANDIDATE_CAP).filter(entry => entry.id)`` — cap first, then
drop id-less entries), so this module receives an already-capped, already-id-filtered
candidate list. Verdict/rankedIds validation, dedup, and the "append unranked candidates to the
end in original order" behavior are ported exactly.

Deviation from TS: the TS returns ``null`` (caller falls back) when verdicts end up empty after
filtering; per the phase-1 contract, an empty ``verdicts`` list is a valid 200 here.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from app.providers.llm.base import LlmMessage, LlmProvider
from app.company_search.guardrails import read_trimmed_string

AdjudicationVerdict = Literal["same", "likely", "different"]

SYSTEM_PROMPT = (
    "You are a second opinion for a vendor master-data steward comparing one vendor record "
    "against candidate hits from an external company registry. For each candidate decide "
    "whether it is the same legal entity. "
    'Return JSON only: { "rankedIds": string[], "verdicts": [ { "id": string, "verdict": '
    '"same" | "likely" | "different", "reason": string } ] }. '
    "rankedIds orders every candidate best-first. Give one short concrete reason per candidate "
    'naming the evidence you used (e.g. "same name, different city"). Never invent facts not '
    'present in the input; if the registry record is sparse, say so and prefer "different" over '
    "guessing. Keep reasons under 25 words. Echo back exactly the ids you were given."
)


def _read_verdict(value: Any) -> AdjudicationVerdict | None:
    text = value.strip().lower() if isinstance(value, str) else None
    if text in ("same", "likely", "different"):
        return text  # type: ignore[return-value]
    return None


async def adjudicate_with_llm(
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
                "deterministicScore": entry.get("deterministicScore"),
                "registryNote": read_trimmed_string(entry.get("registryNote"), 200),
            }
            for entry in candidates
        ],
    }
    messages = [
        LlmMessage(role="system", text=SYSTEM_PROMPT),
        LlmMessage(role="user", text=json.dumps(payload)),
    ]
    result = await provider.complete_json(messages)

    allowed_ids = {entry["id"] for entry in candidates}
    verdicts: list[dict[str, Any]] = []
    seen_verdict_ids: set[str] = set()

    raw_verdicts = result.get("verdicts")
    if isinstance(raw_verdicts, list):
        for entry in raw_verdicts:
            if not isinstance(entry, dict):
                continue
            entry_id = read_trimmed_string(entry.get("id"), 120)
            verdict = _read_verdict(entry.get("verdict"))
            if not entry_id or not verdict or entry_id not in allowed_ids:
                continue
            if entry_id in seen_verdict_ids:
                continue
            seen_verdict_ids.add(entry_id)
            row: dict[str, Any] = {"id": entry_id, "verdict": verdict}
            reason = read_trimmed_string(entry.get("reason"), 200)
            if reason:
                row["reason"] = reason
            verdicts.append(row)

    ranked_ids: list[str] = []
    seen_ranked: set[str] = set()
    raw_ranked = result.get("rankedIds")
    if isinstance(raw_ranked, list):
        for value in raw_ranked:
            rid = read_trimmed_string(value, 120)
            if rid and rid in allowed_ids and rid not in seen_ranked:
                seen_ranked.add(rid)
                ranked_ids.append(rid)

    # Any candidate the model failed to rank keeps its original position at the end, so the
    # AI ordering never silently drops a result from the list.
    for entry in candidates:
        if entry["id"] not in seen_ranked:
            seen_ranked.add(entry["id"])
            ranked_ids.append(entry["id"])

    return {"rankedIds": ranked_ids, "verdicts": verdicts}
