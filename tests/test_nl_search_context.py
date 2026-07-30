"""Tests for VMDM context injected into NL-search prompts."""

from __future__ import annotations

from app.nl_search.context import NlSearchParseContext, AlternativeCodeTypeItem, build_system_prompt


def test_build_system_prompt_includes_default_alternative_code_types():
    prompt = build_system_prompt()
    assert "SMDS_VNDR_CD" in prompt
    assert "S4_BP_VNDR_CD" in prompt
    assert "taxId is NEVER a vendor code" in prompt
    assert "zero-padded to 10 digits" in prompt


def test_build_system_prompt_uses_dynamic_alternative_code_types():
    context = NlSearchParseContext(
        alternativeCodeTypes=[
            AlternativeCodeTypeItem(code="CUSTOM_CD", name="Custom Vendor Code"),
        ],
        vendorStatuses=["ACTIVE", "INACTIVE"],
    )
    prompt = build_system_prompt(context)
    assert "CUSTOM_CD: Custom Vendor Code" in prompt
    assert "ACTIVE, INACTIVE" in prompt
