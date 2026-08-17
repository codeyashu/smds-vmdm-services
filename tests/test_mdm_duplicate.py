"""Tests for duplicate request builder."""

from app.mdm.duplicate_search import build_duplicate_request


def test_build_duplicate_request_includes_tax_slots():
    form_state = {
        "tradingName": "Acme",
        "postalAddresses": [{"cityName": "Mumbai", "streetName": "Main St"}],
        "taxInformation": {
            "taxIdentificationNumbers": [
                {"taxIdentificationNumber": "ABCDE1234F", "iso2CountryCode": "IN"},
            ],
        },
    }
    req = build_duplicate_request(form_state, "IN")
    assert req["tradingName"] == "Acme"
    assert req["iso2CountryCode"] == "IN"
    assert req["taxInformations"][0]["taxTypeCode"] == "TAXNO1"


def test_build_duplicate_request_skips_opaque_city_code():
    form_state = {
        "tradingName": "Acme",
        "postalAddresses": [{"cityCode": "DUTKZXLEQ9F1L"}],
    }
    req = build_duplicate_request(form_state, "IN")
    assert "cityName" not in req
