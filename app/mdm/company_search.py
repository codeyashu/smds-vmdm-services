"""Company external registry search."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from app.mdm.auth import get_company_search_token
from app.mdm.client import mdm_request_json
from app.mdm.config import get_mdm_settings


def _build_query(params: dict[str, Any]) -> str:
    cleaned = {k: str(v) for k, v in params.items() if v is not None and v != ""}
    return urlencode(cleaned)


async def search_company_external(params: dict[str, Any]) -> dict[str, Any]:
    settings = get_mdm_settings()
    token = await get_company_search_token(settings)
    query = _build_query(
        {
            "iso2CountryCode": params.get("iso2CountryCode"),
            "tradingName": params.get("tradingName"),
            "taxReference": params.get("taxReference"),
            "city": params.get("city"),
            "streetName": params.get("streetName"),
            "streetNumber": params.get("streetNumber"),
            "postalCode": params.get("postalCode"),
            "regionName": params.get("regionName"),
            "url": params.get("url"),
            "phone": params.get("phone"),
            "page": params.get("page"),
            "limit": params.get("limit"),
        }
    )
    url = f"{settings.company_search_base_url}/companies?{query}"
    result = await mdm_request_json(
        url,
        token,
        headers={"Consumer-Key": settings.company_search_consumer_key},
        api_version="2",
    )
    if not isinstance(result, dict):
        return {"customerSummaries": []}
    summaries = result.get("customerSummaries") or []
    if isinstance(summaries, list):
        result["customerSummaries"] = [_normalize_summary(row) for row in summaries if isinstance(row, dict)]
    return result


def _normalize_summary(raw: dict[str, Any]) -> dict[str, Any]:
    company_name = str(raw.get("companyName") or raw.get("legalName") or "").strip()
    source_type = raw.get("sourceType")
    if source_type not in ("DNB", "BVD"):
        if raw.get("bureauVanDijkDataId") is not None:
            source_type = "BVD"
        elif raw.get("duns") is not None or raw.get("dunsNumber") is not None:
            source_type = "DNB"
        else:
            source_type = "BVD"
    return {
        **raw,
        "companyName": company_name,
        "sourceType": source_type,
    }
