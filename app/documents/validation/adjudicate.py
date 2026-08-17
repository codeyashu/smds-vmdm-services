"""Multi-document bundle adjudication — main entry."""

from __future__ import annotations

from typing import Any

from app.documents.playbook.config_store import load_country_playbook
from app.documents.validation.address_candidates import collect_address_candidates
from app.documents.validation.address_reconcile import reconcile_address_candidates
from app.documents.validation.bundle_rules import has_blocking_failure, run_bundle_rules
from app.documents.validation.cot import build_cot_trace
from app.documents.validation.evidence_format import format_accept_summary, format_conflict_summary
from app.documents.validation.existing_documents import check_existing_documents
from app.documents.validation.form_compare import compare_form_snapshot
from app.documents.validation.merge_cached_extractions import merge_cached_extractions
from app.documents.validation.normalize import fuzzy_ratio, normalize_name
from app.documents.validation.options import flatten_extractions_to_options
from app.documents.validation.summary import build_bundle_summary
from app.documents.validation.temporal_correlate import correlate_temporal_freshness
from app.documents.validation.types import (
    AddressCandidate,
    AddressReconciliation,
    AdjudicateResponse,
    FieldConflict,
    FieldOption,
    FieldVerdict,
)


def detect_conflicts(options: list[FieldOption]) -> list[FieldConflict]:
    by_path: dict[str, list[FieldOption]] = {}
    for opt in options:
        by_path.setdefault(opt.path, []).append(opt)

    conflicts: list[FieldConflict] = []
    for path, group in by_path.items():
        distinct = {str(o.incoming_value) for o in group if o.incoming_value is not None}
        if len(group) > 1 and len(distinct) > 1:
            conflicts.append(
                FieldConflict(
                    path=path,
                    label=group[0].label,
                    logicalFieldId=group[0].logical_field_id,
                    optionKeys=[o.option_key for o in group],
                )
            )
    return conflicts


def _clear_preselect_on_blocks(options: list[FieldOption], checks: list) -> list[FieldOption]:
    if not has_blocking_failure(checks):
        return options
    blocked_paths = {c.paths[0] for c in checks if c.status == "fail" and c.paths}
    blocked_logical = set()
    for c in checks:
        if c.status == "fail":
            blocked_logical.update(c.logical_field_ids)
    updated: list[FieldOption] = []
    for opt in options:
        if opt.path in blocked_paths or (opt.logical_field_id and opt.logical_field_id in blocked_logical):
            updated.append(opt.model_copy(update={"pre_selected": False}))
        else:
            updated.append(opt)
    return updated


def _pick_conflict_winner(
    group: list[FieldOption],
    freshness_by_path: dict[str, str | None],
    name_threshold: float,
) -> FieldOption | None:
    if not group:
        return None
    preferred_key = freshness_by_path.get(group[0].path)
    if preferred_key:
        for opt in group:
            if opt.option_key == preferred_key:
                return opt
    # Subset street: prefer longer value when one contains the other
    if group[0].logical_field_id in {"bill_to_street", "bill_to_city"} or group[0].path.endswith("streetName"):
        sorted_by_len = sorted(group, key=lambda o: len(str(o.incoming_value or "")), reverse=True)
        top, second = sorted_by_len[0], sorted_by_len[1] if len(sorted_by_len) > 1 else None
        if second:
            a = str(top.incoming_value or "")
            b = str(second.incoming_value or "")
            if a and b and (normalize_name(a) in normalize_name(b) or normalize_name(b) in normalize_name(a)):
                return top
    # Name fields: if fuzzy match above threshold, pick highest authority/confidence
    if group[0].logical_field_id in {"trading_name", "legal_name"}:
        base = str(group[0].incoming_value or "")
        close = [o for o in group if fuzzy_ratio(base, str(o.incoming_value or "")) >= name_threshold * 100]
        if close:
            return sorted(close, key=lambda o: o.confidence, reverse=True)[0]
    return sorted(group, key=lambda o: o.confidence, reverse=True)[0]


