"""Extraction pipeline — OCR and LLM providers are faked; no network, no real Azure creds."""

from __future__ import annotations

import pytest
import structlog

from app.documents.extract import pipeline
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from tests.fakes import GST_ENVELOPE, FailingOcr, FailingOnRetryLlm, FakeLlm, FakeOcr


async def _run(content=b"%PDF-fake", mime="application/pdf", country="IN"):
    return await pipeline.run_extraction(content, mime, country)


async def test_raises_unavailable_when_no_providers(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: None)
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: None)
    with pytest.raises(ExtractionUnavailable):
        await _run()


async def test_raises_upstream_error_when_ocr_fails(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FailingOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([GST_ENVELOPE]))
    with pytest.raises(ExtractionUpstreamError):
        await _run()


async def test_returns_patches_for_recognised_gst_document(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([GST_ENVELOPE]))
    result = await _run()
    assert result.doc_type == "IN_GST_CERTIFICATE"
    paths = {p.path for p in result.patches}
    assert "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber" in paths


async def test_unknown_doc_type_returns_empty_patches_and_a_warning(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr(text="unrelated invoice"))
    monkeypatch.setattr(
        pipeline, "get_llm_provider", lambda: FakeLlm([{"doc_type": "UNKNOWN", "doc_type_confidence": 0.1}])
    )
    result = await _run()
    assert result.doc_type == "UNKNOWN"
    assert result.patches == []
    assert result.warnings


async def test_retries_once_on_malformed_json_then_succeeds(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(
        pipeline,
        "get_llm_provider",
        lambda: FakeLlm([{"gst": "missing doc_type entirely"}, GST_ENVELOPE]),
    )
    result = await _run()
    assert result.doc_type == "IN_GST_CERTIFICATE"


async def test_raises_upstream_error_after_two_malformed_responses(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(
        pipeline,
        "get_llm_provider",
        lambda: FakeLlm([{"bad": "payload"}, {"still": "bad"}]),
    )
    with pytest.raises(ExtractionUpstreamError):
        await _run()


async def test_raises_upstream_error_when_retry_hits_transport_error(monkeypatch):
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(
        pipeline,
        "get_llm_provider",
        lambda: FailingOnRetryLlm({"bad": "payload"}, RuntimeError("connection reset")),
    )
    with pytest.raises(ExtractionUpstreamError):
        await _run()


async def test_runs_gstin_pan_crosscheck_when_both_present(monkeypatch):
    envelope = {
        "doc_type": "IN_GST_CERTIFICATE",
        "doc_type_confidence": 0.95,
        "gst": {"gstin": "27AABCA1234F1Z5", "confidence": 0.98},
        "pan": {"pan": "AABCA1234F", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()
    statuses = {c["id"]: c["status"] for c in result.cross_checks}
    assert statuses.get("gstin_contains_pan") == "pass"


async def test_failing_crosscheck_clears_pre_selected_on_pan_and_gstin(monkeypatch):
    """to_patches.py's contract: pre_selected is never true for a value that is part of a
    failing cross-check. A GSTIN embedding AABCA1234F against a PAN block reading ZZZZZ9999Z
    fails gstin_contains_pan, so neither identifier may arrive pre-ticked."""
    envelope = {
        "doc_type": "IN_GST_CERTIFICATE",
        "doc_type_confidence": 0.95,
        "gst": {"gstin": "27AABCA1234F1Z5", "trade_name": "ACME LOGISTICS", "confidence": 0.98},
        "pan": {"pan": "ZZZZZ9999Z", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()

    by_tax = {p.tax_type_code: p for p in result.patches if p.tax_type_code}
    assert by_tax["TAXNO3"].pre_selected is False, "PAN patch must not be pre-selected"
    assert by_tax["TAXNO4"].pre_selected is False, "GSTIN patch must not be pre-selected"

    statuses = {c["id"]: c["status"] for c in result.cross_checks}
    assert statuses["gstin_contains_pan"] == "fail"


async def test_failing_crosscheck_leaves_unrelated_patches_pre_selected(monkeypatch):
    """The clearing is narrowly scoped: gstin_contains_pan implicates only PAN/GSTIN, so a
    high-confidence trading name from the same document keeps its pre-selection."""
    envelope = {
        "doc_type": "IN_GST_CERTIFICATE",
        "doc_type_confidence": 0.95,
        "gst": {"gstin": "27AABCA1234F1Z5", "trade_name": "ACME LOGISTICS", "confidence": 0.98},
        "pan": {"pan": "ZZZZZ9999Z", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()

    trading = next(p for p in result.patches if p.path == "tradingName")
    assert trading.pre_selected is True


async def test_passing_crosscheck_keeps_pan_and_gstin_pre_selected(monkeypatch):
    envelope = {
        "doc_type": "IN_GST_CERTIFICATE",
        "doc_type_confidence": 0.95,
        "gst": {"gstin": "27AABCA1234F1Z5", "confidence": 0.98},
        "pan": {"pan": "AABCA1234F", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()

    by_tax = {p.tax_type_code: p for p in result.patches if p.tax_type_code}
    assert by_tax["TAXNO3"].pre_selected is True
    assert by_tax["TAXNO4"].pre_selected is True


async def test_failing_ifsc_check_does_not_clear_pan_or_gstin_pre_selection(monkeypatch):
    """A malformed IFSC says nothing about the PAN/GSTIN — only checks that implicate those
    identifiers may clear their pre-selection."""
    envelope = {
        "doc_type": "IN_GST_CERTIFICATE",
        "doc_type_confidence": 0.95,
        "gst": {"gstin": "27AABCA1234F1Z5", "confidence": 0.98},
        "pan": {"pan": "AABCA1234F", "confidence": 0.9},
        "cheque": {"ifsc": "NOT-AN-IFSC", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()

    statuses = {c["id"]: c["status"] for c in result.cross_checks}
    assert statuses["ifsc_shape"] == "fail"
    by_tax = {p.tax_type_code: p for p in result.patches if p.tax_type_code}
    assert by_tax["TAXNO3"].pre_selected is True
    assert by_tax["TAXNO4"].pre_selected is True


async def test_udyam_doc_type_surfaces_as_unmapped_not_a_patch(monkeypatch):
    envelope = {
        "doc_type": "IN_UDYAM_CERTIFICATE",
        "doc_type_confidence": 0.9,
        "udyam": {"udyam_number": "UDYAM-MH-01-1234567", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()
    assert result.patches == []
    assert any(row["value"] == "UDYAM-MH-01-1234567" for row in result.unmapped)
