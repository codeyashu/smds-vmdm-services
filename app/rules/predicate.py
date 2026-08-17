"""Condition evaluation — v1's six operators, unchanged semantics, plus the additive v2 set.

Mirrors the portal's ``evaluateOperator`` (``rule-dependency-engine.ts:279-296``) closely
enough that a golden-fixture test can assert agreement. The one deliberate behavioral
change: v1's ``default: return false`` for an unrecognized operator is not reachable here —
``RuleCondition.operator`` is validated against the closed set at model-construction time
(``app/rules/models.py``), so an unknown operator is a load-time error, never a silent
runtime `false` (gap 9 in the design plan — a typo used to produce a *permissive* engine).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.rules.models import RuleCondition
from app.rules.vpath import resolve_vpath


def read_condition_value(condition: RuleCondition, document: dict, row: dict | None) -> Any:
    """Resolve the value a condition tests.

    If the condition carries a VPath ``path`` override, resolve it (against ``row`` when
    row-relative, else ``document``) and take the first match — a condition is expected to
    reference a single scalar, not a wildcard set.

    Otherwise, fall back to flat lookup: check ``row`` first (a condition's ``fieldName``
    almost always refers to a sibling field in the same row — e.g. "bankCountryCode" beside
    "iban"), then ``document``. This is deliberately *not* a port of the portal's
    ``resolveRulePath`` — binding a condition within its own scope by construction, rather
    than reconstructing a global path, is what fixes the cross-row contamination in gap 3.
    """
    if condition.path:
        matches = resolve_vpath(condition.path, document, row=row)
        return matches[0][1] if matches else None

    field = condition.field_name
    if row is not None and field in row:
        return row[field]
    if field in document:
        return document[field]
    return None


def _is_present(value: Any) -> bool:
    """v1's implicit "exists" semantics: not None, and not a blank string."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def _as_str_list(values: list[str] | None) -> list[str]:
    return values or []


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def evaluate_operator(operator: str, value: Any, values: list[str] | None) -> bool:
    """Evaluate one operator given the resolved subject ``value`` and the condition's
    literal ``values`` list. Pure function, no document access — makes this trivially
    unit-testable against the fixture corpus independent of path resolution.
    """
    literals = _as_str_list(values)

    # --- v1's six, unchanged semantics ---
    if operator == "exists":
        return _is_present(value)
    if operator == "notExists":
        return not _is_present(value)
    if operator == "equals":
        return _is_present(value) and str(value) == (literals[0] if literals else None)
    if operator == "notEquals":
        return not (_is_present(value) and str(value) == (literals[0] if literals else None))
    if operator == "in":
        return _is_present(value) and str(value) in literals
    if operator == "notIn":
        return not (_is_present(value) and str(value) in literals)

    # --- v2 additive ---
    if operator == "eqIgnoreCase":
        return _is_present(value) and literals and str(value).lower() == literals[0].lower()
    if operator in ("gt", "gte", "lt", "lte"):
        return _evaluate_ordering(operator, value, literals)
    if operator == "isBlank":
        return not _is_present(value)
    if operator == "isNotBlank":
        return _is_present(value)
    if operator == "startsWith":
        return _is_present(value) and bool(literals) and str(value).startswith(literals[0])
    if operator == "endsWith":
        return _is_present(value) and bool(literals) and str(value).endswith(literals[0])
    if operator == "contains":
        return _is_present(value) and bool(literals) and literals[0] in str(value)
    if operator == "matches":
        return _is_present(value) and bool(literals) and re.search(literals[0], str(value)) is not None
    if operator == "lengthEq":
        return literals and len(str(value or "")) == int(literals[0])
    if operator == "lengthGte":
        return literals and len(str(value or "")) >= int(literals[0])
    if operator == "lengthLte":
        return literals and len(str(value or "")) <= int(literals[0])
    if operator in ("dateBefore", "dateAfter", "dateWithinDays"):
        return _evaluate_date(operator, value, literals)

    # Unreachable in practice — RuleCondition.operator is validated at model-construction
    # time against the closed operator set (models.py). A RuntimeError here (rather than
    # v1's silent `false`) means a code path bypassed that validation, which is itself a bug
    # worth surfacing loudly rather than degrading to "field is never required".
    raise RuntimeError(f"unreachable: unvalidated operator {operator!r} reached the evaluator")


def _evaluate_ordering(operator: str, value: Any, literals: list[str]) -> bool:
    if not _is_present(value) or not literals:
        return False
    try:
        lhs, rhs = float(value), float(literals[0])
    except (TypeError, ValueError):
        lhs_d, rhs_d = _parse_date(value), _parse_date(literals[0])
        if lhs_d is None or rhs_d is None:
            return False
        lhs, rhs = lhs_d.toordinal(), rhs_d.toordinal()
    if operator == "gt":
        return lhs > rhs
    if operator == "gte":
        return lhs >= rhs
    if operator == "lt":
        return lhs < rhs
    return lhs <= rhs  # lte


def _evaluate_date(operator: str, value: Any, literals: list[str]) -> bool:
    subject = _parse_date(value)
    if subject is None:
        return False
    if operator == "dateWithinDays":
        if not literals:
            return False
        try:
            days = int(literals[0])
        except ValueError:
            return False
        return abs((date.today() - subject).days) <= days
    if not literals:
        return False
    reference = _parse_date(literals[0])
    if reference is None:
        return False
    return subject < reference if operator == "dateBefore" else subject > reference


def evaluate_condition(condition: RuleCondition, document: dict, row: dict | None) -> bool:
    value = read_condition_value(condition, document, row)
    return evaluate_operator(condition.operator, value, condition.values)
