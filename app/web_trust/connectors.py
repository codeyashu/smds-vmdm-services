"""Country-specific deterministic connectors (no data fill — verification only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.web_trust.address_review import review_bill_to_address
from app.web_trust.tax_validators import (
    validate_gb_company_number,
    validate_in_gstin,
    validate_in_pan,
)

# Re-export for tests and address_review lazy imports.
__all__ = [
    "run_connector",
    "validate_gb_company_number",
    "validate_in_gstin",
    "validate_in_pan",
]


def run_connector(
    connector_type: str,
    *,
    tax_ids: list[str],
    trading_name: str | None,
    legal_name: str | None = None,
    address: dict[str, Any] | None = None,
    country: str | None = None,
    website: str | None = None,
) -> list[dict[str, Any]]:
    """Return zero or more verification hits from a connector."""
    hits: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    if connector_type == "bill_to_address_review":
        review = review_bill_to_address(address, country=country or "", tax_ids=tax_ids)
        hits.append(
            {
                "connectorId": "bill_to_address",
                "sourceType": "format_validator",
                "verificationMode": "format_check",
                "sourceUrl": None,
                "displayName": "Bill-to address review (BILL_TO only)",
                "extracted": review["extracted"],
                "fieldEvidence": review["fieldEvidence"],
                "completenessScore": review["completenessScore"],
                "limitations": review["limitations"],
                "retrievedAt": now,
                "authorityWeight": 0.95,
            }
        )
        return hits

    if connector_type == "in_gstin_format":
        for tax_id in tax_ids:
            extracted = validate_in_gstin(tax_id)
            if not extracted:
                continue
            hits.append(
                {
                    "connectorId": "in_gstin",
                    "sourceType": "format_validator",
                    "verificationMode": "format_check",
                    "sourceUrl": "https://www.gst.gov.in/",
                    "displayName": f"GSTIN format check ({extracted['taxIdentificationNumber']})",
                    "extracted": extracted,
                    "retrievedAt": now,
                    "authorityWeight": 1.0,
                }
            )
        return hits

    if connector_type == "in_pan_format":
        for tax_id in tax_ids:
            extracted = validate_in_pan(tax_id)
            if not extracted:
                continue
            hits.append(
                {
                    "connectorId": "in_pan",
                    "sourceType": "format_validator",
                    "verificationMode": "format_check",
                    "sourceUrl": "https://www.incometax.gov.in/",
                    "displayName": f"PAN format check ({extracted['taxIdentificationNumber']})",
                    "extracted": extracted,
                    "retrievedAt": now,
                    "authorityWeight": 0.9,
                }
            )
        return hits

    if connector_type == "gb_company_number_format":
        for tax_id in tax_ids:
            extracted = validate_gb_company_number(tax_id)
            if not extracted:
                continue
            hits.append(
                {
                    "connectorId": "gb_company_number",
                    "sourceType": "format_validator",
                    "verificationMode": "format_check",
                    "sourceUrl": "https://find-and-update.company-information.service.gov.uk/",
                    "displayName": f"Companies House number format ({extracted['taxIdentificationNumber']})",
                    "extracted": extracted,
                    "retrievedAt": now,
                    "authorityWeight": 0.85,
                }
            )
        return hits

    if connector_type == "in_gstin_live_lookup":
        from app.web_trust.registry.in_gstin import lookup_in_gstin

        gstin = next((tax_id for tax_id in tax_ids if validate_in_gstin(tax_id)), None)
        if not gstin:
            return hits

        result = lookup_in_gstin(gstin)
        if result.limitation:
            hits.append(
                {
                    "connectorId": "in_gstin_live",
                    "limitations": [result.limitation],
                    "skipMatchedRecord": True,
                }
            )
        if result.extracted:
            number = result.extracted["taxIdentificationNumber"]
            hits.append(
                {
                    "connectorId": "in_gstin_live",
                    "sourceType": "government_registry",
                    "verificationMode": "live_registry",
                    "sourceUrl": result.extracted.get("sourceUrl"),
                    "displayName": f"GSTIN registry ({number})",
                    "extracted": result.extracted,
                    "retrievedAt": now,
                    "authorityWeight": 1.0,
                }
            )
        return hits

    if connector_type == "gb_companies_house_lookup":
        from app.web_trust.registry.gb_companies_house import lookup_gb_company

        for tax_id in tax_ids:
            extracted = lookup_gb_company(tax_id)
            if not extracted:
                continue
            company_number = extracted["taxIdentificationNumber"]
            hits.append(
                {
                    "connectorId": "gb_companies_house",
                    "sourceType": "government_registry",
                    "verificationMode": "live_registry",
                    "sourceUrl": extracted.get("sourceUrl"),
                    "displayName": f"Companies House ({company_number})",
                    "extracted": extracted,
                    "retrievedAt": now,
                    "authorityWeight": 1.0,
                }
            )
        return hits

    if connector_type == "company_registry_lookup":
        from app.web_trust.enrichment import lookup_commercial_directory

        hit = lookup_commercial_directory(
            country=country or "",
            trading_name=trading_name,
            legal_name=legal_name,
            tax_ids=tax_ids,
            address=address,
            website=website,
        )
        if hit:
            hits.append({**hit, "retrievedAt": now})
        return hits

    if connector_type == "company_website_probe":
        from app.web_trust.enrichment import probe_company_website

        hit = probe_company_website(website)
        if hit:
            hits.append({**hit, "retrievedAt": now})
        return hits

    return hits
