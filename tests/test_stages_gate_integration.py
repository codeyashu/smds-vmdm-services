"""Integration tests — stage runners respect resolvedStages gate."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.onboard.stages import run_address_stage, run_duplicate_stage, run_registry_stage

_RESOLVED = {
    'address_enrich': {'stage': 'address_enrich', 'confidence': 0.9, 'resolvedAt': '2026-01-01T00:00:00Z'},
    'registry': {'stage': 'registry', 'confidence': 0.9, 'resolvedAt': '2026-01-01T00:00:00Z'},
    'duplicate_precheck': {
        'stage': 'duplicate_precheck',
        'confidence': 1.0,
        'resolvedAt': '2026-01-01T00:00:00Z',
    },
}


@pytest.mark.asyncio
@patch('app.onboard.stages.select_external_address', new_callable=AsyncMock)
@patch('app.onboard.stages.is_mdm_configured', return_value=True)
async def test_address_stage_skips_external_call_when_already_resolved(_mdm, mock_select):
    context = {
        'countryCode': 'IN',
        'formState': {'postalAddresses': [{'streetName': 'Main St', 'cityName': 'Mumbai'}]},
        'resolvedStages': _RESOLVED,
    }
    step, _ = await run_address_stage(context)
    assert step == 'address_enrich_already_resolved'
    mock_select.assert_not_called()


@pytest.mark.asyncio
@patch('app.onboard.stages.search_company_external', new_callable=AsyncMock)
@patch('app.onboard.stages.is_mdm_configured', return_value=True)
async def test_registry_stage_skips_external_call_when_already_resolved(_mdm, mock_search):
    context = {
        'countryCode': 'IN',
        'formState': {
            'tradingName': 'Acme Pvt Ltd',
            'postalAddresses': [{'cityName': 'Mumbai'}],
        },
        'resolvedStages': _RESOLVED,
    }
    step, _ = await run_registry_stage(context)
    assert step == 'registry_already_resolved'
    mock_search.assert_not_called()


@pytest.mark.asyncio
@patch('app.onboard.stages.search_duplicate_vendors', new_callable=AsyncMock)
@patch('app.onboard.stages.is_mdm_configured', return_value=True)
async def test_duplicate_stage_skips_external_call_when_already_resolved(_mdm, mock_dup):
    context = {
        'countryCode': 'IN',
        'formState': {'tradingName': 'Acme Pvt Ltd'},
        'resolvedStages': _RESOLVED,
    }
    step, _ = await run_duplicate_stage(context)
    assert step == 'duplicate_precheck_already_resolved'
    mock_dup.assert_not_called()
