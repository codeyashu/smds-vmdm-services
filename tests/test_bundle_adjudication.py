"""Bundle adjudication tests."""

from __future__ import annotations

from app.documents.validation.adjudicate import adjudicate_bundle


def _patch(path: str, value, label: str, confidence: float = 0.95, **kwargs):
    return {
        "path": path,
        "value": value,
        "label": label,
        "confidence": confidence,
        "pre_selected": confidence >= 0.9,
        "regex_ok": True,
        **kwargs,
    }


def test_trading_name_conflict_across_pan_gst_and_coi():
    extractions = [
        {
            "documentId": "eph_pan",
            "docType": "IN_PAN_CARD",
            "patches": [_patch("tradingName", "ACME LOGISTICS", "Trading name", 0.92)],
            "warnings": [],
        },
        {
            "documentId": "eph_gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "27AABCA1234F1Z5",
                    "GSTIN",
                ),
                _patch("tradingName", "ACME LOGISTICS PVT LTD", "Trading name", 0.95),
            ],
            "warnings": [],
        },
        {
            "documentId": "eph_coi",
            "docType": "IN_CERTIFICATE_OF_INCORPORATION",
            "patches": [
                _patch("_unmapped.cin", "U12345MH2020PTC123456", "CIN", 0.9),
                _patch("tradingName", "ACME LOGISTICS PRIVATE LIMITED", "Trading name", 0.9),
            ],
            "warnings": [],
        },
    ]
    result = adjudicate_bundle("IN", extractions)
    assert any(c.path == "tradingName" for c in result.conflicts)
    assert len(result.cot_trace) >= 6
    assert any(s.kind == "observe" for s in result.cot_trace)
    assert any(s.kind == "compare" for s in result.cot_trace)


def test_trading_name_conflict_across_pan_and_gst():
    extractions = [
        {
            "documentId": "eph_pan",
            "docType": "IN_PAN_CARD",
            "patches": [_patch("tradingName", "ACME LOGISTICS", "Trading name", 0.92)],
            "warnings": [],
        },
        {
            "documentId": "eph_gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "27AABCA1234F1Z5",
                    "GSTIN",
                ),
                _patch("tradingName", "ACME LOGISTICS PVT LTD", "Trading name", 0.95),
            ],
            "warnings": [],
        },
    ]
    result = adjudicate_bundle("IN", extractions)
    assert any(c.path == "tradingName" for c in result.conflicts)
    assert any(v.action == "steward_required" for v in result.field_verdicts)


def test_gstin_singleton_block():
    extractions = [
        {
            "documentId": "a",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "27AABCA1234F1Z5",
                    "GSTIN",
                )
            ],
        },
        {
            "documentId": "b",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "29AAACI4403L3ZI",
                    "GSTIN",
                )
            ],
        },
    ]
    result = adjudicate_bundle("IN", extractions)
    assert any(c.id == "id_gstin_singleton" and c.status == "fail" for c in result.bundle_checks)


def test_cross_gstin_pan_mismatch():
    extractions = [
        {
            "documentId": "gst",
            "docType": "IN_GST_CERTIFICATE",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber",
                    "27AABCA1234F1Z5",
                    "GSTIN",
                )
            ],
        },
        {
            "documentId": "pan",
            "docType": "IN_PAN_CARD",
            "patches": [
                _patch(
                    "taxInformation.taxIdentificationNumbers.2.taxIdentificationNumber",
                    "ZZZZZ9999Z",
                    "TIN/PAN",
                )
            ],
        },
    ]
    result = adjudicate_bundle("IN", extractions)
    assert any(c.id == "cross_gstin_embeds_pan" and c.status == "fail" for c in result.bundle_checks)


def test_iban_validator():
    from app.documents.validation.identifiers import validate_iban

    ok = validate_iban("DE89370400440532013000")
    assert ok.ok
    bad = validate_iban("DE00BAD")
    assert not bad.ok


def test_no_playbook_country():
    result = adjudicate_bundle("XX", [])
    assert result.warnings
    assert result.playbook_version == 0
