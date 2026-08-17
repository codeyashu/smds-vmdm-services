"""``/v1/rules`` — the successor ruleset API.

Three endpoints for phase 1 (design plan §Phasing):

- ``GET /v1/rules/{country}/compiled`` — the compat projection. Same shape as MDM's
  ``getValidationRules``, plus a lossiness ledger. This is what
  ``src/app/api/validation/[country]/rules/route.ts`` in the portal will call once its
  source facade (phase 2) exists; nothing in the portal calls it yet.
- ``POST /v1/rules/simulate`` — payload + country (+ optional phase) in, a normalized
  field-state projection out. Used by golden tests today; becomes the shadow-diff and
  authoring-simulator primitive later.
- ``POST /v1/rules/{country}/import`` — pulls MDM's live ruleset for a country and writes
  it to ``config/rules/countries/{CC}/ruleset.yaml`` via the importer. An authoring-time
  operation, not a hot path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import require_service_bearer
from app.mdm.validation_rules import get_country_validation_rules, is_validation_rules_configured
from app.rules.compat import compile_ruleset
from app.rules.evaluate import evaluate_ruleset
from app.rules.importer import import_from_mdm_response
from app.rules.store import (
    country_ruleset_path,
    list_ruleset_countries,
    load_country_ruleset,
    save_country_ruleset,
)

router = APIRouter(prefix="/v1/rules", tags=["rules"], dependencies=[Depends(require_service_bearer)])


class LedgerEntryOut(BaseModel):
    rule_id: str | None = Field(default=None, alias="ruleId")
    field_name: str = Field(alias="fieldName")
    reason: str
    detail: str

    model_config = {"populate_by_name": True}


class CompiledRulesetResponse(BaseModel):
    iso2_country_code: str = Field(alias="iso2CountryCode")
    vendor_status_reason: str | None = Field(default=None, alias="vendorStatusReason")
    rules: list[dict[str, Any]]
    ledger: list[LedgerEntryOut]
    excluded_inactive_count: int = Field(alias="excludedInactiveCount")

    model_config = {"populate_by_name": True}


@router.get("/countries")
async def list_countries() -> dict[str, list[str]]:
    return {"countries": list_ruleset_countries()}


@router.get("/{country}/compiled", response_model=CompiledRulesetResponse)
async def get_compiled(
    country: str,
    entity_type: str | None = Query(default=None, alias="entityType"),
    vendor_status_reason: str | None = Query(default=None, alias="vendorStatusReason"),
    phase: str | None = Query(default=None),
) -> CompiledRulesetResponse:
    del entity_type  # not yet part of the selector match — phase 2 (entity-type overlays)
    ruleset = load_country_ruleset(country)
    if ruleset is None:
        raise HTTPException(status_code=404, detail=f"no ruleset imported for {country.upper()}")

    result = compile_ruleset(
        ruleset.rules,
        iso2_country_code=country.upper(),
        vendor_status_reason=vendor_status_reason or ruleset.selector.vendor_status_reason,
        phase=phase,
    )
    return CompiledRulesetResponse(
        iso2CountryCode=result.iso2_country_code,
        vendorStatusReason=result.vendor_status_reason,
        rules=result.rules,
        ledger=[
            LedgerEntryOut(ruleId=e.rule_id, fieldName=e.field_name, reason=e.reason, detail=e.detail)
            for e in result.ledger
        ],
        excludedInactiveCount=result.excluded_inactive_count,
    )


class SimulateRequest(BaseModel):
    country: str
    payload: dict[str, Any]
    phase: str | None = None

    model_config = {"populate_by_name": True}


class FieldProjectionOut(BaseModel):
    path: str
    field_name: str = Field(alias="fieldName")
    is_required: bool = Field(alias="isRequired")
    is_applicable: bool = Field(alias="isApplicable")
    is_visible: bool = Field(alias="isVisible")
    regex_pattern: str | None = Field(default=None, alias="regexPattern")
    contributing_rule_ids: list[str] = Field(alias="contributingRuleIds")
    groups: dict[str, str]

    model_config = {"populate_by_name": True}


@router.post("/simulate")
async def simulate(body: SimulateRequest) -> dict[str, list[FieldProjectionOut]]:
    ruleset = load_country_ruleset(body.country)
    if ruleset is None:
        raise HTTPException(status_code=404, detail=f"no ruleset imported for {body.country.upper()}")

    result = evaluate_ruleset(ruleset.rules, body.payload, phase=body.phase)
    fields = [
        FieldProjectionOut(
            path=p.path,
            fieldName=p.field_name,
            isRequired=p.is_required,
            isApplicable=p.is_applicable,
            isVisible=p.is_visible,
            regexPattern=p.regex_pattern,
            contributingRuleIds=p.contributing_rule_ids,
            groups=p.groups,
        )
        for p in result.fields.values()
    ]
    return {"fields": fields}


@router.post("/{country}/import")
async def import_country(country: str) -> dict[str, Any]:
    if not is_validation_rules_configured():
        raise HTTPException(status_code=503, detail="MDM_VENDOR_INGESTION_BASE_URL not configured")

    mdm_response = await get_country_validation_rules(country)
    ruleset = import_from_mdm_response(mdm_response)
    save_country_ruleset(ruleset)

    # Round-trip sanity check on the same request that just wrote the file — a failure
    # here means the importer produced something the compat projection can't cleanly
    # reproduce, which should never happen for a fresh mdm-import (see
    # tests/test_rules_roundtrip.py). Surface it as a 500 rather than writing silently.
    result = compile_ruleset(
        ruleset.rules,
        iso2_country_code=country.upper(),
        vendor_status_reason=ruleset.selector.vendor_status_reason,
    )
    if result.ledger:
        raise HTTPException(
            status_code=500,
            detail=f"import produced a non-empty ledger for a pure mdm-import: {result.ledger}",
        )

    return {
        "country": country.upper(),
        "ruleCount": len(ruleset.rules),
        "path": str(country_ruleset_path(country)),
    }
