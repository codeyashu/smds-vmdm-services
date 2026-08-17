"""v2 rule model.

Governing principle (see the design plan): v1's field names, the ``dependencies[]``
container, the ``ruleType`` vocabulary, and the condition object are kept verbatim as the
canonical core. Everything new is an *additive* sibling key, namespaced under ``x`` on the
rule and as optional extra fields on the condition. A v1 rule (``CountryValidationRuleResponse``
as served by MDM's ``getValidationRules``, mirrored in the portal at
``src/lib/mdm/vendor-search.ts:449-481``) is a valid v2 rule with zero translation.

This is what makes the compat projection (``app/rules/compat.py``) "drop the ``x`` key and
any condition field outside v1's shape" rather than a semantic downgrade — and what makes the
dropped keys mechanically enumerable as the lossiness ledger instead of hand-curated.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# v1 core — unchanged names, unchanged semantics
# ---------------------------------------------------------------------------

#: v1's six operators. Unknown operator is a load-time error in v2 (never a silent
#: runtime ``false``, which was v1's failure mode — see gap 9 in the design plan).
V1_OPERATORS = ("exists", "notExists", "equals", "notEquals", "in", "notIn")

#: v1's four dependency types.
V1_RULE_TYPES = ("atLeastOne", "allOrNone", "mutuallyExclusive", "conditional")

#: v1's four action types, valid inside ``condition.action.actionType``.
V1_ACTION_TYPES = ("makeRequired", "makeOptional", "makeApplicable", "makeRequiredOneOf")


class RuleAction(BaseModel):
    """``ValidationRuleCondition.action`` — unchanged from v1."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    target_fields: list[str] | None = Field(default=None, alias="targetFields")
    action_type: str | None = Field(default=None, alias="actionType")

    @field_validator("action_type")
    @classmethod
    def _known_action_type(cls, v: str | None) -> str | None:
        if v is not None and v not in V1_ACTION_TYPES:
            raise ValueError(f"unknown actionType {v!r}; expected one of {V1_ACTION_TYPES}")
        return v


class RuleCondition(BaseModel):
    """``ValidationRuleCondition`` — v1 core plus optional v2 addressing extensions.

    ``path``/``targetPaths`` are VPath overrides (see ``app/rules/vpath.py``). When present
    they take precedence over ``fieldName``/``action.targetFields`` at evaluation time, but
    ``fieldName`` stays populated so the compat projection always has a v1-shaped fallback.
    The importer emits ``path``/``targetPaths`` only where the portal's ``resolveRulePath``
    special-casing was doing real work (bank/tax/telecom/BU/withholding) — gap 1 is fixed
    where it bites, not rewritten everywhere.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field_name: str = Field(alias="fieldName")
    operator: str
    values: list[str] | None = None
    action: RuleAction | None = None

    # v2 extensions — optional, additive
    path: str | None = None
    target_paths: list[str] | None = Field(default=None, alias="targetPaths")

    @field_validator("operator")
    @classmethod
    def _known_operator(cls, v: str) -> str:
        if v not in V1_OPERATORS and v not in V2_EXTRA_OPERATORS:
            raise ValueError(f"unknown operator {v!r}")
        return v


class RuleDependency(BaseModel):
    """``ValidationRuleDependency`` — unchanged shape."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rule_type: str = Field(alias="ruleType")
    conditions: list[RuleCondition] | None = None
    applicable_fields: list[str] | None = Field(default=None, alias="applicableFields")
    error_message: str | None = Field(default=None, alias="errorMessage")

    @field_validator("rule_type")
    @classmethod
    def _known_rule_type(cls, v: str) -> str:
        if v not in V1_RULE_TYPES:
            raise ValueError(f"unknown ruleType {v!r}; expected one of {V1_RULE_TYPES}")
        return v


# ---------------------------------------------------------------------------
# v2 extensions
# ---------------------------------------------------------------------------

