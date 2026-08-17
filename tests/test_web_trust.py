from app.web_trust.connectors import validate_gb_company_number, validate_in_gstin, validate_in_pan
from app.web_trust.playbook import load_web_trust_playbook
from app.web_trust.types import WebTrustAddressInput, WebTrustVerifyRequest
from app.web_trust.verify import verify_web_trust


def test_load_in_playbook():
    book = load_web_trust_playbook("IN")
    assert book is not None
    assert book.status == "active"
    assert len(book.connectors) >= 2


def test_gstin_valid_checksum():
    result = validate_in_gstin("27AAPFU0939F1ZV")
    assert result is not None
    assert result["taxIdentificationNumber"] == "27AAPFU0939F1ZV"


def test_gstin_rejects_bad_checksum():
    assert validate_in_gstin("27AABCU9603R1ZZ") is None


def test_pan_format():
    assert validate_in_pan("AABCU9603R") is not None
    assert validate_in_pan("BAD") is None


def test_gb_company_number():
    assert validate_gb_company_number("12345678") is not None
    assert validate_gb_company_number("SC123456") is not None
    assert validate_gb_company_number("X") is None


def test_verify_in_with_valid_gstin():
    response = verify_web_trust(
        WebTrustVerifyRequest(
            tradingName="Acme Logistics",
            iso2CountryCode="IN",
            taxIdentificationNumbers=["27AAPFU0939F1ZV"],
            address=WebTrustAddressInput(cityName="Mumbai", iso2CountryCode="IN"),
        )
    )
    assert response.skipped is False
    assert response.reviewId
    assert response.enteredData.get("tradingName") == "Acme Logistics"
    assert response.trustScore is not None


def test_verify_off_country():
    response = verify_web_trust(
        WebTrustVerifyRequest(
            tradingName="Acme",
            iso2CountryCode="US",
        )
    )
    assert response.skipped is True
