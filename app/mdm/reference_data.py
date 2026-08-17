"""MDM vendor reference-data client (cities lookup)."""

from __future__ import annotations

import time
from typing import Any

from app.mdm.auth import get_mdm_token
from app.mdm.client import MdmApiError, mdm_request_json_with_headers
from app.mdm.config import get_mdm_settings

_PAGE_SIZE = 100
_MAX_PAGES = 50
_CACHE_TTL_SECONDS = 24 * 3600

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def is_reference_data_configured() -> bool:
    from app.mdm.config import get_mdm_settings_optional

    settings = get_mdm_settings_optional()
    return settings is not None and bool(settings.vendor_reference_base_url)


async def get_cities_for_country(country_code: str) -> list[dict[str, Any]]:
    """Full cities list for country — cached 24h in-process."""
    country = country_code.strip().upper()
    if not country:
        return []

    cached = _cache.get(country)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    settings = get_mdm_settings()
    if not settings.vendor_reference_base_url:
        return []

    token = await get_mdm_token(settings)
    items: list[dict[str, Any]] = []

    async def fetch_page(page: int) -> tuple[list[dict[str, Any]], int | None]:
        url = (
            f"{settings.vendor_reference_base_url}/vendors/reference-data/cities/{country}"
            f"?page={page}&limit={_PAGE_SIZE}"
        )
        try:
            data, headers = await mdm_request_json_with_headers(url, token, api_version="1")
        except MdmApiError as exc:
            if exc.status == 404:
                return [], None
            raise
        page_items = data if isinstance(data, list) else []
        last_page_raw = headers.get("Last-Page")
        last_page = int(last_page_raw) if last_page_raw is not None else None
        return page_items, last_page

    first, last_page = await fetch_page(1)
    if not first:
        _cache[country] = (now + _CACHE_TTL_SECONDS, [])
        return []

    items.extend(first)
    if len(first) < _PAGE_SIZE:
        _cache[country] = (now + _CACHE_TTL_SECONDS, items)
        return items

    cap = min(last_page or _MAX_PAGES, _MAX_PAGES)
    for page in range(2, cap + 1):
        page_items, _ = await fetch_page(page)
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < _PAGE_SIZE:
            break

    _cache[country] = (now + _CACHE_TTL_SECONDS, items)
    return items