#: Operators additive to v1's six. Kept in models.py (not predicate.py) because
#: ``RuleCondition.operator`` validates against the union — the condition object itself
#: is the closed-operator predicate; there is no separate expression-language layer.
#: Names follow JsonLogic's vocabulary where one exists, per the design plan's library
#: evaluation (CEL's first-party Python binding exposes no walkable AST for conflict
#: analysis; JsonLogic's maintained Python options are untyped or pre-1.0 — borrow the
#: names, not the dependency).
#:
#: Deliberately EXCLUDED for phase 1: ``any``/``all``/``none`` quantifiers and the
#: ``count*`` cardinality operators. Both need a *nested* sub-predicate, which the flat
#: v1 condition object (a single fieldName/path + operator + values) has no shape for.
#: Adding one is a real schema decision — bound up with how the conflict analyzer treats
#: quantifiers as opaque atoms (design plan §Conflict resolution, step 3) — and is
#: deferred to the phase that adds conflict detection, rather than half-implemented here.
V2_EXTRA_OPERATORS = (
    "eqIgnoreCase",
    "gt", "gte", "lt", "lte",
    "isBlank", "isNotBlank",
    "startsWith", "endsWith", "contains", "matches",
    "lengthEq", "lengthGte", "lengthLte",
    "dateBefore", "dateAfter", "dateWithinDays",
)

RuleSource = Literal["mdm-import", "authored", "llm"]
RuleStatus = Literal["draft", "active", "deprecated"]
RulePhase = Literal["create", "save", "submit", "approve", "revalidate", "import"]
RuleSeverity = Literal["error", "warning", "info"]

#: Effect kinds that CANNOT survive the compat projection — anything here is additive
#: capability beyond v1's four ``actionType`` values and always lands in the lossiness
#: ledger. Split deliberately from the projectable v1 actions: a country authored entirely
#: with v1-expressible effects has an empty ledger and can flip to `v2` on Gate A alone.
EffectKind = Literal[
    "setRequired", "setApplicable", "setVisible", "setReadOnly",  # inverses v1 lacks (gap 8)
    "setRegex", "applyValidator", "groupConstraint",
    "setControlType", "setReference", "setLabel", "setHint", "setOrigin", "setSection",
]

GroupConstraintKind = Literal[
    "atLeastOne", "allOrNone", "mutuallyExclusive", "requiredOneOf", "exactlyOne"
]


class RuleEffect(BaseModel):
    """A single ``x.effects[]`` entry. Discriminated informally on ``kind`` (pydantic
    doesn't need a formal discriminated union here since every field beyond ``kind`` is
    optional and effect-specific fields simply go unused for other kinds — keeping this a
    single flat model, rather than a tagged union, is what keeps YAML authoring readable).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: EffectKind
    value: bool | str | None = None

    # applyValidator
    validator: str | None = None
    args: dict | None = None
    applies_to: list[str] | None = Field(default=None, alias="appliesTo")

    # groupConstraint
    group_id: str | None = Field(default=None, alias="groupId")
    constraint: GroupConstraintKind | None = None
    members: list[str] | None = None
    message: str | None = None

    # setReference
    dataset_path: str | None = Field(default=None, alias="datasetPath")
    depends_on: list[str] | None = Field(default=None, alias="dependsOn")
    static_options: list[str] | None = Field(default=None, alias="staticOptions")
    derive_related_fields: list[dict] | None = Field(default=None, alias="deriveRelatedFields")

    # setLabel / setHint
    locale: str | None = None


class RuleExtension(BaseModel):
    """The ``x`` namespace — everything that is not v1. Optional in its entirety; a
    freshly MDM-imported rule with no local override carries only the identity/provenance
    fields the importer must always stamp (ruleId, version, status, source).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rule_id: str = Field(alias="ruleId")
    version: int = 1
    content_hash: str | None = Field(default=None, alias="contentHash")
    status: RuleStatus = "draft"
    effective_from: date | None = Field(default=None, alias="effectiveFrom")
    effective_to: date | None = Field(default=None, alias="effectiveTo")
    author: str | None = None
    source: RuleSource = "authored"
    source_ref: str | None = Field(default=None, alias="sourceRef")
    change_reason: str | None = Field(default=None, alias="changeReason")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    scope: str = "$"
    targets: list[str] = Field(default_factory=list)

    effects: list[RuleEffect] = Field(default_factory=list)

    phases: list[RulePhase] = Field(default_factory=lambda: ["create", "save", "submit"])
    severity: RuleSeverity = "error"
    severity_by_phase: dict[str, RuleSeverity] = Field(default_factory=dict, alias="severityByPhase")

    message_code: str | None = Field(default=None, alias="messageCode")
    explain_template: str | None = Field(default=None, alias="explainTemplate")

    priority: int = 100
    overrides: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Escape hatch — quarantined, never resolved by the conflict analyzer beyond POSSIBLE.
    cel_expression: str | None = Field(default=None, alias="celExpression")

    # Grounding provenance for LLM-drafted rules (§D of the design plan).
    grounding_confirmations: list[dict] = Field(default_factory=list, alias="groundingConfirmations")
    activated_by: str | None = Field(default=None, alias="activatedBy")
    activated_at: datetime | None = Field(default=None, alias="activatedAt")


