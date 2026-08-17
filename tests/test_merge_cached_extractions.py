"""Tests for lazy cache merge into adjudication bundles."""

from __future__ import annotations

from app.documents.validation.merge_cached_extractions import merge_cached_extractions


def test_merge_cached_skips_when_doc_type_already_uploaded():
    live = [
        {
            "documentId": "new_gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [{"path": "tradingName", "value": "ACME", "label": "Trading name", "confidence": 0.9}],
        }
    ]
    existing = [
        {
            "filename": "old_gst.pdf",
            "classifiedDocType": "IN_GST_CERTIFICATE",
            "extractionCache": {
                "extractedAt": "2026-01-01T00:00:00Z",
                "docType": "IN_GST_CERTIFICATE",
                "patchesSummary": {"tradingName": "OLD ACME"},
            },
        }
    ]
    merged, notes = merge_cached_extractions(live, existing)
    assert len(merged) == 1
    assert notes == []


def test_merge_cached_includes_other_doc_type_from_cache():
    live = [
        {
            "documentId": "new_gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [],
        }
    ]
    existing = [
        {
            "filename": "pan.pdf",
            "classifiedDocType": "IN_PAN_CARD",
            "extractionCache": {
                "extractedAt": "2026-01-01T00:00:00Z",
                "docType": "IN_PAN_CARD",
                "patchesSummary": {
                    "taxInformation.taxIdentificationNumbers.2.taxIdentificationNumber": "ABCDE1234F",
                },
                "addressCandidates": [
                    {
                        "candidateKey": "IN_PAN_CARD:operational",
                        "addressRole": "operational",
                        "label": "PAN address",
                        "fullAddressText": "1 Main St",
                        "fields": {},
                        "sourceDocType": "IN_PAN_CARD",
                        "confidence": 0.9,
                    }
                ],
            },
        }
    ]
    merged, notes = merge_cached_extractions(live, existing)
    assert len(merged) == 2
    cached = next(row for row in merged if str(row.get("documentId", "")).startswith("cached:"))
    assert cached["docType"] == "IN_PAN_CARD"
    assert len(cached.get("patches") or []) == 1
    assert len(cached.get("addressCandidates") or []) == 1
    assert notes
