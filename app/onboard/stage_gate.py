"""Rule-based stage gate — skip optional enrichment stages when already resolved."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.mdm.address_mapping import build_postal_address_search_line

OptionalStageId = Literal['address_enrich', 'registry', 'duplicate_precheck']
StageSkipReason = Literal['already_resolved', 'input_missing']

STAGE_RESOLVED_THRESHOLD = 0.85


class StageGateDecision(TypedDict, total=False):
    run: bool
    reason: StageSkipReason


def _read_bill_to_address(form_state: dict[str, Any]) -> dict[str, Any]:
    addresses = form_state.get('postalAddresses')
    if isinstance(addresses, list) and addresses and isinstance(addresses[0], dict):
        return addresses[0]
    return {}


def _stage_input_missing(stage_id: OptionalStageId, working_state: dict[str, Any]) -> bool:
    if stage_id == 'address_enrich':
        address = _read_bill_to_address(working_state)
        return not build_postal_address_search_line(address).strip()
    if stage_id == 'registry':
        return not str(working_state.get('tradingName') or '').strip()
    return False


def decide_stage(
    stage_id: OptionalStageId,
    working_state: dict[str, Any],
    resolved_stages: dict[str, Any] | None = None,
    confidence_threshold: float = STAGE_RESOLVED_THRESHOLD,
) -> StageGateDecision:
    resolved = resolved_stages or {}
    prior = resolved.get(stage_id)
    if isinstance(prior, dict):
        try:
            confidence = float(prior.get('confidence', 0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence >= confidence_threshold:
            return {'run': False, 'reason': 'already_resolved'}

    if _stage_input_missing(stage_id, working_state):
        return {'run': False, 'reason': 'input_missing'}

    return {'run': True}


def gated_step_id(stage_id: OptionalStageId, reason: StageSkipReason) -> str:
    if reason == 'already_resolved':
        return f'{stage_id}_already_resolved'
    return f'{stage_id}_skipped'
