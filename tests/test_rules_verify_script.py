"""Prove ``scripts/verify_rules.py``'s checks actually catch problems, not just that clean
data passes silently. Each test hand-builds a ``Ruleset`` with one specific defect and
asserts the matching checker function reports it — this is the enforcement half of the
VPath profile (``$..`` etc.) and the validator/override integrity promised in the design
plan's §C.4 "Where detection runs"."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_rules as vr  # noqa: E402

from app.rules.models import (  # noqa: E402
    Ruleset,
    RulesetSelector,
    RuleCondition,
    RuleDependency,
    RuleEffect,
    RuleExtension,
    ValidationRule,
)


def _rule(field_name: str, **x_overrides) -> ValidationRule:
    x = RuleExtension(rule_id=f"test.{field_name}", status="active", **x_overrides)
    return ValidationRule(field_name=field_name, x=x)


def test_check_vpaths_rejects_recursive_descent():
    rule = _rule("a", scope="$..a")
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[rule])
    errors = vr._check_vpaths(ruleset)
    assert errors and "recursive descent" in errors[0]


def test_check_vpaths_accepts_a_clean_scope():
    rule = _rule("a", scope="$.bankAccounts[*]", targets=["@.iban"])
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[rule])
    assert vr._check_vpaths(ruleset) == []


def test_check_validators_rejects_unknown_name():
    rule = _rule("a", effects=[RuleEffect(kind="applyValidator", validator="not-a-real-validator")])
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[rule])
    errors = vr._check_validators(ruleset)
    assert errors and "unknown validator" in errors[0]


def test_check_validators_accepts_known_name():
    rule = _rule("a", effects=[RuleEffect(kind="applyValidator", validator="gstin")])
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[rule])
    assert vr._check_validators(ruleset) == []


def test_check_duplicate_rule_ids():
    a = ValidationRule(field_name="a", x=RuleExtension(rule_id="dup", status="active"))
    b = ValidationRule(field_name="b", x=RuleExtension(rule_id="dup", status="active"))
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[a, b])
    errors = vr._check_duplicate_rule_ids(ruleset)
    assert errors and "dup" in errors[0]


def test_check_overlay_shape_rejects_dangling_override():
    rule = _rule("a", overrides=["does.not.exist"])
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[rule])
    errors = vr._check_overlay_shape(ruleset)
    assert errors and "unknown ruleId" in errors[0]


def test_check_overlay_shape_accepts_override_within_same_ruleset():
    target = _rule("a")
    overriding = _rule("b", overrides=["test.a"])
    ruleset = Ruleset(
        ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[target, overriding]
    )
    assert vr._check_overlay_shape(ruleset) == []


def test_ledger_v2_only_operator_is_fatal():
    condition = RuleCondition(field_name="a", operator="gt", values=["5"])
    dependency = RuleDependency(rule_type="conditional", conditions=[condition])
    rule = ValidationRule(
        field_name="a",
        dependencies=[dependency],
        x=RuleExtension(rule_id="test.a", status="active"),
    )
    ruleset = Ruleset(ruleset_id="country/ZZ", selector=RulesetSelector(iso2_country_code=["ZZ"]), rules=[rule])
    fatal, info = vr._check_ledger(ruleset, "ZZ")
    assert fatal and "gt" in fatal[0]
    assert info == []
