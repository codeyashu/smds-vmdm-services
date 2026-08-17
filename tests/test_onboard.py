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


@pytest.mark.asyncio
async def test_create_onboard_session_creates_a_durable_run_record():
    from app.onboard import run_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/onboard/sessions", json={"countryCode": "IN"})
        session_id = created.json()["sessionId"]

        res = await client.get(f"/v1/onboard/runs/{session_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["runId"] == session_id
    assert body["countryCode"] == "IN"
    assert body["status"] == "pending"
    assert run_store.get_run(session_id) is not None


@pytest.mark.asyncio
async def test_list_onboard_runs_returns_summaries_most_recent_first():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/onboard/sessions", json={"countryCode": "IN"})
        second = await client.post("/v1/onboard/sessions", json={"countryCode": "IN"})

        res = await client.get("/v1/onboard/runs")
    assert res.status_code == 200
    body = res.json()
    run_ids = [r["runId"] for r in body["runs"]]
    assert second.json()["sessionId"] in run_ids
    assert first.json()["sessionId"] in run_ids
    assert run_ids.index(second.json()["sessionId"]) < run_ids.index(first.json()["sessionId"])
    summary = body["runs"][0]
    assert "stageCount" in summary
    assert "stageResults" not in summary


@pytest.mark.asyncio
async def test_list_onboard_runs_caps_an_excessive_limit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/onboard/runs?limit=999999")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_get_onboard_run_404_when_unknown():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/onboard/runs/does-not-exist")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_run_session_records_stages_and_tool_calls_into_the_run_record():
    from app.onboard import run_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/onboard/sessions", json={"countryCode": "IN"})
        session_id = created.json()["sessionId"]
        await client.post(
            f"/v1/onboard/sessions/{session_id}/run",
            json={"countryCode": "IN", "formState": {"tradingName": "Acme"}, "files": []},
        )

    run = run_store.get_run(session_id)
    body = run_store.to_dict(run)
    assert body["status"] == "done"
    assert len(body["stageResults"]) > 0
    assert len(body["toolCallLog"]) > 0


def test_mcp_tool_catalog():
    tools = list_tools()
    names = {t["name"] for t in tools}
    assert "extract_documents" in names
    assert "adjudicate_documents" in names
    assert "reconcile_address_candidates" in names
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
