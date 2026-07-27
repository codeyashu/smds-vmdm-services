"""ExtractionEnvelope — the single-LLM-call response shape. Pure, no network."""

from __future__ import annotations

from app.documents.extract.schemas.india import ENVELOPE_DOC_TYPES, ExtractionEnvelope, GstExtraction


def test_envelope_accepts_known_doc_type_with_matching_block():
    env = ExtractionEnvelope(
        doc_type="IN_GST_CERTIFICATE",
        doc_type_confidence=0.97,
        gst=GstExtraction(gstin="27AABCA1234F1Z5", confidence=0.99),
    )
    assert env.doc_type in ENVELOPE_DOC_TYPES
    assert env.gst.gstin == "27AABCA1234F1Z5"


def test_envelope_defaults_other_blocks_to_none():
    env = ExtractionEnvelope(doc_type="IN_PAN_CARD")
    assert env.gst is None
    assert env.cheque is None
    assert env.udyam is None
    assert env.coi is None


def test_envelope_unknown_is_a_valid_doc_type():
    env = ExtractionEnvelope(doc_type="UNKNOWN", doc_type_confidence=0.2)
    assert env.doc_type == "UNKNOWN"
    assert "UNKNOWN" in ENVELOPE_DOC_TYPES


def test_envelope_doc_type_is_required():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractionEnvelope()


def test_envelope_json_schema_exposes_all_blocks():
    schema = ExtractionEnvelope.model_json_schema()
    assert schema["properties"].keys() >= {"doc_type", "doc_type_confidence", "pan", "gst", "cheque", "udyam", "coi"}
