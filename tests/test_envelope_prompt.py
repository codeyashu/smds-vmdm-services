"""Envelope prompt builder — pure string/list assembly, no network."""

from __future__ import annotations

from app.documents.classify.doctype import Classification
from app.documents.extract.prompts.india.envelope import build_envelope_messages, envelope_json_schema


def test_messages_have_system_then_user_role():
    hint = Classification(doc_type="IN_GST_CERTIFICATE", confidence=0.8, ambiguous=False)
    messages = build_envelope_messages("GSTIN 27AABCA1234F1Z5", ["base64img"], hint)
    assert messages[0].role == "system"
    assert messages[1].role == "user"


def test_system_message_lists_every_doc_type():
    hint = Classification(doc_type=None, confidence=0.0, ambiguous=True)
    messages = build_envelope_messages("text", [], hint)
    for doc_type in ("IN_PAN_CARD", "IN_GST_CERTIFICATE", "IN_CANCELLED_CHEQUE", "UNKNOWN"):
        assert doc_type in messages[0].text


def test_user_message_includes_hint_and_ocr_text():
    hint = Classification(doc_type="IN_GST_CERTIFICATE", confidence=0.8, ambiguous=False)
    messages = build_envelope_messages("GSTIN 27AABCA1234F1Z5 some text", ["img"], hint)
    assert "IN_GST_CERTIFICATE" in messages[1].text
    assert "GSTIN 27AABCA1234F1Z5" in messages[1].text


def test_user_message_handles_no_hint():
    hint = Classification(doc_type=None, confidence=0.0, ambiguous=True)
    messages = build_envelope_messages("unclear text", [], hint)
    assert "UNKNOWN" in messages[1].text


def test_long_ocr_text_is_truncated():
    messages = build_envelope_messages(
        "A" * 20000, [], Classification(doc_type=None, confidence=0.0, ambiguous=True)
    )
    assert len(messages[1].text) < 13000


def test_images_capped_at_five():
    images = [f"img{i}" for i in range(10)]
    messages = build_envelope_messages(
        "text", images, Classification(doc_type=None, confidence=0.0, ambiguous=True)
    )
    assert len(messages[1].images_b64) == 5


def test_envelope_json_schema_matches_model_properties():
    schema = envelope_json_schema()
    assert schema["properties"].keys() >= {"doc_type", "pan", "gst", "cheque", "udyam", "coi"}
