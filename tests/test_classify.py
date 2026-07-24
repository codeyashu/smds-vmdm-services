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


def test_unknown_is_ambiguous():
    c = classify_by_anchors("some unrelated invoice text")
    assert c.doc_type is None and c.ambiguous is True
