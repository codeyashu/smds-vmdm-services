from __future__ import annotations

from app.documents.classify.doctype import classify_by_anchors


def test_gst_certificate_detected():
    c = classify_by_anchors("FORM GST REG-06 ... GSTIN 27AABCA1234F1Z5 Registration Certificate")
    assert c.doc_type == "IN_GST_CERTIFICATE"
    assert c.ambiguous is False


def test_pan_card_detected():
    c = classify_by_anchors("INCOME TAX DEPARTMENT Permanent Account Number AABCA1234F")
    assert c.doc_type == "IN_PAN_CARD"


def test_cheque_detected():
    c = classify_by_anchors("Account Number 000123456789 IFSC HDFC0001234 MICR 400240001")
    assert c.doc_type == "IN_CANCELLED_CHEQUE"


def test_partnership_deed_detected_before_coi():
    c = classify_by_anchors("DEED OF PARTNERSHIP between partners dated 2020")
    assert c.doc_type == "IN_DEED_OF_PARTNERSHIP"


def test_iec_certificate_detected():
    c = classify_by_anchors("Importer Exporter Code IEC certificate issued by DGFT")
    assert c.doc_type == "IN_IEC_CERTIFICATE"


def test_address_proof_detected():
    c = classify_by_anchors("Address proof utility bill electricity bill")
    assert c.doc_type == "IN_ADDRESS_PROOF"


def test_pan_with_aadhaar_prefers_pan_over_address_proof():
    c = classify_by_anchors(
        "INCOME TAX DEPARTMENT Permanent Account Number AADHAAR UIDAI sole proprietor AOXPS7707K"
    )
    assert c.doc_type == "IN_PAN_CARD"


def test_classify_by_filename_pan_aadhaar():
    from app.documents.classify.doctype import classify_by_filename

    assert classify_by_filename("tax_certificate_pan_aadhaar_card_sole_proprietor_rashid.pdf") == "IN_PAN_CARD"


def test_classify_by_filename_mto():
    from app.documents.classify.doctype import classify_by_filename

    assert classify_by_filename("tax_certificate_mto_iata_cha_certificate_lalit.pdf") == "IN_MTO_IATA_CHA_CERTIFICATE"


def test_unknown_is_ambiguous():
    c = classify_by_anchors("some unrelated invoice text")
    assert c.doc_type is None and c.ambiguous is True
