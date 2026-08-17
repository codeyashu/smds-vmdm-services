"""Enrichment plan merge — Python port of @smds/vmdm-server-core enrichment-merge."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

HIGH_CONFIDENCE_THRESHOLD = 0.8


def read_nested_value(obj: dict[str, Any], path: str) -> Any:
    current: Any = obj
    for part in path.split("."):
        if current is None or not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def format_display_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _raw_patch_to_option(patch: dict[str, Any], form_snapshot: dict[str, Any]) -> dict[str, Any]:
    current_value = read_nested_value(form_snapshot, patch["path"])
    incoming_display = format_display_value(patch.get("value"))
    needs = patch.get("needsResolution")
    if needs == "cityCode":
        incoming_display = f"{incoming_display} (will resolve to city code)"
    elif needs == "bankingInstitutionCode":
        incoming_display = f"{incoming_display} (will resolve via bank master)"

    evidence = patch.get("evidenceSnippet") or (
        (patch.get("evidence") or {}).get("snippet") if isinstance(patch.get("evidence"), dict) else None
    )

    pre_selected = patch.get("confidence", 0) >= HIGH_CONFIDENCE_THRESHOLD and not needs

    return {
        "optionKey": f"{patch.get('sourceLabel', patch.get('source'))}:{patch['path']}",
        "path": patch["path"],
        "label": patch.get("label", patch["path"]),
        "source": patch.get("source", "document"),
        "sourceLabel": patch.get("sourceLabel", "Source"),
        "incomingValue": patch.get("value"),
        "currentDisplay": format_display_value(current_value),
        "incomingDisplay": incoming_display,
        "confidence": patch.get("confidence", 0),
        "preSelected": pre_selected,
        "needsResolution": needs,
        "evidenceSnippet": evidence,
    }


def detect_field_conflicts(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path: dict[str, list[dict[str, Any]]] = {}
    for opt in options:
        by_path.setdefault(opt["path"], []).append(opt)

    conflicts: list[dict[str, Any]] = []
    for path, group in by_path.items():
        distinct = {json.dumps(opt.get("incomingValue"), sort_keys=True, default=str) for opt in group}
        if len(group) > 1 and len(distinct) > 1:
            conflicts.append(
                {
                    "path": path,
                    "label": group[0].get("label", path),
                    "optionKeys": [opt["optionKey"] for opt in group],
                }
            )
    return conflicts


def merge_enrichment_plan(
    session_id: str,
    country_code: str,
    patch_groups: list[list[dict[str, Any]]],
    form_snapshot: dict[str, Any],
    *,
    duplicate_matches: list[dict[str, Any]] | None = None,
    steps_completed: list[str] | None = None,
    read_only_hints: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for group in patch_groups:
        for patch in group:
            key = f"{patch.get('sourceLabel', '')}:{patch['path']}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(patch)

    options = [_raw_patch_to_option(p, form_snapshot) for p in deduped]
    return {
        "sessionId": session_id,
        "countryCode": country_code,
        "options": options,
        "readOnlyHints": read_only_hints,
        "conflicts": detect_field_conflicts(options),
        "duplicateMatches": duplicate_matches,
        "stepsCompleted": steps_completed or [],
        "warnings": warnings or [],
    }


def apply_patches_to_form_state(form_state: dict[str, Any], patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply raw patches to working state (dot paths, shallow merge per path)."""
    result = deepcopy(form_state)
    for patch in patches:
        parts = patch["path"].split(".")
        current: Any = result
        for i, part in enumerate(parts[:-1]):
            if not isinstance(current, dict):
                break
            nxt = parts[i + 1]
            if current.get(part) is None:
                current[part] = [] if nxt.isdigit() else {}
            current = current[part]
        if isinstance(current, dict):
            current[parts[-1]] = patch.get("value")
    return result

