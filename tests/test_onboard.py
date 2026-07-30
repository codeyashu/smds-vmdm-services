"""Tests for onboard session API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.mcp.tools import list_tools


@pytest.mark.asyncio
async def test_onboard_ready_reports_v2():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/onboard/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["orchestratorVersion"] == 2


@pytest.mark.asyncio
async def test_run_session_accepts_files_and_form_state():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/onboard/sessions", json={"countryCode": "IN"})
        session_id = created.json()["sessionId"]
        res = await client.post(
            f"/v1/onboard/sessions/{session_id}/run",
            json={
                "countryCode": "IN",
                "formState": {"tradingName": "Acme"},
                "docAvailability": "full",
                "files": [
                    {
                        "name": "gst.png",
                        "type": "image/png",
                        "contentBase64": "aGVsbG8=",
                    }
                ],
            },
        )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    assert "RUN_STARTED" in res.text


@pytest.mark.asyncio
async def test_create_onboard_session():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/onboard/sessions", json={"countryCode": "IN"})
    assert res.status_code == 200
    body = res.json()
    assert body["countryCode"] == "IN"
    assert "sessionId" in body


def test_mcp_tool_catalog():
    tools = list_tools()
    names = {t["name"] for t in tools}
    assert "extract_documents" in names
    assert "create_prospect" in names
    assert "apply_vendor_patch" in names


@pytest.mark.asyncio
async def test_mcp_list_tools_requires_auth_when_configured():
    transport = ASGITransport(app=app)
    token = get_settings().service_bearer_token
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/mcp/tools")
        if token:
            assert res.status_code == 401
            res = await client.get("/v1/mcp/tools", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert "tools" in res.json()
