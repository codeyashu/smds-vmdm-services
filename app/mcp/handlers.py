"""In-process MCP read-tool handlers (adjudication, address reconcile)."""

from __future__ import annotations

from typing import Any

from app.documents.validation.adjudicate import adjudicate_bundle
from app.documents.validation.address_reconcile import reconcile_address_candidates
from app.documents.validation.merge_cached_extractions import merge_cached_extractions


def _extractions_from_cache(existing_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged, _ = merge_cached_extractions([], existing_documents)
    return merged


async def adjudicate_documents_handler(args: dict[str, Any]) -> dict[str, Any]:
    payload = args.get("payload") or args.get("body") or args
    country = str(payload.get("countryCode") or payload.get("country_code") or "IN")
    extractions = list(payload.get("extractions") or [])
    form_snapshot = payload.get("formSnapshot") or payload.get("form_snapshot") or {}
    existing = payload.get("existingDocuments") or payload.get("existing_documents") or []
    merged, notes = merge_cached_extractions(extractions, existing)
    result = adjudicate_bundle(country, merged, form_snapshot, existing)
    out = result.as_dict()
    if notes:
        out["warnings"] = list(out.get("warnings") or []) + notes
    return out


async def get_vendor_document_extractions_handler(args: dict[str, Any]) -> dict[str, Any]:
    payload = args.get("payload") or args.get("body") or args
    existing = payload.get("existingDocuments") or payload.get("existing_documents") or []
    extractions = _extractions_from_cache(existing if isinstance(existing, list) else [])
    return {"extractions": extractions, "count": len(extractions)}


async def reconcile_address_candidates_handler(args: dict[str, Any]) -> dict[str, Any]:
    payload = args.get("payload") or args.get("body") or args
    candidates = payload.get("addressCandidates") or payload.get("address_candidates") or []
    form_snapshot = payload.get("formSnapshot") or payload.get("form_snapshot") or {}
    return reconcile_address_candidates(candidates, form_snapshot)


async def resolve_field_conflicts_handler(args: dict[str, Any]) -> dict[str, Any]:
    payload = args.get("payload") or args.get("body") or args
    adjudication = payload.get("adjudication")
    path = payload.get("path")

    if isinstance(adjudication, dict):
        verdicts = adjudication.get("fieldVerdicts") or []
        conflicts = adjudication.get("conflicts") or []
        options = adjudication.get("options") or []

        if path:
            verdict = next((row for row in verdicts if row.get("path") == path), None)
            conflict = next((row for row in conflicts if row.get("path") == path), None)
            option_keys = conflict.get("optionKeys") if conflict else []
            candidates = [row for row in options if row.get("optionKey") in (option_keys or [])]
            return {
                "path": path,
                "verdict": verdict,
                "conflict": conflict,
                "candidates": candidates,
            }

        return {
            "conflicts": conflicts,
            "fieldVerdicts": verdicts,
            "requiresSteward": [
                row.get("path")
                for row in verdicts
                if row.get("action") == "steward_required" and row.get("path")
            ],
        }

    country = str(payload.get("countryCode") or payload.get("country_code") or "IN")
    extractions = list(payload.get("extractions") or [])
    form_snapshot = payload.get("formSnapshot") or payload.get("form_snapshot") or {}
    existing = payload.get("existingDocuments") or payload.get("existing_documents") or []
    merged, _ = merge_cached_extractions(extractions, existing)
    result = adjudicate_bundle(country, merged, form_snapshot, existing)
    verdicts = [row.model_dump(by_alias=True) for row in result.field_verdicts]
    conflicts = [row.model_dump(by_alias=True) for row in result.conflicts]
    return {
        "conflicts": conflicts,
        "fieldVerdicts": verdicts,
        "requiresSteward": [row.path for row in result.field_verdicts if row.action == "steward_required"],
    }
