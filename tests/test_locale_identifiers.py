from app.documents.rules.locale_patterns import (
    format_us_ein,
    is_valid_ae_trn,
    is_valid_gb_crn,
    is_valid_gb_vat,
    is_valid_us_ein,
    is_valid_uscc,
)
from app.documents.validation.identifiers import (
    validate_ein,
    validate_gb_crn,
    validate_gb_vat,
    validate_trn,
    validate_uscc,
)


def test_uscc_checksum():
    assert is_valid_uscc("91310000MA1FL1RD1C")
    assert not is_valid_uscc("91310000MA1FL1RD1X")


def test_ae_trn_shape():
    assert is_valid_ae_trn("100123456700003")
    assert not is_valid_ae_trn("200123456700003")


def test_us_ein_shape():
    assert is_valid_us_ein("12-3456789")
    assert validate_ein("123456789").normalized == "12-3456789"


def test_gb_identifiers():
    assert is_valid_gb_vat("GB123456789")
    assert is_valid_gb_crn("12345678")
    assert validate_gb_crn("SC123456").ok
