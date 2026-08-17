"""MCP in-process handler tests."""

from __future__ import annotations

import pytest

from app.mcp.handlers import (
    adjudicate_documents_handler,
    get_vendor_document_extractions_handler,
    reconcile_address_candidates_handler,
    resolve_field_conflicts_handler,
)


@pytest.mark.asyncio
async def test_reconcile_address_candidates_handler():
    candidates = [
        {
            "candidateKey": "IN_ADDRESS_PROOF:operational",
            "addressRole": "operational",
            "label": "Address proof",
            "fullAddressText": "D.NO.61B, Avinashi, 641652",
            "fields": {"cityName": "Avinashi", "postalCode": "641652"},
            "sourceDocType": "IN_ADDRESS_PROOF",
            "confidence": 0.98,
        }
    ]
    result = await reconcile_address_candidates_handler(
        {"addressCandidates": candidates, "formSnapshot": {"postalAddresses": [{"cityName": "Avinashi"}]}}
    )
    assert result["selectedCandidateKey"] == "IN_ADDRESS_PROOF:operational"


@pytest.mark.asyncio
async def test_get_vendor_document_extractions_from_cache():
    result = await get_vendor_document_extractions_handler(
        {
            "existingDocuments": [
                {
                    "filename": "gst.pdf",
                    "classifiedDocType": "IN_GST_CERTIFICATE",
                    "extractionCache": {
                        "extractedAt": "2026-01-01T00:00:00Z",
                        "docType": "IN_GST_CERTIFICATE",
                        "patchesSummary": {"tradingName": "ACME"},
                    },
                }
            ]
        }
    )
    assert result["count"] == 1
    assert result["extractions"][0]["docType"] == "IN_GST_CERTIFICATE"


@pytest.mark.asyncio
async def test_adjudicate_documents_handler_merges_cache():
    result = await adjudicate_documents_handler(
        {
            "countryCode": "IN",
            "extractions": [
                {
                    "documentId": "gst",
                    "docType": "IN_GST_CERTIFICATE",
                    "patches": [
                        {
                            "path": "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                            "value": "27AABCA1234F1Z5",
                            "label": "GSTIN",
                            "confidence": 0.95,
                            "preSelected": True,
                            "regexOk": True,
                        }
                    ],
                    "warnings": [],
                }
            ],
            "existingDocuments": [
                {
                    "filename": "pan.pdf",
                    "classifiedDocType": "IN_PAN_CARD",
                    "extractionCache": {
                        "extractedAt": "2026-01-01T00:00:00Z",
                        "docType": "IN_PAN_CARD",
                        "patchesSummary": {
                            "taxInformation.taxIdentificationNumbers.2.taxIdentificationNumber": "ABCDE1234F",
                        },
                    },
                }
            ],
        }
    )
    assert result["countryCode"] == "IN"
    assert any("cached extraction" in w.lower() for w in result.get("warnings") or [])
    option_keys = {row["optionKey"] for row in result.get("options") or []}
    assert any(key.startswith("IN_PAN_CARD:") for key in option_keys)


@pytest.mark.asyncio
async def test_resolve_field_conflicts_from_adjudication_payload():
    adjudication = {
        "conflicts": [{"path": "tradingName", "optionKeys": ["a", "b"]}],
        "fieldVerdicts": [
            {
                "path": "tradingName",
                "action": "steward_required",
                "recommendedOptionKey": "a",
            }
        ],
        "options": [
            {"optionKey": "a", "path": "tradingName", "incomingValue": "A"},
            {"optionKey": "b", "path": "tradingName", "incomingValue": "B"},
        ],
    }
    result = await resolve_field_conflicts_handler({"adjudication": adjudication, "path": "tradingName"})
    assert result["verdict"]["action"] == "steward_required"
    assert len(result["candidates"]) == 2
