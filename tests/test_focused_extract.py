"""Focused third-pass extraction — pure logic tests."""

from __future__ import annotations

from app.documents.extract.focused import (
    FOCUSED_SPECS,
    apply_focused_extractions,
    apply_pan_number_boost,
    merge_envelopes,
    missing_critical_fields,
)
from app.documents.extract.schemas.india import (
    AddressProofExtraction,
    ChequeExtraction,
    CoiExtraction,
    ExtractionEnvelope,
    ExtractedAddress,
    GstExtraction,
    IecExtraction,
    MtoExtraction,
    PanExtraction,
    PartnershipExtraction,
    UdyamExtraction,
)
from tests.fakes import FakeLlm


def test_missing_critical_fields_covers_all_focused_doc_types():
    assert set(FOCUSED_SPECS) == {
        "IN_PAN_CARD",
        "IN_GST_CERTIFICATE",
        "IN_IEC_CERTIFICATE",
        "IN_CERTIFICATE_OF_INCORPORATION",
        "IN_MTO_IATA_CHA_CERTIFICATE",
        "IN_CANCELLED_CHEQUE",
        "IN_DEED_OF_PARTNERSHIP",
        "IN_UDYAM_CERTIFICATE",
        "IN_ADDRESS_PROOF",
    }


def test_missing_critical_fields_pan():
    envelope = ExtractionEnvelope(doc_type="IN_PAN_CARD", pan=PanExtraction(holder_name="A"))
    assert missing_critical_fields(envelope) == ["PAN card"]


def test_missing_critical_fields_gst_complete():
    envelope = ExtractionEnvelope(
        doc_type="IN_GST_CERTIFICATE",
        gst=GstExtraction(gstin="27AABCA1234F1Z5", confidence=0.9),
    )
    assert missing_critical_fields(envelope) == []


def test_merge_envelopes_keeps_primary_doc_type():
    primary = ExtractionEnvelope(
        doc_type="IN_PAN_CARD",
        pan=PanExtraction(holder_name="Yogesh Saruparia", confidence=0.8),
    )
    secondary = ExtractionEnvelope(
        doc_type="IN_ADDRESS_PROOF",
        pan=PanExtraction(pan="ABCDE1234F", holder_name="Other", confidence=0.95),
    )
    merged = merge_envelopes(primary, secondary)
    assert merged.doc_type == "IN_PAN_CARD"
    assert merged.pan is not None
    assert merged.pan.pan == "ABCDE1234F"
    assert merged.pan.holder_name == "Yogesh Saruparia"


async def test_apply_focused_extractions_merges_pan():
    envelope = ExtractionEnvelope(
        doc_type="IN_PAN_CARD",
        pan=PanExtraction(holder_name="Yogesh Saruparia", confidence=0.8),
    )
    llm = FakeLlm([{"pan": "ABCDE1234F", "holder_name": "Yogesh Saruparia", "confidence": 0.95}])
    result = await apply_focused_extractions(llm, envelope, ["img"], 30.0)
    assert result.pan is not None
    assert result.pan.pan == "ABCDE1234F"


async def test_apply_pan_number_boost_rejects_invalid_shape():
    envelope = ExtractionEnvelope(
        doc_type="IN_PAN_CARD",
        pan=PanExtraction(holder_name="Yogesh Saruparia", confidence=0.8),
    )
    llm = FakeLlm([{"pan": "NOTVALID12", "confidence": 0.9}])
    result = await apply_pan_number_boost(llm, envelope, ["img"], 30.0)
    assert result.pan is not None
    assert result.pan.pan is None


async def test_apply_pan_number_boost_accepts_valid_pan():
    envelope = ExtractionEnvelope(doc_type="IN_PAN_CARD", pan=PanExtraction(holder_name="Yogesh"))
    llm = FakeLlm([{"pan": "ABCDE1234F", "confidence": 0.95}])
    result = await apply_pan_number_boost(llm, envelope, ["img"], 30.0)
    assert result.pan is not None
    assert result.pan.pan == "ABCDE1234F"


async def test_apply_focused_extractions_address_proof():
    envelope = ExtractionEnvelope(doc_type="IN_ADDRESS_PROOF", address_proof=AddressProofExtraction())
    llm = FakeLlm(
        [
            {
                "holder_name": "ACME",
                "address": {
                    "postal_code": "560001",
                    "city_name": "Bengaluru",
                    "street_name": "MG Road",
                },
                "confidence": 0.9,
            }
        ]
    )
    result = await apply_focused_extractions(llm, envelope, ["img"], 30.0)
    assert result.address_proof is not None
    assert result.address_proof.address is not None
    assert result.address_proof.address.postal_code == "560001"


def test_incomplete_cheque_needs_ifsc_or_account():
    spec = FOCUSED_SPECS["IN_CANCELLED_CHEQUE"]
    assert spec.is_incomplete(ExtractionEnvelope(doc_type="IN_CANCELLED_CHEQUE"))
    assert not spec.is_incomplete(
        ExtractionEnvelope(
            doc_type="IN_CANCELLED_CHEQUE",
            cheque=ChequeExtraction(ifsc="HDFC0001234", confidence=0.9),
        )
    )


def test_incomplete_partnership_needs_name_or_registration():
    spec = FOCUSED_SPECS["IN_DEED_OF_PARTNERSHIP"]
    assert spec.is_incomplete(ExtractionEnvelope(doc_type="IN_DEED_OF_PARTNERSHIP"))
    assert not spec.is_incomplete(
        ExtractionEnvelope(
            doc_type="IN_DEED_OF_PARTNERSHIP",
            partnership=PartnershipExtraction(firm_name="ACME Partners", confidence=0.9),
        )
    )
