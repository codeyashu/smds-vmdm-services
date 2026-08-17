"""Tests for TrustLens cross-field correlation."""

from __future__ import annotations

from app.web_trust.correlation import compute_field_correlation
from app.web_trust.scoring import compare_field
from app.web_trust.types import WebMatchedRecord


def _record(
    connector_id: str,
    display: str,
    evidence: list,
    score: int = 80,
) -> WebMatchedRecord:
    return WebMatchedRecord(
        id=connector_id,
        sourceType="format_validator",
        verificationMode="format_check",
        connectorId=connector_id,
        displayName=display,
        matchScore=score,
        fieldEvidence=evidence,
        authorityWeight=1.0,
    )


def test_isolated_tax_only_match_flagged():
    gstin_evidence = [
        compare_field(
            field="tax",
            label="Tax ID",
            left="33AALCS3056Q1ZT",
            right="33AALCS3056Q1ZT",
            score=100,
        ),
        compare_field(
            field="country",
            label="Country",
            left="IN",
            right="IN",
            score=100,
        ),
    ]
    records = [
        _record("in_gstin", "GSTIN format", gstin_evidence),
    ]
    _, summary = compute_field_correlation(records)
    assert summary.isolatedMatch is True
    assert summary.correlationScore < 70
    assert "identifier" in (summary.narrative or "").lower()


def test_directory_with_name_not_isolated():
    evidence = [
        compare_field(
            field="tradingName",
            label="Trading name",
            left="SREEJA HOSIERIES",
            right="SREEJA HOSIERIES PVT LTD",
            score=92,
        ),
        compare_field(
            field="tax",
            label="Tax ID",
            left="33AALCS3056Q1ZT",
            right="33AALCS3056Q1ZT",
            score=100,
        ),
        compare_field(
            field="city",
            label="City",
            left="Tirupur",
            right="Tirupur",
            score=100,
        ),
    ]
    records = [_record("commercial_directory", "DNB directory", evidence, score=95)]
    _, summary = compute_field_correlation(records)
    assert summary.isolatedMatch is False
    assert summary.correlatedFieldCount == 3
