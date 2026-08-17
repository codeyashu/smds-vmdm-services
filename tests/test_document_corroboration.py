"""Document corroboration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.documents.validation.adjudicate import adjudicate_bundle
from app.documents.validation.document_corroboration import (
    corroborate_documents_async,
    should_run_document_corroboration,
)


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


def test_should_run_when_multiple_documents(monkeypatch):
    monkeypatch.setenv("DOCUMENT_CORROBORATION_ENABLED", "true")
    adjudication = adjudicate_bundle("IN", [{"documentId": "a", "docType": "IN_PAN_CARD", "patches": []}])
    assert should_run_document_corroboration(
        [
            {"documentId": "a", "docType": "IN_PAN_CARD", "patches": []},
            {"documentId": "b", "docType": "IN_GST_CERTIFICATE", "patches": []},
        ],
        adjudication,
    )


def test_should_not_run_when_disabled(monkeypatch):
    monkeypatch.delenv("DOCUMENT_CORROBORATION_ENABLED", raising=False)
    extractions = [
        {"documentId": "a", "docType": "IN_PAN_CARD", "patches": []},
        {"documentId": "b", "docType": "IN_GST_CERTIFICATE", "patches": []},
    ]
    adjudication = adjudicate_bundle("IN", extractions)
    assert not should_run_document_corroboration(extractions, adjudication)


@pytest.mark.asyncio
async def test_corroborate_returns_suggestions(monkeypatch):
    monkeypatch.setenv("DOCUMENT_CORROBORATION_ENABLED", "true")
    extractions = [
        {
            "documentId": "eph_pan",
            "docType": "IN_PAN_CARD",
            "patches": [_patch("tradingName", "ACME LOGISTICS", "Trading name", 0.92)],
            "warnings": [],
        },
        {
            "documentId": "eph_gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [_patch("tradingName", "ACME LOGISTICS PVT LTD", "Trading name", 0.95)],
            "warnings": [],
        },
    ]
    adjudication = adjudicate_bundle("IN", extractions)
    conflict = next(c for c in adjudication.conflicts if c.path == "tradingName")
    option_key = conflict.option_keys[0]

    mock_provider = AsyncMock()
    mock_provider.complete_json = AsyncMock(
        return_value={
            "verdict": "likely",
            "correlationScore": 78,
            "narrative": "Names are variants of the same entity.",
            "suggestedOptions": [{"path": "tradingName", "optionKey": option_key, "reason": "GST legal style"}],
            "suggestedAddressCandidateKey": None,
        }
    )

    with patch("app.documents.validation.document_corroboration.get_llm_provider", return_value=mock_provider):
        result = await corroborate_documents_async(
            country_code="IN",
            extractions=extractions,
            form_snapshot={"tradingName": "ACME"},
            adjudication=adjudication,
        )

    assert result.skipped is False
    assert result.verdict == "likely"
    assert result.suggested_options[0].option_key == option_key
