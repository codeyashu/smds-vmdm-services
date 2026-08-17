"""Compare extracted values with the steward's current form snapshot."""

from __future__ import annotations

from typing import Any

from app.documents.validation.normalize import fuzzy_ratio, normalize_identifier, normalize_name
from app.documents.validation.types import BundleCheck, FieldOption


def _read_path(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _values_equivalent(form_value: Any, incoming: Any, path: str) -> bool:
    if form_value is None or incoming is None:
        return False
    if isinstance(form_value, bool) or isinstance(incoming, bool):
        return bool(form_value) == bool(incoming)
    form_text = str(form_value).strip()
    incoming_text = str(incoming).strip()
    if not form_text or not incoming_text:
        return False
    if "taxIdentification" in path or path.endswith("gstin") or "postalCode" in path:
        return normalize_identifier(form_text) == normalize_identifier(incoming_text)
    return fuzzy_ratio(form_text, incoming_text) >= 0.92


def compare_form_snapshot(
    options: list[FieldOption],
    form_snapshot: dict[str, Any] | None,
) -> list[BundleCheck]:
    if not form_snapshot:
        return []

    checks: list[BundleCheck] = []
    seen_paths: set[str] = set()

    for opt in options:
        if opt.path in seen_paths:
            continue
        seen_paths.add(opt.path)

        current = _read_path(form_snapshot, opt.path)
        if current is None or str(current).strip() == "":
            continue

        if _values_equivalent(current, opt.incoming_value, opt.path):
            continue

        checks.append(
            BundleCheck(
                id=f"form_mismatch_{opt.path}",
                status="warn",
                severity="warn",
                message=(
                    f"{opt.label} on the form is {str(current).strip()}, but "
                    f"{opt.source_label} shows {opt.incoming_display}. "
                    "Confirm which value is correct before applying."
                ),
                paths=[opt.path],
                logicalFieldIds=[opt.logical_field_id] if opt.logical_field_id else [],
                documentIds=[opt.document_id] if opt.document_id else [],
            )
        )

    return checks
