"""LLM cross-source entity corroboration for TrustLens (read-only, no web crawl)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.providers.llm.base import LlmMessage
from app.providers.llm.factory import get_llm_provider
from app.web_trust.scoring import build_vendor_field_evidence, compute_overall_match
from app.web_trust.types import WebMatchedRecord

_CORROBORATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["same", "likely", "different", "insufficient"],
        },
        "correlationScore": {"type": "integer"},
        "corroboratedFields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "conflictingFields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "narrative": {"type": "string"},
    },
    "required": [
        "verdict",
        "correlationScore",
        "corroboratedFields",
        "conflictingFields",
        "narrative",
    ],
    "additionalProperties": False,
}


def _build_prompt(request_dict: dict[str, Any], matched_records: list[WebMatchedRecord]) -> str:
    entered = {
        "tradingName": request_dict.get("tradingName"),
        "legalName": request_dict.get("legalName"),
        "taxIds": request_dict.get("taxIdentificationNumbers"),
        "address": request_dict.get("address"),
        "country": request_dict.get("iso2CountryCode"),
        "website": request_dict.get("website"),
    }
    sources = []
    for record in matched_records:
        if record.connectorId == "bill_to_address":
            continue
        sources.append(
            {
                "source": record.displayName,
                "type": record.sourceType,
                "mode": record.verificationMode,
                "extracted": record.extractedFields,
                "fieldScores": [
                    {"field": entry.field, "score": entry.score, "status": entry.status}
                    for entry in record.fieldEvidence
                    if entry.status != "unknown"
                ],
            }
        )
    return (
        "You are a vendor master data steward assistant. Assess whether external signals "
        "describe the SAME legal entity as the steward-entered vendor record.\n\n"
        "Rules:\n"
        "- Tax ID substring match alone is NOT enough — require name and/or address alignment.\n"
        "- Format-only checks (checksum) are weaker than live registry or directory hits.\n"
        "- Flag 'different' when names or cities clearly refer to another company.\n"
        "- Use 'insufficient' when sources lack identity fields.\n\n"
        f"Entered record:\n{json.dumps(entered, indent=2)}\n\n"
        f"External signals:\n{json.dumps(sources, indent=2)}\n"
    )


async def _corroborate_async(
    request_dict: dict[str, Any],
    matched_records: list[WebMatchedRecord],
) -> dict[str, Any] | None:
    provider = get_llm_provider()
    if provider is None:
        return None
    if len(matched_records) < 2:
        return None

    messages = [
        LlmMessage(
            role="system",
            text=(
                "Return JSON only. Score correlation 0-100. "
                "corroboratedFields uses: tradingName, tax, city, street, postalCode, country."
            ),
        ),
        LlmMessage(role="user", text=_build_prompt(request_dict, matched_records)),
    ]
    try:
        return await provider.complete_json(
            messages,
            schema=_CORROBORATION_SCHEMA,
            timeout_s=25.0,
            trace_name="trustlens.llm_corroboration",
        )
    except Exception:  # noqa: BLE001
        return None


async def corroborate_with_llm_async(
    request_dict: dict[str, Any],
    matched_records: list[WebMatchedRecord],
) -> WebMatchedRecord | None:
    result = await _corroborate_async(request_dict, matched_records)
    if not result:
        return None

    verdict = str(result.get("verdict") or "insufficient")
    if verdict == "insufficient":
        return None

    corroborated = [str(f) for f in result.get("corroboratedFields") or []]
    extracted: dict[str, Any] = {"iso2CountryCode": request_dict.get("iso2CountryCode")}
    for record in matched_records:
        for field in corroborated:
            value = (record.extractedFields or {}).get(field)
            if field == "tax":
                value = value or (record.extractedFields or {}).get("taxIdentificationNumber")
            if value and field not in extracted:
                if field == "tax":
                    extracted["taxIdentificationNumber"] = value
                else:
                    extracted[field] = value

    field_evidence = build_vendor_field_evidence(request_dict, extracted)
    match_score, _, _ = compute_overall_match(field_evidence)

    return WebMatchedRecord(
        id="llm-corroboration",
        sourceType="other",
        verificationMode="web_enrichment",
        sourceUrl=None,
        connectorId="llm_corroboration",
        displayName="AI cross-source corroboration",
        extractedFields=extracted,
        matchScore=int(result.get("correlationScore") or match_score),
        fieldEvidence=field_evidence,
        llmVerdict=verdict if verdict in ("same", "likely", "different") else "likely",
        llmReason=str(result.get("narrative") or ""),
        authorityWeight=0.5,
    )


def corroborate_with_llm(
    request_dict: dict[str, Any],
    matched_records: list[WebMatchedRecord],
) -> WebMatchedRecord | None:
    """Sync entry for scripts/tests — do not call from an async request handler."""
    return asyncio.run(corroborate_with_llm_async(request_dict, matched_records))
