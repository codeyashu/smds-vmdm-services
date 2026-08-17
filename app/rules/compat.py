"""The compat projection — v2's answer to ``getValidationRules``.

Compiles a layered v2 ruleset down to the flat wire shape the portal already understands
(``CountryValidationRuleResponse``, ``src/lib/mdm/vendor-search.ts:477``) so that
``rule-dependency-engine.ts`` and every one of its 60+ call sites work completely unchanged
— see the design plan's "Position: v2 *is* the ruleset API". Because the v2 rule model
extends v1's shape *in place* (``app/rules/models.py``) rather than replacing it, this
projection is mechanical: strip the ``x`` namespace and any condition field outside v1's
four, filter to rules that are active for the given phase — done. It is not a semantic
downgrade computed by a separate code path that could itself drift from the authored rule.

What that strip drops is exactly what cannot survive contact with the v1 evaluator, and it
is recorded per rule as a **lossiness ledger entry** rather than silently discarded. The
ledger is the measured, per-country justification for ever building a native v2 evaluator
(design plan's deliverable B) — not a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rules.models import V1_OPERATORS, ValidationRule


@dataclass
class LedgerEntry:
    rule_id: str | None
    field_name: str
    reason: str
    detail: str


@dataclass
class CompileResult:
    iso2_country_code: str
    vendor_status_reason: str | None
    rules: list[dict[str, Any]]
    ledger: list[LedgerEntry] = field(default_factory=list)
    excluded_inactive_count: int = 0

    def as_v1_response(self) -> dict[str, Any]:
        """Exactly ``CountryValidationRuleResponse`` — {iso2CountryCode, vendorStatusReason?, rules}."""
        out: dict[str, Any] = {"iso2CountryCode": self.iso2_country_code, "rules": self.rules}
        if self.vendor_status_reason is not None:
            out["vendorStatusReason"] = self.vendor_status_reason
        return out


def compile_ruleset(
    rules: list[ValidationRule],
    *,
    iso2_country_code: str,
    vendor_status_reason: str | None = None,
    phase: str | None = None,
) -> CompileResult:
    """Project ``rules`` to the v1 wire shape for the given phase.

    A rule with ``x.status != "active"`` or whose ``x.phases`` excludes ``phase`` is
    dropped entirely (not ledgered as lossy — this is correct behavior, mirroring
    ``evaluate.py``'s ``_rule_active_for_phase``, and is what retires the portal's
    client-side ``filterProspectCreateRules``/``filterProspectPostSubmitRules`` subset
    filters, gap 6). A rule with no ``x`` at all (a bare v1-shaped/imported rule) always
    participates, matching today's behavior where MDM ships no phase dimension.
    """
    compiled: list[dict[str, Any]] = []
    ledger: list[LedgerEntry] = []
    excluded = 0

    for rule in rules:
        if rule.x is not None:
            if rule.x.status != "active":
                excluded += 1
                continue
            if phase is not None and phase not in rule.x.phases:
                excluded += 1
                continue

        ledger.extend(_ledger_for_rule(rule))
        compiled.append(_strip_to_v1_shape(rule))

    return CompileResult(
        iso2_country_code=iso2_country_code,
        vendor_status_reason=vendor_status_reason,
        rules=compiled,
        ledger=ledger,
        excluded_inactive_count=excluded,
    )


def _strip_to_v1_shape(rule: ValidationRule) -> dict[str, Any]:
    dumped = rule.model_dump(by_alias=True, exclude_none=True, exclude={"x"})
    for dependency in dumped.get("dependencies") or []:
        for condition in dependency.get("conditions") or []:
            condition.pop("path", None)
            condition.pop("targetPaths", None)
    return dumped


def _ledger_for_rule(rule: ValidationRule) -> list[LedgerEntry]:
    entries: list[LedgerEntry] = []
    rule_id = rule.x.rule_id if rule.x else None

    if rule.x is not None:
        if rule.x.effects:
            kinds = ", ".join(sorted({e.kind for e in rule.x.effects}))
            entries.append(LedgerEntry(
                rule_id, rule.field_name, "no-inverse-effect",
                f"x.effects [{kinds}] have no v1 actionType equivalent and are dropped",
            ))
        if rule.x.cel_expression:
            entries.append(LedgerEntry(
                rule_id, rule.field_name, "cel-expression-not-projectable",
                "x.celExpression cannot be represented in v1's condition object",
            ))
        if rule.x.severity != "error" or rule.x.severity_by_phase:
            entries.append(LedgerEntry(
                rule_id, rule.field_name, "no-severity-field",
                f"severity={rule.x.severity!r} severityByPhase={rule.x.severity_by_phase!r} "
                "cannot be carried — v1's wire shape has no per-rule severity field",
            ))
        if "[?(" in rule.x.scope:
            entries.append(LedgerEntry(
                rule_id, rule.field_name, "row-filter-not-representable-in-v1",
                f"scope {rule.x.scope!r} selects specific rows; v1's scopeKey applies to "
                "every row of a section uniformly and cannot express the filter",
            ))

    for dependency in rule.dependencies or []:
        for condition in dependency.conditions or []:
            if condition.operator not in V1_OPERATORS:
                entries.append(LedgerEntry(
                    rule_id, rule.field_name, "v2-only-operator",
                    f"condition on {condition.field_name!r} uses operator "
                    f"{condition.operator!r}, which v1's evaluator does not recognize and "
                    "would silently treat as false (gap 9) — HIGH severity, must not ship "
                    "to a country still on the mdm/v2-shadow source",
                ))

    return entries
