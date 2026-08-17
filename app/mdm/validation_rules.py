"""MDM ``getValidationRules`` client — the import source for the v2 rule engine.

No prior caller of this endpoint existed in this repo (the portal calls it directly at
``src/lib/mdm/vendor-search.ts:492``, ``GET {vendorIngestionBaseUrl}/validation/{iso2}/rules``).
This module is that first caller, added for ``app/rules/importer.py`` and for the
back-book replay harness (design plan §F), which needs the same country ruleset the portal
would have fetched.
"""

from __future__ import annotations

from typing import Any

from app.mdm.auth import get_mdm_token
from app.mdm.client import mdm_request_json
from app.mdm.config import get_mdm_settings


def is_validation_rules_configured() -> bool:
    from app.mdm.config import get_mdm_settings_optional

    settings = get_mdm_settings_optional()
    return settings is not None and bool(settings.vendor_ingestion_base_url)


async def get_country_validation_rules(
    iso2_country_code: str,
    *,
    vendor_status_reason: str | None = None,
    entity_type: str | None = None,
) -> dict[str, Any]:
    """Fetch ``CountryValidationRuleResponse`` for one country — the exact shape
    ``app/rules/importer.py`` expects. Uncached at this layer; the importer/replay caller
    is responsible for any caching it needs (unlike the portal's 18h reference cache, a
    batch import or replay run wants a fresh fetch each time it's invoked)."""
    settings = get_mdm_settings()
    if not settings.vendor_ingestion_base_url:
        raise RuntimeError("MDM_VENDOR_INGESTION_BASE_URL is not configured")

    country = iso2_country_code.strip().upper()
    params: list[str] = []
    if vendor_status_reason:
        params.append(f"vendorStatusReason={vendor_status_reason}")
    if entity_type:
        params.append(f"entityType={entity_type}")
    query = f"?{'&'.join(params)}" if params else ""

    url = f"{settings.vendor_ingestion_base_url}/validation/{country}/rules{query}"
    token = await get_mdm_token(settings)
    data = await mdm_request_json(url, token, api_version="1")
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected validation-rules response shape for {country}: {type(data)}")
    return data
