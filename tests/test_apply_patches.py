"""Tests for document apply-patches."""

from __future__ import annotations

import pytest

from app.documents.apply_patches import apply_document_options


@pytest.mark.asyncio
async def test_apply_simple_scalar():
    selected = [
        {
            "path": "tradingName",
            "label": "Trading name",
            "incomingValue": "ACME",
            "sourceDocType": "IN_GST_CERTIFICATE",
            "sourceDocTypeLabel": "IN_GST_CERTIFICATE",
        }
    ]
    result = await apply_document_options({}, selected, country_code="IN")
    assert result["formState"]["tradingName"] == "ACME"
    assert len(result["applied"]) == 1


@pytest.mark.asyncio
async def test_remap_edit_bank_accounts():
    selected = [
        {
            "path": "vendorBankAccounts.0.ifsc",
            "label": "IFSC",
            "incomingValue": "HDFC0001234",
            "sourceDocType": "IN_CANCELLED_CHEQUE",
            "sourceDocTypeLabel": "IN_CANCELLED_CHEQUE",
        }
    ]
    result = await apply_document_options(
        {},
        selected,
        country_code="IN",
        remap_path="edit_bank_accounts",
    )
    assert result["applied"][0]["path"].startswith("bankAccounts.")
