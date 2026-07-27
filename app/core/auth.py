"""Optional bearer-token gate for smds-vmdm-services.

When ``DOCAI_SERVICE_BEARER_TOKEN`` is set, callers must present
``Authorization: Bearer <token>``. When unset, auth is disabled (dev only).
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_service_bearer(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().service_bearer_token
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")
