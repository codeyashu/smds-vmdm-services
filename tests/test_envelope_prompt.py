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


def _object_schemas(schema: dict) -> list[tuple[str, dict]]:
    """Every object-typed subschema in the document, as (json-pointer-ish label, schema)."""
    found: list[tuple[str, dict]] = []

    def walk(node, path: str) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
            return
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" or "properties" in node:
            found.append((path or "<root>", node))
        for key, child in node.items():
            if key in ("$defs", "properties", "definitions"):
                for name, sub in child.items():
                    walk(sub, f"{path}/{key}/{name}")
            elif key in ("anyOf", "oneOf", "allOf", "prefixItems", "items"):
                walk(child, f"{path}/{key}")

    walk(schema, "")
    return found


def test_envelope_json_schema_is_openai_strict_mode_compatible():
    """OpenAI/Azure structured outputs with strict=True requires, on EVERY object:
    additionalProperties: false, and `required` listing every declared property."""
    schema = envelope_json_schema()
    objects = _object_schemas(schema)

    # Root + the six nested models must all be present, or the walker is not finding them.
    assert len(objects) >= 7, f"expected root + 6 $defs objects, walked {len(objects)}"

    for label, obj in objects:
        assert obj.get("additionalProperties") is False, f"{label} missing additionalProperties: false"
        prop_names = set(obj.get("properties", {}))
        required = set(obj.get("required", []))
        assert required == prop_names, f"{label} required {sorted(required)} != properties {sorted(prop_names)}"


def test_envelope_json_schema_covers_every_nested_model():
    schema = envelope_json_schema()
    assert set(schema["$defs"]) == {
        "ChequeExtraction",
        "CoiExtraction",
        "ExtractedAddress",
        "GstExtraction",
        "PanExtraction",
        "UdyamExtraction",
    }


def test_envelope_json_schema_does_not_mutate_the_pydantic_model_schema():
    """The transform must build a copy — the pydantic model's own schema stays untouched."""
    from app.documents.extract.schemas.india import ExtractionEnvelope

    envelope_json_schema()
    pristine = ExtractionEnvelope.model_json_schema()
    assert "additionalProperties" not in pristine
    assert pristine["required"] == ["doc_type"]
