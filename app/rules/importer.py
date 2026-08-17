"""Import a v1 ``CountryValidationRuleResponse`` (MDM's ``getValidationRules`` payload) into
a v2 ``Ruleset``.

This is the phase-1 acceptance test's input half: ``import(mdm_response)`` followed by
``compile_ruleset(...).as_v1_response()`` (``app/rules/compat.py``) must reproduce
``mdm_response`` exactly, because the v2 model is v1's shape plus an additive ``x``
namespace that the compat projection strips back off. See
``tests/test_rules_roundtrip.py``.

MDM ships duplicate rows for the same ``fieldName`` (gap 15 — e.g. India's
``taxDeclarationRegimeCode`` appears twice, ``isApplicable: false`` then ``true``) with no
way to tell them apart. The importer's stable-slug generation turns that into two
addressable ``ruleId``s instead of a silent collapse — which is itself new information: a
country's duplicate-row count becomes visible and diagnosable rather than being an implicit
"last one wins" that only the array order decided.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone

from app.rules.models import Ruleset, RulesetSelector, ValidationRule, RuleExtension


def _slugify(text: str | None) -> str:
    if not text:
        return "field"
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s or "field"


def _rule_id_base(iso2_country_code: str, rule: ValidationRule) -> str:
    parts = [iso2_country_code.lower(), _slugify(rule.field_group_label), _slugify(rule.field_name)]
    if rule.scope_key:
        parts.append(_slugify(rule.scope_key))
    return ".".join(parts)


def _content_hash(rule: ValidationRule) -> str:
    body = rule.model_dump(by_alias=True, exclude_none=True, exclude={"x"})
    canonical = json.dumps(body, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def import_from_mdm_response(
    mdm_response: dict, *, imported_at: datetime | None = None
) -> Ruleset:
    """``mdm_response`` matches ``CountryValidationRuleResponse``: ``{iso2CountryCode,
    vendorStatusReason?, rules: [...]}``. Every rule is stamped ``source: mdm-import``,
    ``status: active`` (an import ships live, matching the fact that MDM already serves it
    live today — the ledger and Gate A checks are what determine whether it's *safe* to
    flip a country's source, not whether the imported data itself is draft), and a
    deterministic ``ruleId``.
    """
    cc = mdm_response["iso2CountryCode"]
    stamp = imported_at or datetime.now(timezone.utc)

    seen: Counter[str] = Counter()
    imported_rules: list[ValidationRule] = []

    for raw_rule in mdm_response.get("rules", []):
        rule = ValidationRule.model_validate(raw_rule)
        base_id = _rule_id_base(cc, rule)
        seen[base_id] += 1
        rule_id = base_id if seen[base_id] == 1 else f"{base_id}-{seen[base_id]}"

        rule.x = RuleExtension(
            rule_id=rule_id,
            version=1,
            status="active",
            source="mdm-import",
            created_at=stamp,
            updated_at=stamp,
            scope="$",
            phases=["create", "save", "submit"],
            severity="error",
        )
        rule.x.content_hash = _content_hash(rule)
        imported_rules.append(rule)

    return Ruleset(
        ruleset_id=f"country/{cc}",
        revision=1,
        layer="country",
        selector=RulesetSelector(
            iso2_country_code=[cc],
            vendor_status_reason=mdm_response.get("vendorStatusReason"),
        ),
        rules=imported_rules,
    )
