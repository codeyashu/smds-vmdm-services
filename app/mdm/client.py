"""Low-level async MDM HTTP client."""

from __future__ import annotations

from typing import Any

import httpx


class MdmApiError(Exception):
    def __init__(self, status: int, message: str, detailed_errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.status = status
        self.detailed_errors = detailed_errors or []


async def mdm_request_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    api_version: str = "1",
    timeout: float = 30.0,
) -> Any:
    request_headers: dict[str, str] = {
        "authorization": f"Bearer {token}",
        **(headers or {}),
    }
    if api_version:
        request_headers["api-version"] = api_version
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.request(method, url, headers=request_headers, json=json_body)

    if not res.is_success:
        message = res.text
        detailed: list[dict[str, Any]] = []
        try:
            body = res.json()
            if isinstance(body, dict):
                message = str(body.get("errorMessage") or message)
                raw_errors = body.get("detailedErrors")
                if isinstance(raw_errors, list):
                    detailed = raw_errors
        except Exception:  # noqa: BLE001
            pass
        raise MdmApiError(res.status_code, message or f"MDM request failed ({res.status_code})", detailed)

    if res.headers.get("content-type", "").startswith("application/json"):
        return res.json()
    text = res.text
    return text


async def mdm_request_json_with_headers(
    url: str,
    token: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    api_version: str = "1",
    timeout: float = 30.0,
) -> tuple[Any, httpx.Headers]:
    request_headers: dict[str, str] = {
        "authorization": f"Bearer {token}",
        **(headers or {}),
    }
    if api_version:
        request_headers["api-version"] = api_version
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.request(method, url, headers=request_headers, json=json_body)

    if not res.is_success:
        message = res.text
        try:
            body = res.json()
            if isinstance(body, dict):
                message = str(body.get("errorMessage") or message)
        except Exception:  # noqa: BLE001
            pass
        raise MdmApiError(res.status_code, message or f"MDM request failed ({res.status_code})")

    data: Any
    if res.headers.get("content-type", "").startswith("application/json"):
        data = res.json()
    else:
        data = res.text
    return data, res.headers
