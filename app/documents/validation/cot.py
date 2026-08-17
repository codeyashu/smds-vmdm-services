"""Build auditable chain-of-thought traces for bundle adjudication."""

from __future__ import annotations

from app.documents.validation.types import BundleCheck, CotStep, FieldConflict, FieldOption, FieldVerdict


def build_cot_trace(
    options: list[FieldOption],
    conflicts: list[FieldConflict],
    bundle_checks: list[BundleCheck],
    field_verdicts: list[FieldVerdict],
) -> list[CotStep]:
    steps: list[CotStep] = []
    step = 1

    for opt in options:
        steps.append(
            CotStep(
                step=step,
                kind="observe",
                message=f"{opt.source_label}: {opt.label} = {opt.incoming_display}",
                refs=[opt.option_key],
            )
        )
        step += 1

    for check in bundle_checks:
        if check.status == "skip":
            continue
        steps.append(
            CotStep(
                step=step,
                kind="rule",
                message=check.message or check.id,
                refs=check.logical_field_ids or check.document_ids,
            )
        )
        step += 1

    for conflict in conflicts:
        steps.append(
            CotStep(
                step=step,
                kind="compare",
                message=f"Conflict on {conflict.label}: {len(conflict.option_keys)} candidate values.",
                refs=conflict.option_keys,
            )
        )
        step += 1

    for verdict in field_verdicts:
        steps.append(
            CotStep(
                step=step,
                kind="recommend",
                message=verdict.reason or f"{verdict.label}: {verdict.action}",
                refs=[verdict.recommended_option_key or verdict.path],
            )
        )
        step += 1

    return steps
