"""HTTP client for portal BFF routes used by the onboard orchestrator."""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx

DEFAULT_PORTAL_BFF_URL = "http://localhost:3000"


def portal_base_url() -> str:
    return (os.getenv("VMDM_PORTAL_BFF_URL") or os.getenv("PORTAL_BFF_URL") or DEFAULT_PORTAL_BFF_URL).rstrip("/")


async def post_json(path: str, body: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=portal_base_url(), timeout=timeout) as client:
        res = await client.post(
            path,
            json=body,
            headers={"accept": "application/json", "content-type": "application/json"},
        )
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else {"data": data}


async def get_json(path: str, params: dict[str, str] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=portal_base_url(), timeout=timeout) as client:
        res = await client.get(path, params=params, headers={"accept": "application/json"})
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else {"data": data}


async def post_multipart(path: str, files: list[tuple[str, bytes, str]], form: dict[str, str]) -> dict[str, Any]:
    multipart_files = [("files", (name, content, mime)) for name, content, mime in files]
    async with httpx.AsyncClient(base_url=portal_base_url(), timeout=120.0) as client:
        res = await client.post(path, files=multipart_files, data=form)
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else {"data": data}


def decode_upload_files(files: list[dict[str, Any]]) -> list[tuple[str, bytes, str]]:
    decoded: list[tuple[str, bytes, str]] = []
    for entry in files:
        name = str(entry.get("name") or "upload")
        mime = str(entry.get("type") or "application/octet-stream")
        raw = entry.get("contentBase64")
        if not isinstance(raw, str):
            continue
        decoded.append((name, base64.b64decode(raw), mime))
    return decoded
