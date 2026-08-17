"""Experimental LLM cross-document consistency check (advisory only)."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from app.documents.validation.types import AdjudicateResponse, DocumentCorroboration, DocumentCorroborationSuggestion
from app.providers.llm.base import LlmMessage
from app.providers.llm.factory import get_llm_provider

CorroborationVerdict = Literal["same", "likely", "different", "insufficient"]

_CORROBORATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["same", "likely", "different", "insufficient"],
        },
        "correlationScore": {"type": "integer"},
        "narrative": {"type": "string"},
        "suggestedOptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "optionKey": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["path", "optionKey"],
                "additionalProperties": False,
            },
        },
        "suggestedAddressCandidateKey": {"type": ["string", "null"]},
    },
    "required": [
        "verdict",
        "correlationScore",
        "narrative",
        "suggestedOptions",
        "suggestedAddressCandidateKey",
    ],
    "additionalProperties": False,
}


def is_document_corroboration_enabled() -> bool:
    return os.environ.get("DOCUMENT_CORROBORATION_ENABLED", "").strip().lower() == "true"


def should_run_document_corroboration(
    extractions: list[dict[str, Any]],
    adjudication: AdjudicateResponse,
) -> bool:
    if not is_document_corroboration_enabled():
        return False
    if len(extractions) >= 2:
        return True
    if len(adjudication.address_candidates) > 1:
        return True
    if adjudication.conflicts:
        return True
    if any(verdict.action == "steward_required" for verdict in adjudication.field_verdicts):
        return True
    return False


def _form_summary(form_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = form_snapshot or {}
    tax_rows = (
        (snapshot.get("taxInformation") or {}).get("taxIdentificationNumbers") or []
        if isinstance(snapshot.get("taxInformation"), dict)
        else []
    )
    tax_ids = [
        str(row.get("taxIdentificationNumber")).strip()
        for row in tax_rows
        if isinstance(row, dict) and row.get("taxIdentificationNumber")
    ]
    addresses = snapshot.get("postalAddresses") if isinstance(snapshot.get("postalAddresses"), list) else []
    bill_to = next(
        (
            row
            for row in addresses
            if isinstance(row, dict) and str(row.get("contactAddressPurposeCode", "")).upper() == "BILL_TO"
        ),
        addresses[0] if addresses and isinstance(addresses[0], dict) else {},
    )
    return {
        "tradingName": snapshot.get("tradingName"),
        "legalName": snapshot.get("legalName"),
        "taxIdentificationNumbers": tax_ids,
        "billToAddress": bill_to if isinstance(bill_to, dict) else {},
    }


def _document_signals(extractions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for extraction in extractions:
        patches = extraction.get("patches") or []
        fields = [
            {
                "path": patch.get("path"),
                "label": patch.get("label"),
                "value": patch.get("value"),
                "confidence": patch.get("confidence"),
            }
            for patch in patches
            if isinstance(patch, dict) and patch.get("path")
        ]
        signals.append(
            {
                "documentId": extraction.get("documentId"),
                "docType": extraction.get("docType"),
                "fields": fields[:40],
            }
        )
    return signals


def _conflict_payload(adjudication: AdjudicateResponse) -> list[dict[str, Any]]:
    options_by_path: dict[str, list[dict[str, Any]]] = {}
    for option in adjudication.options:
        options_by_path.setdefault(option.path, []).append(
            {
                "optionKey": option.option_key,
                "sourceLabel": option.source_label,
                "value": option.incoming_display,
                "confidence": option.confidence,
                "evidenceSnippet": option.evidence_snippet,
            }
        )

    payload: list[dict[str, Any]] = []
    for conflict in adjudication.conflicts:
        verdict = next((row for row in adjudication.field_verdicts if row.path == conflict.path), None)
        payload.append(
            {
                "path": conflict.path,
                "label": conflict.label,
                "logicalFieldId": conflict.logical_field_id,
                "options": options_by_path.get(conflict.path, []),
                "deterministicRecommendedOptionKey": verdict.recommended_option_key if verdict else None,
                "deterministicAction": verdict.action if verdict else None,
            }
        )
    return payload


def _address_payload(adjudication: AdjudicateResponse) -> list[dict[str, Any]]:
    return [
        {
            "candidateKey": candidate.candidate_key,
            "addressRole": candidate.address_role,
            "label": candidate.label,
            "fullAddressText": candidate.full_address_text,
            "sourceDocType": candidate.source_doc_type,
            "recommendedForBillTo": candidate.recommended_for_bill_to,
            "alignmentScore": candidate.alignment_score,
        }
        for candidate in adjudication.address_candidates
    ]


def _build_prompt(
    *,
    country_code: str,
    form_snapshot: dict[str, Any] | None,
    extractions: list[dict[str, Any]],
    adjudication: AdjudicateResponse,
) -> str:
    payload = {
        "countryCode": country_code,
        "formSnapshot": _form_summary(form_snapshot),
        "documents": _document_signals(extractions),
        "conflicts": _conflict_payload(adjudication),
        "addressCandidates": _address_payload(adjudication),
        "bundleSummary": adjudication.bundle_summary,
        "stewardRequiredPaths": [
            verdict.path for verdict in adjudication.field_verdicts if verdict.action == "steward_required"
        ],
    }
    return (
        "You are a vendor master data steward assistant. Assess whether uploaded documents and "
        "the steward-entered form describe the SAME legal entity.\n\n"
        "Rules:\n"
        "- This is an advisory consistency check only — never claim government registry proof.\n"
        "- Prefer authoritative doc types (GST certificate, CoI) over address proof for legal name.\n"
        "- Distinguish trading name variants (Pvt Ltd vs Private Limited) from different entities.\n"
        "- For address branches, prefer principal/registered office for bill-to unless evidence says otherwise.\n"
        "- suggestedOptions must use optionKey values exactly as provided in conflicts.\n"
        "- suggestedAddressCandidateKey must match a candidateKey from addressCandidates or be null.\n"
        "- Use insufficient when evidence is too sparse.\n\n"
        f"Bundle context:\n{json.dumps(payload, indent=2)}\n"
    )


def _sanitize_suggestions(
    raw: dict[str, Any],
    adjudication: AdjudicateResponse,
) -> tuple[list[dict[str, str]], str | None]:
    valid_paths = {option.path: {option.option_key for option in adjudication.options} for option in adjudication.options}
    valid_address_keys = {candidate.candidate_key for candidate in adjudication.address_candidates}

    suggestions: list[dict[str, str]] = []
    for entry in raw.get("suggestedOptions") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        option_key = str(entry.get("optionKey") or "").strip()
        if not path or not option_key:
            continue
        if option_key not in valid_paths.get(path, set()):
            continue
        reason = str(entry.get("reason") or "").strip()
        suggestions.append({"path": path, "optionKey": option_key, "reason": reason})

    address_key = raw.get("suggestedAddressCandidateKey")
    suggested_address: str | None = None
    if isinstance(address_key, str) and address_key.strip():
        normalized = address_key.strip()
        if normalized in valid_address_keys:
            suggested_address = normalized

    return suggestions, suggested_address


async def corroborate_documents_async(
    *,
    country_code: str,
    extractions: list[dict[str, Any]],
    form_snapshot: dict[str, Any] | None,
    adjudication: AdjudicateResponse,
) -> DocumentCorroboration:
    if not should_run_document_corroboration(extractions, adjudication):
        return DocumentCorroboration(
            skipped=True,
            skipReason="Document corroboration not required for this bundle.",
        )

    provider = get_llm_provider()
    if provider is None:
        return DocumentCorroboration(
            skipped=True,
            skipReason="LLM provider not configured.",
        )

    messages = [
        LlmMessage(
            role="system",
            text=(
                "Return JSON only. correlationScore is 0-100. narrative is 2-4 sentences for a steward."
            ),
        ),
        LlmMessage(
            role="user",
            text=_build_prompt(
                country_code=country_code,
                form_snapshot=form_snapshot,
                extractions=extractions,
                adjudication=adjudication,
            ),
        ),
    ]

    try:
        raw = await provider.complete_json(
            messages,
            schema=_CORROBORATION_SCHEMA,
            timeout_s=25.0,
            trace_name="documents.entity_corroboration",
        )
    except Exception:  # noqa: BLE001
        return DocumentCorroboration(
            skipped=True,
            skipReason="Document corroboration LLM call failed.",
        )

    if not isinstance(raw, dict):
        return DocumentCorroboration(
            skipped=True,
            skipReason="Document corroboration returned no result.",
        )

    verdict = str(raw.get("verdict") or "insufficient")
    if verdict not in ("same", "likely", "different", "insufficient"):
        verdict = "insufficient"

    score_raw = raw.get("correlationScore")
    try:
        correlation_score = max(0, min(100, int(score_raw)))
    except (TypeError, ValueError):
        correlation_score = None

    if verdict == "insufficient":
        return DocumentCorroboration(
            skipped=False,
            verdict="insufficient",
            narrative=str(raw.get("narrative") or "").strip() or None,
            correlationScore=correlation_score,
        )

    suggestions, suggested_address = _sanitize_suggestions(raw, adjudication)

    return DocumentCorroboration(
        skipped=False,
        verdict=verdict,  # type: ignore[arg-type]
        narrative=str(raw.get("narrative") or "").strip() or None,
        correlationScore=correlation_score,
        suggestedOptions=[
            DocumentCorroborationSuggestion(
                path=row["path"],
                optionKey=row["optionKey"],
                reason=row.get("reason") or None,
            )
            for row in suggestions
        ],
        suggestedAddressCandidateKey=suggested_address,
    )
