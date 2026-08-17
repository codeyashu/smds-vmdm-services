"""Tests for form snapshot comparison during adjudication."""

from app.documents.validation.form_compare import compare_form_snapshot
from app.documents.validation.types import FieldOption


def _option(path: str, label: str, value: str, source: str) -> FieldOption:
    return FieldOption(
        optionKey=f"IN_GST_CERTIFICATE:{path}",
        path=path,
        label=label,
        sourceLabel=source,
        incomingValue=value,
        incomingDisplay=value,
        confidence=0.95,
        preSelected=True,
    )


def test_form_mismatch_warns_when_values_differ():
    options = [_option("tradingName", "Trading name", "ACME NEW", "GST certificate")]
    checks = compare_form_snapshot(options, {"tradingName": "ACME OLD"})
    assert len(checks) == 1
    assert "form is ACME OLD" in checks[0].message


def test_form_match_skips_warn():
    options = [_option("tradingName", "Trading name", "ACME LTD", "GST certificate")]
    checks = compare_form_snapshot(options, {"tradingName": "ACME LTD"})
    assert checks == []
