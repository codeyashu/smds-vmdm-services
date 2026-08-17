"""Aadhaar-only upload detection — filename says pan_aadhaar but scan is Aadhaar only."""

from __future__ import annotations

from app.documents.classify.doctype import (
    extract_aadhaar_number,
    is_aadhaar_only_document,
    resolve_filename_hint,
)

_AADHAAR_OCR = """
Enrolment No.: 2017/60101/25309
Yogesh Saruparia
Address: plot no. 5 B, Udaipur Rajasthan - 313001
9745 3493 5742
Unique Identification Authority of India
"""


def test_is_aadhaar_only_document():
    assert is_aadhaar_only_document(_AADHAAR_OCR)
    assert not is_aadhaar_only_document("Permanent Account Number ABCDE1234F Income Tax Department")


def test_extract_aadhaar_number():
    assert extract_aadhaar_number(_AADHAAR_OCR) == "974534935742"


def test_resolve_filename_hint_remaps_aadhaar_only_pan_upload():
    hinted = resolve_filename_hint(
        "tax_certificate_pan_aadhaar_card_sole_proprietor.pdf",
        _AADHAAR_OCR,
    )
    assert hinted == "IN_ADDRESS_PROOF"
