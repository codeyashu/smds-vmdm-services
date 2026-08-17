"""Temporal ranking and supersession across document options."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.documents.validation.types import FieldOption, FreshnessFinding

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y")


def _parse_date(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    iso_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match:
        try:
            return datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            return None
    return None


def _option_date(opt: FieldOption, extraction_meta: dict[str, dict[str, Any]]) -> datetime | None:
    doc_id = opt.document_id or ""
    meta = extraction_meta.get(doc_id) or {}
    for key in ("effectiveDate", "effective_date"):
        parsed = _parse_date(meta.get(key))
        if parsed:
            return parsed
    return None


def _build_extraction_meta(extractions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for extraction in extractions:
        doc_id = str(extraction.get("documentId") or "")
        if not doc_id:
            continue
        meta[doc_id] = {
            "docType": extraction.get("docType"),
            "effectiveDate": extraction.get("effectiveDate") or extraction.get("effective_date"),
            "uploadedAt": extraction.get("uploadedAt") or extraction.get("uploaded_at"),
        }
    return meta


def _authority_rank(logical_id: str | None, doc_type: str) -> int:
    """Lower is higher authority."""
    lid = logical_id or ""
    if lid == "legal_name":
        order = ["IN_CERTIFICATE_OF_INCORPORATION", "IN_GST_CERTIFICATE", "IN_DEED_OF_PARTNERSHIP"]
    elif lid == "trading_name":
        order = ["IN_GST_CERTIFICATE", "IN_PAN_CARD", "IN_CERTIFICATE_OF_INCORPORATION", "IN_ADDRESS_PROOF"]
    elif lid.startswith("bill_to") or lid in {"bill_to_city", "bill_to_street", "bill_to_postal_code"}:
        order = ["IN_ADDRESS_PROOF", "IN_GST_CERTIFICATE", "IN_CERTIFICATE_OF_INCORPORATION"]
    else:
        return 50
    try:
        return order.index(doc_type)
    except ValueError:
        return 40


def correlate_temporal_freshness(
    options: list[FieldOption],
    extractions: list[dict[str, Any]],
    existing_documents: list[dict[str, Any]] | None,
    form_snapshot: dict[str, Any] | None,
) -> list[FreshnessFinding]:
    del form_snapshot  # reserved for stale-form detection in a later pass
    findings: list[FreshnessFinding] = []
    meta = _build_extraction_meta(extractions)

    by_path: dict[str, list[FieldOption]] = {}
    for opt in options:
        by_path.setdefault(opt.path, []).append(opt)

    new_types = {str(e.get("docType") or "") for e in extractions}

    for path, group in by_path.items():
        if len(group) < 2:
            continue
        scored: list[tuple[FieldOption, datetime | None, int]] = []
        for opt in group:
            scored.append((opt, _option_date(opt, meta), _authority_rank(opt.logical_field_id, opt.source_label)))
        scored.sort(
            key=lambda row: (
                row[1] is not None,
                row[1] or datetime.min,
                -row[2],
                row[0].confidence,
            ),
            reverse=True,
        )
        winner, winner_date, _ = scored[0]
        compared = []
        for opt, dt, _auth in scored:
            compared.append(
                {
                    "source": opt.source_label,
                    "optionKey": opt.option_key,
                    "date": dt.date().isoformat() if dt else None,
                }
            )

        superseded_keys = [opt.option_key for opt, _, _ in scored[1:]]
        duplicate_type = any(
            str(existing.get("classifiedDocType") or existing.get("docType") or "") in new_types
            for existing in (existing_documents or [])
        )

        if duplicate_type and len(scored) > 1:
            status = "superseded"
            rationale = (
                f"Newer upload preferred for {winner.label}: {winner.incoming_display} from {winner.source_label}"
                + (f" (dated {winner_date.date().isoformat()})" if winner_date else "")
                + "."
            )
        elif winner_date is None:
            status = "unknown_date"
            rationale = (
                f"Higher-authority source selected for {winner.label}: {winner.source_label} "
                f"({winner.incoming_display}). Document dates unavailable for temporal ranking."
            )
        else:
            status = "current"
            rationale = (
                f"Preferred {winner.incoming_display} from {winner.source_label}"
                + (f" (effective {winner_date.date().isoformat()})" if winner_date else "")
                + " based on document date and authority."
            )

        findings.append(
            FreshnessFinding(
                path=path,
                status=status,
                preferredOptionKey=winner.option_key,
                rationale=rationale,
                comparedDates=compared,
                supersededOptionKeys=superseded_keys,
            )
        )

    return findings
