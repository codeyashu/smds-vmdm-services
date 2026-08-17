"""Phase 1 acceptance test: import(MDM response) -> compile() must reproduce the MDM
response exactly (semantic equality; key ordering is irrelevant to dict `==`, list/array
order is preserved and does matter). This is the round-trip proof from the design plan's
phase 1: "Brazil's ruleset is a file, and the API we'd serve from it is byte-equivalent to
MDM's." It is the cheapest possible evidence that the v2 model is expressive enough to be
the ruleset API, and it is the test most likely to catch a modeling gap early.

Fixtures are the portal's own validation fixtures
(``src/features/validation/__fixtures__/*.json`` in smds-vmdmportal), copied into
``tests/fixtures/rules/`` — they are exactly ``CountryValidationRuleResponse`` payloads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules.compat import compile_ruleset
from app.rules.importer import import_from_mdm_response

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "rules"

ALL_FIXTURES = sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_round_trip_reproduces_mdm_response(fixture_path: Path):
    mdm_response = json.loads(fixture_path.read_text(encoding="utf-8"))

    ruleset = import_from_mdm_response(mdm_response)
    result = compile_ruleset(
        ruleset.rules,
        iso2_country_code=mdm_response["iso2CountryCode"],
        vendor_status_reason=mdm_response.get("vendorStatusReason"),
    )

    assert result.excluded_inactive_count == 0, "a pure import must not exclude any rule"
    assert result.ledger == [], (
        "a pure MDM import must have an EMPTY lossiness ledger — every v1 rule is, by "
        "construction, expressible in v1's own shape. A non-empty ledger here means the "
        "importer introduced something the projection can't strip cleanly, which is an "
        "importer bug, not a genuine capability gap."
    )

    compiled = result.as_v1_response()
    assert compiled == mdm_response, (
        "compile(import(x)) must equal x. Diff the two payloads to find which rule or "
        "condition field the importer/compat pair failed to round-trip."
    )


def test_duplicate_field_rows_get_distinct_rule_ids():
    """The India duplicate-row problem (gap 15): MDM ships the same fieldName twice with
    different isApplicable. The importer must not collapse them — each gets its own
    ruleId, which is the precondition for ever diagnosing or resolving the duplication
    (phase 2's conflict detection, class C6)."""
    fixture = json.loads((FIXTURES_DIR / "in-prospect-vendor.json").read_text(encoding="utf-8"))
    ruleset = import_from_mdm_response(fixture)

    ids = [r.x.rule_id for r in ruleset.rules]
    assert len(ids) == len(set(ids)), f"importer produced duplicate ruleIds: {ids}"
