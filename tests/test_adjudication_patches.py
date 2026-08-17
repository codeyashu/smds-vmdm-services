"""Tests for verdict-driven patch selection."""

from __future__ import annotations

from app.documents.validation.adjudicate import adjudicate_bundle
from app.onboard.adjudication_patches import patches_from_adjudication
from app.onboard.extraction_mapping import patches_from_extract_results


def _patch(path: str, value, label: str, confidence: float = 0.95, **kwargs):
    return {
        "path": path,
        "value": value,
        "label": label,
        "confidence": confidence,
        "pre_selected": confidence >= 0.9,
        "regex_ok": True,
        **kwargs,
    }


def test_agent_skips_steward_required_conflict():
    extractions = [
        {
            "documentId": "pan",
            "docType": "IN_PAN_CARD",
            "patches": [_patch("tradingName", "ACME LOGISTICS", "Trading name", 0.92)],
            "warnings": [],
        },
        {
            "documentId": "gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "27AABCA1234F1Z5",
                    "GSTIN",
                ),
                _patch("tradingName", "ACME LOGISTICS PVT LTD", "Trading name", 0.95),
            ],
            "warnings": [],
        },
    ]
    adjudication = adjudicate_bundle("IN", extractions).as_dict()
    raw = patches_from_extract_results(extractions)
    verdict_patches = patches_from_adjudication(adjudication, mode="agent")

    assert any(row["path"] == "tradingName" for row in raw)
    assert not any(row["path"] == "tradingName" for row in verdict_patches)
    assert any(
        row["path"] == "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber"
        for row in verdict_patches
    )


def test_steward_mode_includes_suggest_verdicts():
    extractions = [
        {
            "documentId": "gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "27AABCA1234F1Z5",
                    "GSTIN",
                )
            ],
            "warnings": [],
        }
    ]
    adjudication = adjudicate_bundle("IN", extractions).as_dict()
    agent_patches = patches_from_adjudication(adjudication, mode="agent")
    steward_patches = patches_from_adjudication(adjudication, mode="steward")
    assert len(steward_patches) >= len(agent_patches)
