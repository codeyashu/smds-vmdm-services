"""Blend deterministic company scores with LLM similarity — port of blend-semantic-scores.ts."""

from __future__ import annotations

from typing import Any

AI_ELIGIBLE_FIELDS = {
    "tradingName": "nameScore",
    "street": "addressScore",
}


def _status_from_score(score: int) -> str:
    if score >= 85:
        return "match"
    if score >= 60:
        return "partial"
    return "mismatch"


def _compute_overall(field_confidence: list[dict[str, Any]]) -> dict[str, int]:
    compared = [f for f in field_confidence if f.get("status") != "unknown"]
    if not compared:
        return {"score": 0, "comparedFields": 0, "skippedFields": len(field_confidence)}
    total = sum(int(f.get("score") or 0) for f in compared)
    return {
        "score": round(total / len(compared)),
        "comparedFields": len(compared),
        "skippedFields": len(field_confidence) - len(compared),
    }


def blend_semantic_scores(
    scored: list[dict[str, Any]],
    similarity: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    by_id = {str(row.get("id")): row for row in (similarity or []) if row.get("id")}

    blended: list[dict[str, Any]] = []
    for entry in scored:
        summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
        ext_id = str(summary.get("companyExternalId") or "")
        match = by_id.get(ext_id)
        if not match:
            blended.append({**entry, "aiRaisedFields": [], "aiNote": None})
            continue

        ai_raised: list[str] = []
        field_confidence = []
        for field in entry.get("fieldConfidence") or []:
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("field") or "")
            score_key = AI_ELIGIBLE_FIELDS.get(field_name)
            if not score_key or field.get("status") == "unknown":
                field_confidence.append(field)
                continue
            ai_score = match.get(score_key)
            current_score = int(field.get("score") or 0)
            if ai_score is None or int(ai_score) <= current_score:
                field_confidence.append(field)
                continue
            ai_raised.append(field_name)
            new_score = int(ai_score)
            field_confidence.append(
                {**field, "score": new_score, "status": _status_from_score(new_score)}
            )

        overall_match = _compute_overall(field_confidence)
        blended.append(
            {
                **entry,
                "fieldConfidence": field_confidence,
                "overallMatch": overall_match,
                "overallScore": overall_match["score"],
                "aiRaisedFields": ai_raised,
                "aiNote": match.get("note"),
            }
        )

    blended.sort(
        key=lambda row: (
            -int(row.get("overallScore") or 0),
            -int((row.get("overallMatch") or {}).get("comparedFields") or 0),
        )
    )
    return blended
