"""Tests for India GSTIN live registry connector."""

from unittest.mock import MagicMock, patch

from app.web_trust.registry.in_gstin import lookup_in_gstin
from app.web_trust.types import WebTrustAddressInput, WebTrustVerifyRequest
from app.web_trust.verify import verify_web_trust

GSP_ACTIVE_PAYLOAD = {
    "gstin": "27AAPFU0939F1ZV",
    "legalName": "ACME LOGISTICS PRIVATE LIMITED",
    "tradingName": "Acme Logistics",
    "gstStatus": "Active",
    "principalPlaceOfBusiness": {
        "street": "1 MG Road Fort",
        "cityName": "Mumbai",
        "postalCode": "400001",
        "stateCode": "27",
    },
}


def test_lookup_in_gstin_without_credentials(monkeypatch):
    monkeypatch.delenv("IN_GST_GSP_API_KEY", raising=False)
    assert lookup_in_gstin("27AAPFU0939F1ZV").extracted is None


def test_lookup_in_gstin_fixture_mode(monkeypatch):
    monkeypatch.setenv("IN_GST_GSP_API_KEY", "fixture")
    result = lookup_in_gstin("27AAPFU0939F1ZV")
    assert result.extracted is not None
    assert result.extracted["legalName"] == "ACME LOGISTICS PRIVATE LIMITED"
    assert result.extracted["postalCode"] == "400001"


def test_lookup_in_gstin_fixture_not_found(monkeypatch):
    monkeypatch.setenv("IN_GST_GSP_API_KEY", "fixture")
    result = lookup_in_gstin("24AAACC1206D1ZM")
    assert result.extracted is None
    assert result.limitation is not None


def test_lookup_in_gstin_gsp_http_success(monkeypatch):
    monkeypatch.setenv("IN_GST_GSP_API_KEY", "live-key")
    monkeypatch.setenv("IN_GST_GSP_BASE_URL", "https://gsp.example.com")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = GSP_ACTIVE_PAYLOAD

    with patch("app.web_trust.registry.in_gstin.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        result = lookup_in_gstin("27AAPFU0939F1ZV")

    assert result.extracted is not None
    assert result.extracted["gstStatus"] == "Active"
    client.get.assert_called_once()


def test_lookup_in_gstin_gsp_inactive(monkeypatch):
    monkeypatch.setenv("IN_GST_GSP_API_KEY", "live-key")
    monkeypatch.setenv("IN_GST_GSP_BASE_URL", "https://gsp.example.com")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {**GSP_ACTIVE_PAYLOAD, "gstStatus": "Cancelled"}

    with patch("app.web_trust.registry.in_gstin.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        result = lookup_in_gstin("27AAPFU0939F1ZV")

    assert result.extracted is None
    assert "inactive" in (result.limitation or "").lower()


def test_verify_in_uses_live_registry_with_fixture(monkeypatch):
    monkeypatch.setenv("IN_GST_GSP_API_KEY", "fixture")
    result = verify_web_trust(
        WebTrustVerifyRequest(
            tradingName="Acme Logistics",
            legalName="ACME LOGISTICS PRIVATE LIMITED",
            iso2CountryCode="IN",
            taxIdentificationNumbers=["27AAPFU0939F1ZV"],
            address=WebTrustAddressInput(
                streetName="1 MG Road Fort",
                cityName="Mumbai",
                postalCode="400001",
                iso2CountryCode="IN",
            ),
        )
    )

    assert result.skipped is False
    live = next(record for record in result.matchedRecords if record.connectorId == "in_gstin_live")
    assert live.verificationMode == "live_registry"
    assert live.matchScore >= 85
    assert not any(record.connectorId == "in_gstin" for record in result.matchedRecords)
    assert result.trustScore is not None
    assert result.trustScore > 70


def test_verify_in_format_only_without_gsp_key(monkeypatch):
    monkeypatch.delenv("IN_GST_GSP_API_KEY", raising=False)
    result = verify_web_trust(
        WebTrustVerifyRequest(
            tradingName="Acme Logistics",
            iso2CountryCode="IN",
            taxIdentificationNumbers=["27AAPFU0939F1ZV"],
            address=WebTrustAddressInput(cityName="Mumbai", postalCode="400001", iso2CountryCode="IN"),
        )
    )
    assert any(record.connectorId == "in_gstin" for record in result.matchedRecords)
    assert not any(record.connectorId == "in_gstin_live" for record in result.matchedRecords)
    assert result.verificationDisclaimer is not None
