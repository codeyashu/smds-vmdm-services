"""Unit tests for enrichment stage gate."""

from __future__ import annotations

from app.onboard.stage_gate import STAGE_RESOLVED_THRESHOLD, decide_stage, gated_step_id


def _resolved(stage: str, confidence: float = 0.9) -> dict:
    return {stage: {'stage': stage, 'confidence': confidence, 'resolvedAt': '2026-01-01T00:00:00Z'}}


def test_address_enrich_already_resolved_skips():
    decision = decide_stage(
        'address_enrich',
        {'postalAddresses': [{'streetName': 'Main St', 'cityName': 'Mumbai'}]},
        _resolved('address_enrich'),
    )
    assert decision == {'run': False, 'reason': 'already_resolved'}
    assert gated_step_id('address_enrich', 'already_resolved') == 'address_enrich_already_resolved'


def test_address_enrich_below_threshold_runs():
    decision = decide_stage(
        'address_enrich',
        {'postalAddresses': [{'streetName': 'Main St', 'cityName': 'Mumbai'}]},
        _resolved('address_enrich', confidence=0.5),
    )
    assert decision == {'run': True}


def test_address_enrich_input_missing_skips():
    decision = decide_stage('address_enrich', {'postalAddresses': [{}]}, None)
    assert decision == {'run': False, 'reason': 'input_missing'}


def test_address_enrich_fresh_run_with_input():
    decision = decide_stage(
        'address_enrich',
        {'postalAddresses': [{'streetName': 'Main St', 'cityName': 'Mumbai'}]},
        None,
    )
    assert decision == {'run': True}


def test_registry_already_resolved_skips():
    decision = decide_stage(
        'registry',
        {'tradingName': 'Acme Pvt Ltd'},
        _resolved('registry'),
    )
    assert decision == {'run': False, 'reason': 'already_resolved'}
    assert gated_step_id('registry', 'already_resolved') == 'registry_already_resolved'


def test_registry_below_threshold_runs():
    decision = decide_stage(
        'registry',
        {'tradingName': 'Acme Pvt Ltd'},
        _resolved('registry', confidence=STAGE_RESOLVED_THRESHOLD - 0.01),
    )
    assert decision == {'run': True}


def test_registry_input_missing_skips():
    decision = decide_stage('registry', {'tradingName': ''}, None)
    assert decision == {'run': False, 'reason': 'input_missing'}


def test_registry_fresh_run_with_input():
    decision = decide_stage('registry', {'tradingName': 'Acme Pvt Ltd'}, None)
    assert decision == {'run': True}


def test_duplicate_precheck_already_resolved_skips():
    decision = decide_stage(
        'duplicate_precheck',
        {'tradingName': 'Acme'},
        _resolved('duplicate_precheck', confidence=1.0),
    )
    assert decision == {'run': False, 'reason': 'already_resolved'}
    assert gated_step_id('duplicate_precheck', 'already_resolved') == 'duplicate_precheck_already_resolved'


def test_duplicate_precheck_below_threshold_runs():
    decision = decide_stage(
        'duplicate_precheck',
        {'tradingName': 'Acme'},
        _resolved('duplicate_precheck', confidence=0.5),
    )
    assert decision == {'run': True}


def test_duplicate_precheck_fresh_run_always_runs():
    decision = decide_stage('duplicate_precheck', {}, None)
    assert decision == {'run': True}