def build_field_verdicts(
    options: list[FieldOption],
    conflicts: list[FieldConflict],
    checks: list,
    name_threshold: float,
    freshness_by_path: dict[str, str | None] | None = None,
) -> list[FieldVerdict]:
    verdicts: list[FieldVerdict] = []
    conflict_paths = {c.path for c in conflicts}
    freshness_by_path = freshness_by_path or {}

    for conflict in conflicts:
        group = [o for o in options if o.option_key in conflict.option_keys]
        winner = _pick_conflict_winner(group, freshness_by_path, name_threshold)
        candidates = "; ".join(f"{o.source_label}: {o.incoming_display}" for o in group)
        fuzzy_close = False
        if len(group) >= 2:
            vals = [str(o.incoming_value or "") for o in group]
            fuzzy_close = any(
                fuzzy_ratio(vals[i], vals[j]) >= name_threshold * 100
                for i in range(len(vals))
                for j in range(i + 1, len(vals))
            )
        action = "suggest" if fuzzy_close and winner else "steward_required"
        reason = format_conflict_summary(winner, conflict.label, candidates)
        evidence_summary = reason
        verdicts.append(
            FieldVerdict(
                path=conflict.path,
                label=conflict.label,
                logicalFieldId=conflict.logical_field_id,
                action=action,
                reason=reason,
                evidenceSummary=evidence_summary,
                recommendedOptionKey=winner.option_key if winner else None,
                conflictOptionKeys=conflict.option_keys,
            )
        )

    if has_blocking_failure(checks):
        for check in checks:
            if check.status != "fail" or check.severity != "block":
                continue
            for path in check.paths:
                opt = next((o for o in options if o.path == path), None)
                if opt:
                    verdicts.append(
                        FieldVerdict(
                            path=path,
                            label=opt.label,
                            logicalFieldId=opt.logical_field_id,
                            action="reject",
                            reason=check.message or "This field cannot be applied from the uploaded documents.",
                            evidenceSummary=check.message,
                        )
                    )

    seen_paths = {v.path for v in verdicts}
    for opt in options:
        if opt.path in seen_paths or opt.path in conflict_paths:
            continue
        if opt.path.startswith("_unmapped"):
            continue
        if opt.pre_selected and not opt.needs_resolution:
            summary = format_accept_summary(opt)
            verdicts.append(
                FieldVerdict(
                    path=opt.path,
                    label=opt.label,
                    logicalFieldId=opt.logical_field_id,
                    action="accept",
                    reason=summary,
                    evidenceSummary=summary,
                    recommendedOptionKey=opt.option_key,
                )
            )
        elif opt.needs_resolution and opt.confidence >= 0.85:
            summary = (
                f"{opt.label}: {opt.incoming_display} from {opt.source_label} "
                f"— will resolve {opt.needs_resolution} on apply."
            )
            verdicts.append(
                FieldVerdict(
                    path=opt.path,
                    label=opt.label,
                    logicalFieldId=opt.logical_field_id,
                    action="suggest",
                    reason=summary,
                    evidenceSummary=summary,
                    recommendedOptionKey=opt.option_key,
                )
            )

    return verdicts


def adjudicate_bundle(
    country_code: str,
    extractions: list[dict[str, Any]],
    form_snapshot: dict[str, Any] | None = None,
    existing_documents: list[dict[str, Any]] | None = None,
) -> AdjudicateResponse:
    extractions, cache_notes = merge_cached_extractions(extractions, existing_documents)

    playbook = load_country_playbook(country_code)
    if playbook is None:
        return AdjudicateResponse(
            countryCode=country_code.strip().upper(),
            playbookVersion=0,
            options=[],
            conflicts=[],
            bundleChecks=[],
            fieldVerdicts=[],
            cotTrace=[],
            warnings=[f"No document playbook for country {country_code}."] + cache_notes,
            bundleSummary="No document playbook is configured for this country.",
        )

    options = flatten_extractions_to_options(playbook, extractions)
    bundle_checks = run_bundle_rules(playbook, options)

    existing_checks, existing_cot = check_existing_documents(extractions, existing_documents)
    bundle_checks.extend(existing_checks)

    form_checks = compare_form_snapshot(options, form_snapshot or {})
    bundle_checks.extend(form_checks)

    options = _clear_preselect_on_blocks(options, bundle_checks)
    conflicts = detect_conflicts(options)

    address_candidates = collect_address_candidates(extractions)
    reconcile_raw = reconcile_address_candidates(
        [c.model_dump(by_alias=True) for c in address_candidates],
        form_snapshot,
    )
    ranked = reconcile_raw.get("ranked") or []
    address_candidates = [AddressCandidate.model_validate(row) for row in ranked]
    address_reconciliation = AddressReconciliation(
        selectedCandidateKey=reconcile_raw.get("selectedCandidateKey"),
        alignmentScore=float(reconcile_raw.get("alignmentScore") or 0.0),
        rationale=str(reconcile_raw.get("rationale") or ""),
    )

    freshness_findings = correlate_temporal_freshness(
        options, extractions, existing_documents, form_snapshot
    )
    freshness_by_path = {f.path: f.preferred_option_key for f in freshness_findings}

    field_verdicts = build_field_verdicts(
        options, conflicts, bundle_checks, playbook.name_fuzzy_threshold, freshness_by_path
    )
    cot_trace = build_cot_trace(options, conflicts, bundle_checks, field_verdicts)
    if existing_cot:
        offset = len(cot_trace)
        for step in existing_cot:
            cot_trace.append(step.model_copy(update={"step": step.step + offset}))

    warnings: list[str] = list(cache_notes)
    for extraction in extractions:
        for w in extraction.get("warnings") or []:
            warnings.append(str(w))

    bundle_summary = build_bundle_summary(
        extractions, options, conflicts, bundle_checks, field_verdicts
    )

    return AdjudicateResponse(
        countryCode=playbook.country_code,
        playbookVersion=playbook.version,
        options=options,
        conflicts=conflicts,
        bundleChecks=bundle_checks,
        fieldVerdicts=field_verdicts,
        cotTrace=cot_trace,
        warnings=warnings,
        bundleSummary=bundle_summary,
        addressCandidates=address_candidates,
        addressReconciliation=address_reconciliation,
        freshnessFindings=freshness_findings,
    )
