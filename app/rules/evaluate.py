"""The v2 evaluator — produces a normalized effective-field projection from a ruleset and a
concrete vendor payload.

Scope note (read before extending): this module evaluates **document-root-scoped fields
directly**, and **row-scoped fields only where a rule carries an explicit ``x.scope``
VPath**. It deliberately does NOT port the portal's ~100-line ``resolveRulePath``
(``rule-dependency-engine.ts:142-240``) — the special-cased reconstruction of which bank
row, which tax row, which telecom row a bare ``fieldName`` "really" means. That
reconstruction is exactly gap 1 in the design plan, and its replacement is VPath addressing
attached *by the importer*, per rule, once — not re-derived by this evaluator at every call.
A freshly MDM-imported rule that targets a repeating section (bank accounts, tax slots,
postal addresses, telecom numbers) therefore evaluates only at the document root until the
importer (``app/rules/importer.py``) backfills its ``x.scope``/``path``/``targetPaths``.

This is the honest phase-1 slice: golden tests are scoped accordingly (see
``tests/test_rules_roundtrip.py``), not silently widened to claim parity the code doesn't
have yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rules.models import RuleCondition, RuleDependency, ValidationRule
from app.rules.predicate import evaluate_condition
from app.rules.vpath import resolve_scope_rows


@dataclass
class FieldProjection:
    """Comparable, normalized effective state for one concrete field instance.

    Mirrors the portal's ``EffectiveFieldState`` (``rule-dependency-engine.ts:15-35``)
    closely enough for a 1:1 diff, and is exactly ``ShadowFieldProjection`` from the design
    plan's §Shadow mode — the same struct serves the golden test today and the shadow diff
    once that phase lands.
    """

    path: str
    field_name: str
    is_required: bool = False
    is_applicable: bool = True
    is_visible: bool = True
    regex_pattern: str | None = None
    contributing_rule_ids: list[str] = field(default_factory=list)
    groups: dict[str, str] = field(default_factory=dict)  # kind -> group id


@dataclass
class EvaluationResult:
    fields: dict[str, FieldProjection]  # path -> projection
    group_errors: list[dict]


def _group_id(applicable_fields: list[str]) -> str:
    """v1's synthesized group identity — ``applicableFields.sort().join('|')``
    (``rule-dependency-engine.ts:352,364,376,410``). Kept identical for the compat
    projection and for golden-test agreement; a v2-native ``groupId`` is authored
    separately once overlays/inverse-effects land (design plan §B.5)."""
    return "|".join(sorted(applicable_fields))


def evaluate_ruleset(
    rules: list[ValidationRule], document: dict, *, phase: str | None = None
) -> EvaluationResult:
    """Evaluate every rule in ``rules`` against ``document``.

    Two passes, mirroring v1's structure:
    1. **Baseline** — one ``FieldProjection`` per rule at its own scope (document root, or
       row-expanded when ``x.scope`` is present), seeded from the rule's own
       ``isRequired``/``isApplicable``/``regexPattern``.
    2. **Dependencies** — each rule's ``dependencies[]`` can mutate *other* fields'
       projections (``conditional`` + condition ``action``) or attach group metadata
       (``atLeastOne``/``allOrNone``/``mutuallyExclusive``/``requiredOneOf``).

    A rule with ``x.status != "active"`` or whose ``x.phases`` excludes ``phase`` is
    skipped entirely — this is what retires the portal's client-side subset filters
    (``filterProspectCreateRules``/``filterProspectPostSubmitRules``, gap 6): phase
    filtering happens once, here, not per caller.
    """
    fields: dict[str, FieldProjection] = {}
    by_field_name: dict[str, list[FieldProjection]] = {}

    active_rules = [r for r in rules if _rule_active_for_phase(r, phase)]

    # --- pass 1: baseline projections, one per rule instance ---
    for rule in active_rules:
        for instance_path, row in _rule_scope_rows(rule, document):
            path = _join(instance_path, rule.field_name) if rule.x and rule.x.scope != "$" else rule.field_name
            proj = FieldProjection(
                path=path,
                field_name=rule.field_name,
                is_required=bool(rule.is_required),
                is_applicable=rule.is_applicable if rule.is_applicable is not None else True,
                is_visible=rule.is_applicable if rule.is_applicable is not None else True,
                regex_pattern=rule.regex_pattern,
                contributing_rule_ids=[rule.x.rule_id] if rule.x else [],
            )
            # Last duplicate row wins at the baseline layer, matching v1's documented
            # behavior for same-fieldName duplicate rows (gap 15) — group errors et al are
            # a phase-2+ concern (precedence model, §C of the design plan). Phase 1 does not
            # silently fix this; it reproduces it faithfully so the round-trip test is honest.
            fields[path] = proj
            by_field_name.setdefault(rule.field_name, []).append(proj)

    # --- pass 2: dependency actions ---
    group_errors: list[dict] = []
    for rule in active_rules:
        for dependency in rule.dependencies or []:
            _apply_dependency(dependency, rule, document, fields, by_field_name, group_errors)

    return EvaluationResult(fields=fields, group_errors=group_errors)


def _rule_active_for_phase(rule: ValidationRule, phase: str | None) -> bool:
    if rule.x is None:
        return True  # a plain v1-shaped rule participates in every phase, matching today
    if rule.x.status != "active":
        return False
    if phase is not None and phase not in rule.x.phases:
        return False
    return True


def _rule_scope_rows(rule: ValidationRule, document: dict) -> list[tuple[str, dict | None]]:
    if rule.x is None or rule.x.scope == "$":
        return [("", None)]
    return resolve_scope_rows(rule.x.scope, document)


def _join(prefix: str, suffix: str) -> str:
    return f"{prefix}.{suffix}" if prefix else suffix


def _apply_dependency(
    dependency: RuleDependency,
    owning_rule: ValidationRule,
    document: dict,
    fields: dict[str, FieldProjection],
    by_field_name: dict[str, list[FieldProjection]],
    group_errors: list[dict],
) -> None:
    if dependency.rule_type == "conditional":
        for condition in dependency.conditions or []:
            if not evaluate_condition(condition, document, None):
                continue
            _apply_condition_action(condition, owning_rule, fields, by_field_name)
        return

    # atLeastOne / allOrNone / mutuallyExclusive / requiredOneOf — group metadata only.
    # v1 does not turn these into a direct isRequired override; they are validated
    # separately (collectMinOneGroupErrors et al.) against submitted *values*, not against
    # the effective-field state. Phase 1 records the group id on each member's projection
    # (for the shadow diff's group-membership comparison, design plan §E.2) and stops there;
    # full group-constraint *validation* against a payload is a §Conflict-resolution-phase
    # concern (groupConstraint effect, C3 unsatisfiable-combination checks).
    members = dependency.applicable_fields or []
    if not members:
        return
    gid = _group_id(members)
    for member in members:
        for proj in by_field_name.get(member, []):
            proj.groups[dependency.rule_type] = gid


def _apply_condition_action(
    condition: RuleCondition,
    owning_rule: ValidationRule,
    fields: dict[str, FieldProjection],
    by_field_name: dict[str, list[FieldProjection]],
) -> None:
    action = condition.action
    if action is None or action.action_type is None:
        return
    targets = action.target_fields or []
    for target_field in targets:
        for proj in by_field_name.get(target_field, []):
            _apply_action_type(action.action_type, proj)
            if owning_rule.x and owning_rule.x.rule_id not in proj.contributing_rule_ids:
                proj.contributing_rule_ids.append(owning_rule.x.rule_id)


def _apply_action_type(action_type: str, proj: FieldProjection) -> None:
    # v1's four actionTypes (models.V1_ACTION_TYPES) — the additive-only set (gap 8). The
    # symmetric inverses (setRequired(false) etc.) are x.effects, applied in a later pass
    # once phase 2 lands; this function intentionally has no "else" branch that clears a
    # flag, matching v1's documented invariant "the effective set can only grow".
    if action_type == "makeRequired":
        proj.is_required = True
    elif action_type == "makeOptional":
        proj.is_required = False
    elif action_type == "makeApplicable":
        proj.is_applicable = True
        proj.is_visible = True
    elif action_type == "makeRequiredOneOf":
        proj.is_required = True
