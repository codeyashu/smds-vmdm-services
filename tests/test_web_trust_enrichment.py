"""Tests for TrustLens enrichment connectors."""

from __future__ import annotations

from unittest.mock import patch

from app.web_trust.enrichment import probe_company_website, lookup_commercial_directory
from app.web_trust.scoring import build_vendor_field_evidence


def test_probe_company_website_extracts_title():
    html = "<html><head><title>Acme Logistics Pvt Ltd</title></head><body></body></html>"
    with patch("app.web_trust.enrichment.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value.status_code = 200
        client.get.return_value.text = html
        hit = probe_company_website("acme.example.com")
    assert hit is not None
    assert hit["sourceType"] == "company_website"
    assert "Acme Logistics" in hit["extracted"]["tradingName"]


def test_tax_match_score_handles_multi_id_vendor_entry():
    evidence = build_vendor_field_evidence(
        {"taxIdentificationNumbers": ["AALCS3056Q", "33AALCS3056Q1ZT"]},
        {"taxIdentificationNumber": "AALCS3056Q"},
    )
    tax_row = next(row for row in evidence if row.field == "tax")
    assert tax_row.score == 100


@patch("app.web_trust.enrichment.is_mdm_configured", return_value=False)
def test_commercial_directory_skips_when_mdm_not_configured(_mock: object):
    assert (
        lookup_commercial_directory(
            country="IN",
            trading_name="Acme",
            legal_name=None,
            tax_ids=[],
            address={},
            website=None,
        )
        is None
    )
