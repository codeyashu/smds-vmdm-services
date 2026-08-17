"""OAuth client-credentials token cache for MDM APIs."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, TypeVar

import httpx

from app.mdm.config import MdmSettings

T = TypeVar("T")

_token_cache: dict[str, tuple[str, float]] = {}
_lock = asyncio.Lock()
REFRESH_BUFFER_SECONDS = 60


async def fetch_client_credentials_token(
    settings: MdmSettings, *, client_id: str, client_secret: str
) -> tuple[str, float]:
    body = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(
            settings.oauth_token_url,
            data=body,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        res.raise_for_status()
        payload = res.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("OAuth token response missing access_token")
    expires_in = float(payload.get("expires_in") or 300)
    return token, expires_in


async def get_token(cache_key: str, fetcher: Callable[[], asyncio.Future[tuple[str, float]]]) -> str:
    now = time.time()
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    async with _lock:
        cached = _token_cache.get(cache_key)
        if cached and cached[1] > now:
            return cached[0]
        token, expires_in = await fetcher()
        expiry = now + max(expires_in - REFRESH_BUFFER_SECONDS, 30)
        _token_cache[cache_key] = (token, expiry)
        return token


async def get_mdm_token(settings: MdmSettings) -> str:
    async def _fetch() -> tuple[str, float]:
        return await fetch_client_credentials_token(
            settings,
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
        )

    return await get_token("mdm-default", _fetch)


async def get_company_search_token(settings: MdmSettings) -> str:
    async def _fetch() -> tuple[str, float]:
        return await fetch_client_credentials_token(
            settings,
            client_id=settings.company_search_oauth_client_id,
            client_secret=settings.company_search_oauth_client_secret,
        )

    return await get_token("company-search", _fetch)


async def get_access_policy_token(settings: MdmSettings) -> str:
    async def _fetch() -> tuple[str, float]:
        return await fetch_client_credentials_token(
            settings,
            client_id=settings.access_policy_oauth_client_id,
            client_secret=settings.access_policy_oauth_client_secret,
        )

    return await get_token("access-policy", _fetch)
