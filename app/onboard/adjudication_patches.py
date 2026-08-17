"""Build enrichment raw patches from adjudication verdicts (agent/steward apply policy)."""

from __future__ import annotations

from typing import Any

AGENT_AUTO_THRESHOLD = 0.85


def _superseded_option_keys(adjudication: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for finding in adjudication.get("freshnessFindings") or []:
        if not isinstance(finding, dict):
            continue
        for key in finding.get("supersededOptionKeys") or []:
            if key:
                keys.add(str(key))
    return keys


def _should_auto_apply(verdict: dict[str, Any], *, mode: str, alignment_score: float) -> bool:
    action = verdict.get("action")
    if action in ("reject", "skip", "steward_required"):
        return False
    if action == "accept":
        return True
    if action == "suggest":
        if mode == "steward":
            return True
        return alignment_score >= AGENT_AUTO_THRESHOLD
    return False


def patches_from_adjudication(
    adjudication: dict[str, Any],
    *,
    mode: str = "agent",
) -> list[dict[str, Any]]:
    """Return raw patches safe to apply to agent working state (verdict-driven)."""
    options_by_key: dict[str, dict[str, Any]] = {}
    for option in adjudication.get("options") or []:
        if isinstance(option, dict) and option.get("optionKey"):
            options_by_key[str(option["optionKey"])] = option

    superseded = _superseded_option_keys(adjudication)
    reconciliation = adjudication.get("addressReconciliation") or {}
    alignment_score = float(reconciliation.get("alignmentScore") or 0.0)

    patches: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for verdict in adjudication.get("fieldVerdicts") or []:
        if not isinstance(verdict, dict):
            continue
        if not _should_auto_apply(verdict, mode=mode, alignment_score=alignment_score):
            continue
        option_key = verdict.get("recommendedOptionKey")
        if not option_key or option_key in superseded:
            continue
        option = options_by_key.get(str(option_key))
        if not option:
            continue
        path = str(option.get("path") or "")
        if not path or path.startswith("_unmapped") or path in seen_paths:
            continue
        seen_paths.add(path)
        patches.append(
            {
                "path": path,
                "label": option.get("label") or path.split(".")[-1],
                "value": option.get("incomingValue"),
                "confidence": float(option.get("confidence") or 0.8),
                "source": "document",
                "sourceLabel": option.get("sourceLabel") or "document",
                "needsResolution": option.get("needsResolution"),
                "evidenceSnippet": option.get("evidenceSnippet"),
            }
        )

    return patches
