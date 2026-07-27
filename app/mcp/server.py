"""MCP server entrypoint — tool discovery and gateway auth stub."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings
from app.mcp.tools import list_tools

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


def _verify_gateway_auth(authorization: str | None) -> None:
    token = get_settings().service_bearer_token
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    if authorization.removeprefix("Bearer ").strip() != token:
        raise HTTPException(status_code=403, detail="Invalid bearer token")


@router.get("/tools")
async def mcp_list_tools(authorization: str | None = Header(default=None)):
    _verify_gateway_auth(authorization)
    return {"tools": list_tools()}
