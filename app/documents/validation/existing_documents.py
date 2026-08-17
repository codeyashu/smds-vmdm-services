"""Warnings when new uploads overlap documents already on the vendor record."""

from __future__ import annotations

from typing import Any

from app.documents.validation.types import BundleCheck, CotStep


def check_existing_documents(
    extractions: list[dict[str, Any]],
    existing_documents: list[dict[str, Any]] | None,
) -> tuple[list[BundleCheck], list[CotStep]]:
    if not existing_documents:
        return [], []

    checks: list[BundleCheck] = []
    cot_steps: list[CotStep] = []
    step = 1

    new_types = {str(e.get("docType") or "") for e in extractions}
    new_types.discard("")

    for existing in existing_documents:
        classified = str(existing.get("classifiedDocType") or existing.get("docType") or "").strip()
        filename = str(existing.get("filename") or "document").strip()
        uploaded_at = str(existing.get("uploadedAt") or existing.get("uploaded_at") or "").strip()

        if not classified:
            continue

        label = classified.replace("_", " ")
        observe_msg = f"Vendor already has {label} on file ({filename}"
        if uploaded_at:
            observe_msg += f", uploaded {uploaded_at}"
        observe_msg += ")."

        cot_steps.append(
            CotStep(step=step, kind="observe", message=observe_msg, refs=[classified])
        )
        step += 1

        if classified in new_types:
            checks.append(
                BundleCheck(
                    id=f"duplicate_doc_type_{classified}",
                    status="warn",
                    severity="warn",
                    message=(
                        f"You uploaded another {label} while one is already stored on this vendor "
                        f"({filename}). Review both if values should match."
                    ),
                    paths=[],
                    logicalFieldIds=[],
                    documentIds=[],
                )
            )

    return checks, cot_steps
