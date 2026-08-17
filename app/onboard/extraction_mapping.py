"""Map extraction pipeline results to enrichment raw patches."""

from __future__ import annotations

from typing import Any


def patches_from_extract_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for result in results:
        doc_type = str(result.get("docType") or "Document")
        for entry in result.get("patches") or []:
            if not entry.get("path"):
                continue
            path = str(entry["path"])
            if path.startswith("_unmapped"):
                continue
            needs = entry.get("needs_resolution") or entry.get("needsResolution")
            evidence = entry.get("evidence")
            snippet = None
            if isinstance(evidence, dict):
                snippet = evidence.get("snippet")
            patches.append(
                {
                    "path": path,
                    "label": entry.get("label") or path.split(".")[-1],
                    "value": entry.get("value"),
                    "confidence": float(entry.get("confidence") or 0.8),
                    "source": "document",
                    "sourceLabel": doc_type,
                    "needsResolution": needs,
                    "evidenceSnippet": snippet,
                }
            )
    return patches


def read_only_hints_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for result in results:
        doc_type = str(result.get("docType") or "Document")
        for entry in result.get("patches") or []:
            path = str(entry.get("path") or "")
            if not path.startswith("_unmapped"):
                continue
            evidence = entry.get("evidence")
            snippet = evidence.get("snippet") if isinstance(evidence, dict) else None
            hints.append(
                {
                    "path": path,
                    "label": entry.get("label") or path,
                    "displayValue": str(entry.get("value") or "—"),
                    "sourceLabel": doc_type,
                    "evidenceSnippet": snippet,
                }
            )
    return hints


def patches_from_bff_address(patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for patch in patches:
        path = patch.get("path")
        if not path:
            continue
        out.append(
            {
                "path": path,
                "label": str(path).split(".")[-1],
                "value": patch.get("value"),
                "confidence": 0.85,
                "source": "address",
                "sourceLabel": "External address service",
            }
        )
    return out


def patches_from_registry_summary(summary: dict[str, Any], fallback_name: str) -> list[dict[str, Any]]:
    name = summary.get("companyName") or fallback_name
    score = summary.get("matchDetails", {}).get("matchScore", 88)
    try:
        confidence = float(score) / 100 if float(score) > 1 else float(score)
    except (TypeError, ValueError):
        confidence = 0.88
    return [
        {
            "path": "tradingName",
            "label": "Trading name",
            "value": name,
            "confidence": confidence,
            "source": "registry",
            "sourceLabel": summary.get("sourceType") or "Registry",
        }
    ]


def summarize_duplicate_matches(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surfaced = items[:5]
    out: list[dict[str, Any]] = []
    for item in surfaced:
        raw_score = item.get("matchedScore")
        try:
            score = float(raw_score or 0)
            if score > 1:
                score /= 100
        except (TypeError, ValueError):
            score = 0
        reasons: list[str] = []
        if item.get("matchedWith"):
            reasons.append(str(item["matchedWith"]))
        out.append(
            {
                "vendorCode": item.get("vendorCode", ""),
                "tradingName": item.get("tradingName"),
                "score": score,
                "matchReasons": reasons,
            }
        )
    return out

