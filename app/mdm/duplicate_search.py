"""Duplicate vendor search — port of portal ingest duplicate API."""

from __future__ import annotations

import re
from typing import Any

from app.mdm.auth import get_mdm_token
from app.mdm.client import MdmApiError, mdm_request_json_with_headers
from app.mdm.config import get_mdm_settings

DUPLICATE_CITY_NAME_PATTERN = re.compile(r"^[a-zA-Z.,'&()/\- ]{2,50}$")


def build_duplicate_request(form_state: dict[str, Any], country: str) -> dict[str, Any]:
    addresses = form_state.get("postalAddresses")
    address = addresses[0] if isinstance(addresses, list) and addresses else {}
    if not isinstance(address, dict):
        address = {}

    tax_root = form_state.get("taxInformation")
    tax_numbers: list[dict[str, Any]] = []
    if isinstance(tax_root, dict) and isinstance(tax_root.get("taxIdentificationNumbers"), list):
        tax_numbers = [row for row in tax_root["taxIdentificationNumbers"] if isinstance(row, dict)]

    tax_informations: list[dict[str, Any]] = []
    for index, entry in enumerate(tax_numbers):
        tin = entry.get("taxIdentificationNumber")
        if not isinstance(tin, str) or not tin.strip():
            continue
        tax_informations.append(
            {
                "taxIdentificationNumber": tin.strip(),
                "iso2CountryCode": entry.get("iso2CountryCode") or country,
                "taxIdentificationTypeCode": entry.get("taxIdentificationTypeCode"),
                "taxTypeCode": entry.get("taxTypeCode") or f"TAXNO{index + 1}",
            }
        )

    city_candidate = address.get("cityName") or address.get("cityCode")
    city_name = None
    if isinstance(city_candidate, str) and DUPLICATE_CITY_NAME_PATTERN.fullmatch(city_candidate.strip()):
        city_name = city_candidate.strip()

    payload: dict[str, Any] = {
        "tradingName": str(form_state.get("tradingName") or "").strip(),
        "iso2CountryCode": country,
        "streetName": address.get("streetName"),
        "postalCode": address.get("postalCode"),
    }
    if city_name:
        payload["cityName"] = city_name
    if tax_informations:
        payload["taxInformations"] = tax_informations
    return payload


async def search_duplicate_vendors(request: dict[str, Any]) -> dict[str, Any]:
    settings = get_mdm_settings()
    token = await get_mdm_token(settings)
    url = f"{settings.vendor_search_base_url}/vendors/duplicates"

    try:
        data, headers = await mdm_request_json_with_headers(
            url,
            token,
            method="POST",
            json_body=request,
            headers={"content-type": "application/json"},
            api_version="1",
        )
        items = data if isinstance(data, list) else []
        return {
            "items": items,
            "pagination": {
                "currentPage": _header_int(headers, "Current-Page"),
                "lastPage": _header_int(headers, "Last-Page"),
                "totalItemCount": _header_int(headers, "Total-Item-Count"),
            },
        }
    except MdmApiError as exc:
        if exc.status == 404:
            return {
                "items": [],
                "pagination": {"currentPage": None, "lastPage": None, "totalItemCount": None},
            }
        raise


def _header_int(headers: Any, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