class ValidationRule(BaseModel):
    """v1's ``ValidationRule`` (``vendor-search.ts:463-481``), extended with the optional
    ``x`` namespace. This is the unit stored in ``config/rules/**`` and the unit the
    importer emits.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field_name: str = Field(alias="fieldName")
    display_label: str | None = Field(default=None, alias="displayLabel")
    field_group_label: str | None = Field(default=None, alias="fieldGroupLabel")
    scope_key: str | None = Field(default=None, alias="scopeKey")
    related_fields: list[str] | None = Field(default=None, alias="relatedFields")
    is_required: bool | None = Field(default=None, alias="isRequired")
    is_applicable: bool | None = Field(default=None, alias="isApplicable")
    is_document_verification_required: bool | None = Field(
        default=None, alias="isDocumentVerificationRequired"
    )
    regex_pattern: str | None = Field(default=None, alias="regexPattern")
    error_message: str | None = Field(default=None, alias="errorMessage")
    dependencies: list[RuleDependency] | None = None

    x: RuleExtension | None = None


class RulesetSelector(BaseModel):
    """When a ruleset layer applies at all — ``null`` means "any"."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    iso2_country_code: list[str] | None = Field(default=None, alias="iso2CountryCode")
    entity_type: str | None = Field(default=None, alias="entityType")
    vendor_status_reason: str | None = Field(default=None, alias="vendorStatusReason")


class RulesetPatch(BaseModel):
    """A country-layer edit to an inherited rule's *metadata only*. Predicate and targets
    are deliberately unpatchable — see the design plan's §Country scaling: patching the
    predicate makes the inherited ruleId a lie and makes conflict analysis reason about a
    body that appears nowhere in one file.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rule_id: str = Field(alias="ruleId")
    set: dict = Field(default_factory=dict)
    reason: str | None = None


class RulesetDisable(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rule_id: str = Field(alias="ruleId")
    reason: str | None = None


class Ruleset(BaseModel):
    """A single ``config/rules/**/*.yaml`` file."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ruleset_id: str = Field(alias="rulesetId")
    revision: int = 1
    extends: str | None = None
    layer: Literal["global", "country", "entity-type", "country-entity-type"] = "global"
    selector: RulesetSelector = Field(default_factory=RulesetSelector)

    disable: list[RulesetDisable] = Field(default_factory=list)
    patch: list[RulesetPatch] = Field(default_factory=list)
    rules: list[ValidationRule] = Field(default_factory=list)
