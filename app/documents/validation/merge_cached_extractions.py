"""Merge attachment extraction caches into adjudication bundles (lazy re-extract)."""

from __future__ import annotations

from typing import Any


def _cache_row(existing: dict[str, Any]) -> dict[str, Any] | None:
    cache = existing.get("extractionCache") or existing.get("extraction_cache")
    return cache if isinstance(cache, dict) else None


def _synthetic_extraction(existing: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any] | None:
    doc_type = str(
        cache.get("docType")
        or cache.get("doc_type")
        or existing.get("classifiedDocType")
        or existing.get("classified_doc_type")
        or existing.get("docType")
        or existing.get("doc_type")
        or ""
    ).strip()
    if not doc_type:
        return None

    filename = str(existing.get("filename") or "cached").strip()
    doc_id = f"cached:{doc_type}:{filename}"

    patches_summary = cache.get("patchesSummary") or cache.get("patches_summary") or {}
    patches: list[dict[str, Any]] = []
    if isinstance(patches_summary, dict):
        for path, value in patches_summary.items():
            if not path or str(path).startswith("_unmapped"):
                continue
            patches.append(
                {
                    "path": str(path),
                    "value": value,
                    "label": str(path),
                    "confidence": 0.85,
                    "preSelected": False,
                    "regexOk": True,
                }
            )

    address_candidates = cache.get("addressCandidates") or cache.get("address_candidates") or []
    if not isinstance(address_candidates, list):
        address_candidates = []

    return {
        "documentId": doc_id,
        "docType": doc_type,
        "patches": patches,
        "warnings": ["Restored from attachment extraction cache (no re-extract)."],
        "addressCandidates": address_candidates,
        "effectiveDate": cache.get("effectiveDate") or cache.get("effective_date"),
    }


def merge_cached_extractions(
    extractions: list[dict[str, Any]],
    existing_documents: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Append cached extractions for doc types not present in the live batch."""
    if not existing_documents:
        return extractions, []

    merged = list(extractions)
    active_types = {str(row.get("docType") or row.get("doc_type") or "") for row in extractions}
    active_types.discard("")
    active_ids = {str(row.get("documentId") or row.get("document_id") or "") for row in extractions}
    active_ids.discard("")

    notes: list[str] = []
    for existing in existing_documents:
        if not isinstance(existing, dict):
            continue
        cache = _cache_row(existing)
        if not cache:
            continue
        synthetic = _synthetic_extraction(existing, cache)
        if not synthetic:
            continue
        doc_type = str(synthetic["docType"])
        doc_id = str(synthetic["documentId"])
        if doc_type in active_types or doc_id in active_ids:
            continue
        merged.append(synthetic)
        active_types.add(doc_type)
        active_ids.add(doc_id)
        notes.append(f"Included cached extraction for {doc_type} ({existing.get('filename', 'document')}).")

    return merged, notes
