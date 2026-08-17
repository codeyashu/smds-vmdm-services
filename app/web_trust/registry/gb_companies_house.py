"""UK Companies House live registry lookup."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.web_trust.tax_validators import validate_gb_company_number

COMPANIES_HOUSE_API_BASE = "https://api.company-information.service.gov.uk"
COMPANIES_HOUSE_PUBLIC_BASE = "https://find-and-update.company-information.service.gov.uk"


def companies_house_api_key() -> str | None:
    value = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    return value or None


def _join_address_lines(address: dict[str, Any]) -> str | None:
    parts = [
        address.get("premises"),
        address.get("address_line_1"),
        address.get("address_line_2"),
    ]
    joined = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
    return joined or None


def lookup_gb_company(company_number: str) -> dict[str, Any] | None:
    """Fetch company profile from Companies House. Returns None when key missing or not found."""
    api_key = companies_house_api_key()
    if not api_key:
        return None

    normalized = company_number.strip().upper().replace(" ", "")
    if not validate_gb_company_number(normalized):
        return None

    url = f"{COMPANIES_HOUSE_API_BASE}/company/{normalized}"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, auth=(api_key, ""))
    except httpx.HTTPError:
        return None

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        return None

    payload = response.json()
    office = payload.get("registered_office_address") or {}
    number = str(payload.get("company_number") or normalized)
    return {
        "taxIdentificationNumber": number,
        "tradingName": payload.get("company_name"),
        "legalName": payload.get("company_name"),
        "companyStatus": payload.get("company_status"),
        "street": _join_address_lines(office),
        "cityName": office.get("locality") or office.get("region"),
        "postalCode": office.get("postal_code"),
        "iso2CountryCode": "GB",
        "status": "registry_confirmed",
        "sourceUrl": f"{COMPANIES_HOUSE_PUBLIC_BASE}/company/{number}",
    }
