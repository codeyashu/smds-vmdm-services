"""Cross-field correlation — fields must corroborate as a set, not in isolation."""

from __future__ import annotations

from typing import Any

from app.web_trust.scoring import FIELD_WEIGHTS, compute_overall_match
from app.web_trust.types import FieldConfidence, FieldCorrelationSummary, WebMatchedRecord

_IDENTITY_FIELDS = frozenset({"tradingName", "city", "street", "postalCode"})
_ISOLATED_FIELDS = frozenset({"tax", "country"})


def _record_correlation_score(record: WebMatchedRecord) -> tuple[int, int, list[FieldConfidence]]:
    compared = [entry for entry in record.fieldEvidence if entry.status != "unknown"]
    if not compared:
        return 0, 0, []
    weighted_sum = 0
    weight_total = 0
    for entry in compared:
        weight = FIELD_WEIGHTS.get(entry.field, 1)
        weighted_sum += entry.score * weight
        weight_total += weight
    score = int(round(weighted_sum / weight_total)) if weight_total else 0
    field_names = {entry.field for entry in compared}
    has_identity = bool(field_names & _IDENTITY_FIELDS)
    if field_names <= _ISOLATED_FIELDS or (not has_identity and "tax" in field_names):
        score = int(round(score * 0.55))
    return score, len(compared), compared


def compute_field_correlation(
    matched_records: list[WebMatchedRecord],
) -> tuple[list[FieldConfidence], FieldCorrelationSummary]:
    candidates = [record for record in matched_records if record.connectorId != "bill_to_address"]
    if not candidates:
        return [], FieldCorrelationSummary(
            correlationScore=0,
            correlatedFieldCount=0,
            isolatedMatch=True,
            narrative="No external sources returned comparable fields.",
        )

    best_record: WebMatchedRecord | None = None
    best_score = -1
    best_count = 0
    best_compared: list[FieldConfidence] = []

    for record in candidates:
        score, count, compared = _record_correlation_score(record)
        if score > best_score or (score == best_score and count > best_count):
            best_score = score
            best_count = count
            best_record = record
            best_compared = record.fieldEvidence

    if best_record is None:
        return [], FieldCorrelationSummary(
            correlationScore=0,
            correlatedFieldCount=0,
            isolatedMatch=True,
            narrative="Sources ran but none returned fields to correlate.",
        )

    compared_fields = {entry.field for entry in best_compared if entry.status != "unknown"}
    isolated = compared_fields <= _ISOLATED_FIELDS or not (compared_fields & _IDENTITY_FIELDS)

    narrative = _build_narrative(
        best_record=best_record,
        compared_fields=compared_fields,
        isolated=isolated,
        score=best_score,
    )

    return best_compared, FieldCorrelationSummary(
        correlationScore=max(0, best_score),
        correlatedFieldCount=best_count,
        isolatedMatch=isolated,
        bestSourceId=best_record.id,
        bestSourceName=best_record.displayName,
        narrative=narrative,
    )


def _build_narrative(
    *,
    best_record: WebMatchedRecord,
    compared_fields: set[str],
    isolated: bool,
    score: int,
) -> str:
    if isolated:
        return (
            f"Only identifier-level fields matched via {best_record.displayName} "
            "(tax ID and/or country). Trading name and address were not corroborated "
            "by any source — this is not proof the same legal entity."
        )
    identity_hits = sorted(compared_fields & _IDENTITY_FIELDS)
    if identity_hits and score >= 85:
        return (
            f"{best_record.displayName} corroborates {len(identity_hits)} identity field(s) "
            f"({', '.join(identity_hits)}) together with tax/country signals."
        )
    if identity_hits:
        return (
            f"{best_record.displayName} partially corroborates "
            f"{', '.join(identity_hits)} — review individual field scores before proceeding."
        )
    return f"{best_record.displayName} returned limited cross-field agreement ({score}% correlation)."


def merge_llm_corroboration(
    summary: FieldCorrelationSummary,
    *,
    llm_verdict: str,
    llm_score: int,
    corroborated_fields: list[str],
) -> FieldCorrelationSummary:
    isolated = summary.isolatedMatch
    if llm_verdict == "different":
        isolated = True
    elif llm_verdict in ("same", "likely") and any(f in _IDENTITY_FIELDS for f in corroborated_fields):
        isolated = False
    score = max(summary.correlationScore, llm_score) if llm_verdict != "different" else min(summary.correlationScore, 35)
    narrative = summary.narrative
    if llm_verdict == "different":
        narrative = "AI corroboration flagged conflicting signals across sources — treat as low trust."
    elif llm_verdict in ("same", "likely") and corroborated_fields:
        narrative = (
            f"{narrative} AI corroboration agrees on "
            f"{', '.join(corroborated_fields)} as the same entity."
        )
    return summary.model_copy(
        update={
            "correlationScore": score,
            "correlatedFieldCount": max(summary.correlatedFieldCount, len(corroborated_fields)),
            "isolatedMatch": isolated,
            "narrative": narrative,
        }
    )
