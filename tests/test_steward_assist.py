"""Steward assist agent endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_explain_validation_stub():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/agents/explain-validation",
            json={
                "countryCode": "IN",
                "fieldPath": "taxInformation.taxIdentificationNumbers.0.taxIdentificationNumber",
                "validationMessage": "Invalid GSTIN format",
                "formState": {"tradingName": "Acme"},
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert "Invalid GSTIN format" in body["explanation"]
    assert body["wikiHint"]


@pytest.mark.asyncio
async def test_summarize_workflow_stub():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/agents/summarize-workflow",
            json={
                "vendorCode": "IN0000123",
                "workflowStatus": "PENDING",
                "changeSnapshot": [{"fieldPath": "tradingName", "value": "Acme"}],
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert "IN0000123" in body["summary"]
    assert body["riskFields"]
