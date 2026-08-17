"""Extraction pipeline — OCR and LLM providers are faked; no network, no real Azure creds."""

from __future__ import annotations

import pytest

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


async def test_cheque_block_ignored_on_gst_doc_type(monkeypatch):
    """Cheque fields on a GST cert envelope are ignored — only the GST block applies."""
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

    assert not any(p.path.startswith("vendorBankAccounts") for p in result.patches)
    by_tax = {p.tax_type_code: p for p in result.patches if p.tax_type_code}
    assert by_tax["TAXNO3"].pre_selected is True
    assert by_tax["TAXNO4"].pre_selected is True


async def test_failing_ifsc_check_on_cancelled_cheque(monkeypatch):
    envelope = {
        "doc_type": "IN_CANCELLED_CHEQUE",
        "doc_type_confidence": 0.95,
        "cheque": {"ifsc": "NOT-AN-IFSC", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()

    statuses = {c["id"]: c["status"] for c in result.cross_checks}
    assert statuses["ifsc_shape"] == "fail"


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


async def test_iec_doc_type_does_not_emit_pan_patches_when_llm_fills_pan_block(monkeypatch):
    """IEC codes must not bleed into the PAN tax slot even if the model populates pan."""
    envelope = {
        "doc_type": "IN_IEC_CERTIFICATE",
        "doc_type_confidence": 0.99,
        "pan": {"pan": "AOXPS7707K", "holder_name": "Yogesh Saruparia", "confidence": 0.95},
        "iec": {"iec_code": "AOXPS7707K", "holder_name": "YASH POLYCHEM INDUSTRIES", "confidence": 0.95},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()

    paths = {p.path for p in result.patches}
    assert "taxInformation.taxIdentificationNumbers.2.taxIdentificationNumber" not in paths
    assert "_unmapped.iecCode" in paths
    assert any(p.path == "tradingName" and p.value == "YASH POLYCHEM INDUSTRIES" for p in result.patches)


async def test_filename_override_corrects_misclassified_pan_aadhaar(monkeypatch):
    envelope = {
        "doc_type": "IN_ADDRESS_PROOF",
        "doc_type_confidence": 0.99,
        "address_proof": {
            "holder_name": "Yogesh Saruparia",
            "address": {"street_name": "MG Road"},
            "confidence": 0.9,
        },
        "pan": {"pan": "AOXPS7707K", "holder_name": "Yogesh Saruparia", "confidence": 0.95},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await pipeline.run_extraction(
        b"%PDF-fake",
        "application/pdf",
        "IN",
        filename="tax_certificate_pan_aadhaar_card_sole_proprietor.pdf",
    )
    assert result.doc_type == "IN_PAN_CARD"
    assert any(p.path.endswith("taxIdentificationNumber") for p in result.patches)


async def test_iec_envelope_ignores_cheque_block(monkeypatch):
    envelope = {
        "doc_type": "IN_IEC_CERTIFICATE",
        "doc_type_confidence": 0.99,
        "cheque": {"ifsc": "HDFC0001234", "confidence": 0.9},
        "iec": {"iec_code": "ABCDE1234F", "confidence": 0.9},
    }
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([envelope]))
    result = await _run()
    assert not any(p.path.startswith("vendorBankAccounts") for p in result.patches)


async def test_vision_retry_fills_missing_pan_on_scan(monkeypatch):
    first = {
        "doc_type": "IN_PAN_CARD",
        "doc_type_confidence": 0.95,
        "pan": {"holder_name": "Yogesh Saruparia", "confidence": 0.8},
    }
    second = {
        "doc_type": "IN_PAN_CARD",
        "doc_type_confidence": 0.95,
        "pan": {"holder_name": "Yogesh Saruparia", "confidence": 0.8},
    }
    third = {"pan": "ABCDE1234F", "holder_name": "Yogesh Saruparia", "confidence": 0.95}
    fourth = {"pan": "ABCDE1234F", "confidence": 0.95}
    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr(text=""))
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([first, second, third, fourth]))
    result = await pipeline.run_extraction(
        b"%PDF-fake",
        "application/pdf",
        "IN",
        filename="tax_certificate_pan_aadhaar_card_sole_proprietor.pdf",
    )
    assert result.doc_type == "IN_PAN_CARD"
    assert any("taxIdentificationNumber" in p.path for p in result.patches)
