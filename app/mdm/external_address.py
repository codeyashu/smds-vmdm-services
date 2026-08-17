"""CMD external address service."""

from __future__ import annotations

from urllib.parse import urlencode

from app.mdm.auth import get_mdm_token
from app.mdm.client import mdm_request_json
from app.mdm.config import get_mdm_settings


async def select_external_address(
    address_line: str,
    iso_country_code: str,
    location_code: str | None = None,
) -> dict:
    settings = get_mdm_settings()
    token = await get_mdm_token(settings)
    country = iso_country_code.strip().upper()
    params: dict[str, str] = {"address": address_line.strip(), "isoCountryCode": country}
    if location_code and location_code.strip():
        params["locationCode"] = location_code.strip()
    query = urlencode(params)
    url = f"{settings.external_service_base_url}/address/select?{query}"
    result = await mdm_request_json(
        url,
        token,
        headers={"consumer-key": settings.external_service_consumer_key},
        api_version="1",
    )
    return result if isinstance(result, dict) else {}
