"""Tests for UK Companies House live registry connector."""

from unittest.mock import MagicMock, patch

from app.web_trust.registry.gb_companies_house import lookup_gb_company
from app.web_trust.types import WebTrustAddressInput, WebTrustVerifyRequest
from app.web_trust.verify import verify_web_trust

SAMPLE_COMPANY = {
    "company_number": "12345678",
    "company_name": "ACME LOGISTICS LTD",
    "company_status": "active",
    "registered_office_address": {
        "address_line_1": "1 Test Street",
        "locality": "London",
        "postal_code": "SW1A 1AA",
        "country": "England",
    },
}


def test_lookup_gb_company_without_api_key(monkeypatch):
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    assert lookup_gb_company("12345678") is None


def test_lookup_gb_company_success(monkeypatch):
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "test-key")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = SAMPLE_COMPANY

    with patch("app.web_trust.registry.gb_companies_house.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        extracted = lookup_gb_company("12345678")

    assert extracted is not None
    assert extracted["legalName"] == "ACME LOGISTICS LTD"
    assert extracted["postalCode"] == "SW1A 1AA"
    assert extracted["status"] == "registry_confirmed"
    client.get.assert_called_once()
    assert client.get.call_args.args[0].endswith("/company/12345678")


def test_lookup_gb_company_not_found(monkeypatch):
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "test-key")
    response = MagicMock()
    response.status_code = 404

    with patch("app.web_trust.registry.gb_companies_house.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        assert lookup_gb_company("12345678") is None


def test_verify_gb_uses_live_registry_when_configured(monkeypatch):
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "test-key")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = SAMPLE_COMPANY

    with patch("app.web_trust.registry.gb_companies_house.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        client_cls.return_value = client

        result = verify_web_trust(
            WebTrustVerifyRequest(
                tradingName="Acme Logistics",
                legalName="ACME LOGISTICS LTD",
                iso2CountryCode="GB",
                taxIdentificationNumbers=["12345678"],
                address=WebTrustAddressInput(
                    streetName="1 Test Street",
                    cityName="London",
                    postalCode="SW1A 1AA",
                    iso2CountryCode="GB",
                ),
            )
        )

    assert result.skipped is False
    live = next(
        record for record in result.matchedRecords if record.connectorId == "gb_companies_house"
    )
    assert live.verificationMode == "live_registry"
    assert live.matchScore >= 85
    assert result.verificationDisclaimer is not None
    assert "Live registry" in result.verificationDisclaimer
    assert not any(record.connectorId == "gb_company_number" for record in result.matchedRecords)


def test_verify_gb_format_only_without_api_key(monkeypatch):
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    result = verify_web_trust(
        WebTrustVerifyRequest(
            tradingName="Acme Logistics",
            iso2CountryCode="GB",
            taxIdentificationNumbers=["12345678"],
            address=WebTrustAddressInput(cityName="London", postalCode="SW1A 1AA", iso2CountryCode="GB"),
        )
    )
    assert result.skipped is False
    assert any(record.connectorId == "gb_company_number" for record in result.matchedRecords)
    assert result.verificationDisclaimer is not None
    assert "Format and structure" in result.verificationDisclaimer
