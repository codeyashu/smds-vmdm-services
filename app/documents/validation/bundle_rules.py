"""Cross-document bundle rules — country playbook driven."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.documents.playbook.types import CountryPlaybook, FieldBinding
from app.documents.rules.in_patterns import is_natural_person, region_for_gstin
from app.documents.validation.identifiers import embedded_pan_in_gstin, validate_identifier_kind
from app.documents.validation.normalize import fuzzy_ratio, normalize_identifier, normalize_name
from app.documents.validation.types import BundleCheck, FieldOption


def _collect_by_logical(options: list[FieldOption]) -> dict[str, list[FieldOption]]:
    grouped: dict[str, list[FieldOption]] = defaultdict(list)
    for opt in options:
        key = opt.logical_field_id or opt.path
        grouped[key].append(opt)
    return grouped


def _distinct_values(opts: list[FieldOption]) -> set[str]:
    out: set[str] = set()
    for opt in opts:
        if opt.incoming_value is None:
            continue
        if isinstance(opt.incoming_value, bool):
            out.add(str(opt.incoming_value))
        else:
            text = str(opt.incoming_value).strip()
            if text:
                out.add(text)
    return out


def _doc_ids(opts: list[FieldOption]) -> list[str]:
    return [opt.document_id or "" for opt in opts if opt.document_id]


def run_bundle_rules(playbook: CountryPlaybook, options: list[FieldOption]) -> list[BundleCheck]:
    checks: list[BundleCheck] = []
    binding_map = playbook.binding_map()
    by_logical = _collect_by_logical(options)

    # Singleton identifier rules from playbook bindings
    for logical_id, binding in binding_map.items():
        if not binding.singleton or not binding.validator:
            continue
        opts = by_logical.get(logical_id, [])
        if not opts:
            continue
        normalized_values: set[str] = set()
        for opt in opts:
            result = validate_identifier_kind(binding.validator, str(opt.incoming_value or ""))
            if result.ok:
                normalized_values.add(result.normalized)
            else:
                checks.append(
                    BundleCheck(
                        id=f"identifier_shape_{logical_id}",
                        status="fail",
                        severity="block",
                        message=result.message,
                        paths=[opt.path],
                        logicalFieldIds=[logical_id],
                        documentIds=_doc_ids([opt]),
                    )
                )
        if len(normalized_values) > 1:
            checks.append(
                BundleCheck(
                    id=f"id_{logical_id}_singleton",
                    status="fail",
                    severity="block",
                    message=f"Multiple distinct values for {binding.label} across documents.",
                    paths=[o.path for o in opts],
                    logicalFieldIds=[logical_id],
                    documentIds=_doc_ids(opts),
                )
            )

    # Cross-doc GSTIN embeds PAN
    gst_opts = by_logical.get("gstin", [])
    pan_opts = by_logical.get("pan", [])
    if gst_opts and pan_opts:
        gst_val = validate_identifier_kind("gstin", str(gst_opts[0].incoming_value or ""))
        pan_val = validate_identifier_kind("pan", str(pan_opts[0].incoming_value or ""))
        if gst_val.ok and pan_val.ok:
            embedded = embedded_pan_in_gstin(gst_val.normalized)
            if embedded and embedded != pan_val.normalized:
                checks.append(
                    BundleCheck(
                        id="cross_gstin_embeds_pan",
                        status="fail",
                        severity="block",
                        message=f"GSTIN embeds PAN {embedded} but PAN document reads {pan_val.normalized}.",
                        paths=[gst_opts[0].path, pan_opts[0].path],
                        logicalFieldIds=["gstin", "pan"],
                        documentIds=_doc_ids(gst_opts + pan_opts),
                    )
                )
            else:
                checks.append(
                    BundleCheck(
                        id="cross_gstin_embeds_pan",
                        status="pass",
                        severity="info",
                        message="GSTIN and PAN identifiers are consistent.",
                        logicalFieldIds=["gstin", "pan"],
                    )
                )

    # Multi-source fuzzy name conflicts
    for logical_id, doc_types in playbook.multi_source_fields.items():
        opts = [o for o in options if o.logical_field_id == logical_id]
        if len(opts) < 2:
            continue
        distinct = _distinct_values(opts)
        if len(distinct) <= 1:
            continue
        threshold = (
            playbook.name_fuzzy_threshold
            if logical_id in ("trading_name", "legal_name")
            else playbook.address_fuzzy_threshold
        )
        values = list(distinct)
        min_ratio = 1.0
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                ratio = fuzzy_ratio(values[i], values[j])
                min_ratio = min(min_ratio, ratio)
        if min_ratio < threshold:
            binding = binding_map.get(logical_id)
            label = binding.label if binding else logical_id
            checks.append(
                BundleCheck(
                    id=f"name_conflict_{logical_id}",
                    status="warn",
                    severity="warn",
                    message=f"{label} differs across documents (fuzzy match {min_ratio:.0%}). Steward must choose.",
                    paths=[o.path for o in opts],
                    logicalFieldIds=[logical_id],
                    documentIds=_doc_ids(opts),
                )
            )

    # GST region vs GSTIN state
    region_opts = by_logical.get("bill_to_region", [])
    if gst_opts and region_opts:
        gst_norm = validate_identifier_kind("gstin", str(gst_opts[0].incoming_value or ""))
        region = normalize_identifier(str(region_opts[0].incoming_value or ""))
        if gst_norm.ok and region:
            derived = region_for_gstin(gst_norm.normalized)
            if derived and derived != region:
                checks.append(
                    BundleCheck(
                        id="addr_region_vs_gstin",
                        status="warn",
                        severity="warn",
                        message=f"GSTIN implies region {derived} but address reads {region}.",
                        paths=[gst_opts[0].path, region_opts[0].path],
                        logicalFieldIds=["gstin", "bill_to_region"],
                        documentIds=_doc_ids(gst_opts + region_opts),
                    )
                )

    # Entity type: natural person PAN vs company GST
    if pan_opts and gst_opts:
        pan_norm = validate_identifier_kind("pan", str(pan_opts[0].incoming_value or ""))
        if pan_norm.ok:
            natural = is_natural_person(pan_norm.normalized)
            if natural is True:
                checks.append(
                    BundleCheck(
                        id="entity_person_with_gst",
                        status="warn",
                        severity="warn",
                        message="PAN indicates natural person but GST certificate present — verify entity type.",
                        paths=[pan_opts[0].path, gst_opts[0].path],
                        logicalFieldIds=["pan", "gstin"],
                        documentIds=_doc_ids(pan_opts + gst_opts),
                    )
                )

    return checks


def has_blocking_failure(checks: list[BundleCheck]) -> bool:
    return any(c.status == "fail" and c.severity == "block" for c in checks)
