"""Template-based English summary for bundle adjudication."""

from __future__ import annotations

from typing import Any

from app.documents.validation.types import BundleCheck, FieldConflict, FieldOption, FieldVerdict


def _doc_labels(extractions: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for extraction in extractions:
        doc_type = str(extraction.get("docType") or "document")
        labels.append(doc_type.replace("_", " "))
    return labels


def build_bundle_summary(
    extractions: list[dict[str, Any]],
    options: list[FieldOption],
    conflicts: list[FieldConflict],
    bundle_checks: list[BundleCheck],
    field_verdicts: list[FieldVerdict],
) -> str:
    if not extractions:
        return "No documents were processed."

    doc_labels = _doc_labels(extractions)
    unique_labels = list(dict.fromkeys(doc_labels))
    count = len(extractions)

    if count == 1:
        opening = f"One document was processed ({unique_labels[0]})."
    else:
        opening = (
            f"{count} documents were processed: {', '.join(unique_labels[:4])}"
            + ("." if len(unique_labels) <= 4 else ", and others.")
        )

    parts: list[str] = [opening]

    conflict_count = len(conflicts)
    steward_count = sum(1 for v in field_verdicts if v.action == "steward_required")
    accept_count = sum(1 for v in field_verdicts if v.action == "accept")
    reject_count = sum(1 for v in field_verdicts if v.action == "reject")

    form_mismatches = [c for c in bundle_checks if c.id.startswith("form_mismatch_")]
    duplicate_docs = [c for c in bundle_checks if c.id.startswith("duplicate_doc_type_")]
    blocking = [c for c in bundle_checks if c.status == "fail" and c.severity == "block"]

    if conflict_count > 0:
        conflict_names = ", ".join(c.label for c in conflicts[:3])
        suffix = " Review the highlighted fields and pick one source per field." if conflict_count else ""
        parts.append(
            f"{conflict_count} field{'s' if conflict_count != 1 else ''} disagree across documents "
            f"({conflict_names}).{suffix}"
        )

    if form_mismatches:
        parts.append(
            f"{len(form_mismatches)} extracted value{'s' if len(form_mismatches) != 1 else ''} "
            "differ from what is already on the form — confirm before applying."
        )

    if duplicate_docs:
        parts.append(
            "Some document types were uploaded again while earlier copies exist on this vendor."
        )

    if blocking:
        parts.append(
            f"{len(blocking)} blocking validation issue{'s' if len(blocking) != 1 else ''} "
            "must be resolved before those fields can be applied."
        )

    if conflict_count == 0 and not form_mismatches and not blocking:
        if accept_count > 0:
            parts.append(
                f"{accept_count} field{'s' if accept_count != 1 else ''} are consistent across documents "
                "and are pre-selected for apply."
            )
        else:
            parts.append("Review extracted values before applying.")

    if steward_count > 0 and conflict_count > 0:
        parts.append("Your choice is required where sources disagree.")

    if reject_count > 0:
        parts.append(
            f"{reject_count} field{'s' if reject_count != 1 else ''} cannot be applied from these documents."
        )

    return " ".join(p.strip() for p in parts if p.strip())
