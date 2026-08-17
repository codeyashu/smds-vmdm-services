"""MCP server entrypoint — tool discovery and gateway auth stub."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.mcp.tools import list_tools
from app.onboard.mcp_gateway import invoke_read_tool

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


class McpInvokeBody(BaseModel):
    tool: str
    args: dict[str, Any] = {}


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


@router.post("/invoke")
async def mcp_invoke(body: McpInvokeBody, authorization: str | None = Header(default=None)):
    _verify_gateway_auth(authorization)
    try:
        result = await invoke_read_tool(body.tool, body.args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
