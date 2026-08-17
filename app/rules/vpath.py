"""VPath — a restricted JSONPath profile.

Parsed with ``jsonpath-ng`` (battle-tested parser); the *restriction* is a small AST walk
we own and unit-test. Do not hand-roll a parser and do not accept full JSONPath.

Allowed: ``$`` (root), ``@`` (current row, only meaningful under a row ``scope``), child
access, ``[*]`` (wildcard index), ``[n]`` (literal index — allowed but discouraged, see
``verify_rules.py``), and an equality filter on a scalar row member against a literal
(``==``, ``!=``). Note on scope: ``jsonpath-ng``'s filter grammar (``.ext.filter``) natively
supports only ``==``/``!=``/``<``/``<=``/``>``/``>=``/``=~`` — there is no native ``in``.
Set-membership filters (`in`) are therefore expressed as multiple rules or, if truly needed,
as an `or` of `==` predicates at the rule-predicate layer (not inside the VPath filter) —
do not attempt to hand-extend the grammar. Ordering comparators (`<` etc.) are excluded from
the allowed set even though the library supports them, to keep the filter fragment to pure
set-membership, which is what the conflict analyzer's finite-domain reasoning assumes.

Forbidden, rejected at *load* time, never silently degraded at runtime:

- ``$..`` recursive descent. Permanently out of the profile (design plan invariant). It is
  unanalyzable — you cannot statically determine the target set without a schema walk,
  which defeats conflict detection — it silently matches fields added to the payload later,
  and it makes "which concrete indexed paths did this rule touch" non-deterministic across
  payload shapes. Every rule in this domain is better written as an explicit ``scope``.
- Script expressions ``[(...)]``, slices ``[1:3]``, unions ``[0,2]``, filters comparing two
  paths, nested filters, and filters on a non-scalar row member.

Array-row semantics: the wildcard/filter goes in ``scope``, never in ``targets``.
``scope="$"`` means targets are absolute VPaths evaluated once against the document root.
``scope="$.bankAccounts[*]"`` means the engine expands to concrete rows, binds ``@`` per
row, and evaluates predicate + targets independently per row — one authored rule yields N
results, never a collapse (fixing v1's TAXNOn/TEL-FAX-MOB collision, gap 2).

Result serialization is the load-bearing constraint that keeps the shadow diff (§E of the
design plan) a plain set operation: strip the leading ``$.``, replace ``[n]`` with ``.n``.
``$.postalAddresses[2].cityName`` becomes ``postalAddresses.2.cityName`` — exactly
``EffectiveFieldState.path`` (``rule-dependency-engine.ts:15-35``) and exactly what the
portal's ``diffNestedPaths`` (``src/lib/nested-payload.ts:152``) produces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jsonpath_ng.ext import parse as _jsonpath_ext_parse
from jsonpath_ng.ext.filter import Expression as _ExtExpression
from jsonpath_ng.ext.filter import Filter as _ExtFilter
from jsonpath_ng.jsonpath import Child, Fields, Index, Root, Slice, This, Where

_ALLOWED_FILTER_OPS = ("==", "!=", "=")


class VPathError(ValueError):
    """A VPath string is outside the allowed profile, or otherwise malformed."""


# --- forbidden-construct detection on the *source string*, before parsing -------------
# jsonpath-ng's base parser doesn't support filters (`[?(...)]`) or `@` at all — that
# requires the `.ext` parser, which also supports scripts/unions/slices we must reject.
# We therefore always parse with the extended grammar (to support `[?(...)]`) but then
# reject any construct outside the allowlist by walking the resulting AST.

_FORBIDDEN_SOURCE_PATTERNS = (
    (re.compile(r"\.\."), "recursive descent ('..') is not allowed in VPath"),
    (re.compile(r"\[\(.*?\)\]"), "script expressions ('[(...)]') are not allowed in VPath"),
    (re.compile(r"\[-?\d+\s*:\s*-?\d*\]"), "slices ('[a:b]') are not allowed in VPath"),
    (re.compile(r"\[\s*-?\d+\s*,\s*-?\d+"), "unions ('[0,2]') are not allowed in VPath"),
)


@dataclass(frozen=True)
class VPathParseResult:
    raw: str
    is_row_relative: bool  # starts with '@' rather than '$'


def _check_forbidden_source(raw: str) -> None:
    for pattern, message in _FORBIDDEN_SOURCE_PATTERNS:
        if pattern.search(raw):
            raise VPathError(f"{message}: {raw!r}")


def _walk_allowed(node: Any, raw: str) -> None:
    """Recursively assert every AST node is one of the allowed constructs."""
    if isinstance(node, (Root, This)):
        return
    if isinstance(node, Fields):
        return
    if isinstance(node, Index):
        return
    if isinstance(node, Slice):
        # jsonpath-ng represents bare `[*]` as a Slice(start=None, end=None, step=None).
        if node.start is not None or node.end is not None or (node.step not in (None, 1)):
            raise VPathError(f"only unbounded wildcard '[*]' is allowed, not a slice: {raw!r}")
        return
    if isinstance(node, Child):
        _walk_allowed(node.left, raw)
        _walk_allowed(node.right, raw)
        return
    if isinstance(node, Where):
        # `Where` backs the `.ext` `filter(...)` function-call extension, not the
        # `[?(...)]` bracket filter we allow below. Not part of the profile.
        raise VPathError(f"unsupported filter construct in VPath: {raw!r}")
    if isinstance(node, _ExtFilter):
        _check_filter(node, raw)
        return
    raise VPathError(f"unsupported VPath construct ({type(node).__name__}): {raw!r}")


def _check_filter(node: _ExtFilter, raw: str) -> None:
    """Restrict a ``[?(...)]`` filter to one ``==``/``!=`` comparison of a single scalar
    row member (``@.<field>``, not ``@.<field>.<nested>``) against a literal.

    Operating on the library's own parsed ``Expression`` objects (``.target``/``.op``/
    ``.value``) rather than string-matching ``str(expressions[0])`` — the structured form
    makes a path-to-path comparison (``@.a == @.b``) structurally distinguishable from a
    path-to-literal one without regex guesswork, since ``.value`` is only ever a Python
    literal for the cases the grammar accepts as an RHS.
    """
    expressions = getattr(node, "expressions", None)
    if not expressions or len(expressions) != 1:
        raise VPathError(f"VPath filters must contain exactly one comparison: {raw!r}")
    expr = expressions[0]
    if not isinstance(expr, _ExtExpression):
        raise VPathError(f"unsupported filter expression in VPath: {raw!r}")
    if expr.op not in _ALLOWED_FILTER_OPS:
        raise VPathError(
            f"VPath filters only support == and != (got {expr.op!r}): {raw!r}"
        )
    target = expr.target
    if not (isinstance(target, Child) and isinstance(target.left, This) and isinstance(target.right, Fields)):
        raise VPathError(
            f"VPath filter must compare a single scalar row member (@.<field>), not a nested path: {raw!r}"
        )
    if isinstance(expr.value, (list, dict)):
        raise VPathError(f"VPath filter value must be a scalar literal, not a list/object: {raw!r}")


def validate_vpath(raw: str) -> VPathParseResult:
    """Parse and validate a VPath string against the allowed profile.

    Raises ``VPathError`` on anything outside it. Call this at ruleset *load* time
    (``verify_rules.py`` and the ruleset store), not lazily at evaluation time — an
    invalid VPath should never reach a running evaluation.
    """
    if not raw or not isinstance(raw, str):
        raise VPathError(f"VPath must be a non-empty string, got {raw!r}")

    is_row_relative = raw.startswith("@")
    if not (raw == "$" or raw.startswith("$.") or raw.startswith("$[") or is_row_relative):
        raise VPathError(f"VPath must start with '$' or '@': {raw!r}")

    _check_forbidden_source(raw)

    # jsonpath-ng has no native '@' root; substitute '$' to parse, but remember which
    # root symbol was used so serialization later can tell absolute from row-relative.
    parseable = "$" + raw[1:] if is_row_relative else raw
    try:
        ast = _jsonpath_ext_parse(parseable)
    except Exception as exc:  # noqa: BLE001 — surface as our own error type
        raise VPathError(f"could not parse VPath {raw!r}: {exc}") from exc

    _walk_allowed(ast, raw)
    return VPathParseResult(raw=raw, is_row_relative=is_row_relative)


# --- resolution against a concrete payload ---------------------------------------------


def resolve_vpath(raw: str, document: dict, *, row: dict | None = None) -> list[tuple[str, Any]]:
    """Resolve a VPath against ``document`` (and, for ``@``-relative paths, ``row``).

    Returns a list of ``(concrete_path, value)`` pairs. A wildcard/filter VPath can yield
    zero, one, or many results; an absolute scalar VPath yields at most one.

    ``concrete_path`` is already in dotted-indexed form (``bankAccounts.0.iban``), ready for
    direct comparison against the portal's ``EffectiveFieldState.path``.
    """
    validated = validate_vpath(raw)
    target = row if validated.is_row_relative else document
    if target is None:
        return []

    parseable = "$" + raw[1:] if validated.is_row_relative else raw
    ast = _jsonpath_ext_parse(parseable)
    matches = ast.find(target)

    results: list[tuple[str, Any]] = []
    for m in matches:
        results.append((_serialize_path(str(m.full_path)), m.value))
    return results


def resolve_scope_rows(scope: str, document: dict) -> list[tuple[str, dict]]:
    """Expand a ``scope`` VPath to concrete rows for row-scoped rule evaluation.

    ``scope="$"`` yields a single ``("", document)`` pseudo-row (targets are absolute).
    ``scope="$.bankAccounts[*]"`` yields ``[("bankAccounts.0", row0), ("bankAccounts.1", row1), ...]``.
    """
    if scope == "$":
        return [("", document)]
    validated = validate_vpath(scope)
    if validated.is_row_relative:
        raise VPathError(f"scope must be an absolute VPath, not row-relative: {scope!r}")
    ast = _jsonpath_ext_parse(scope)
    matches = ast.find(document)
    return [(_serialize_path(str(m.full_path)), m.value) for m in matches]


def _serialize_path(jsonpath_ng_path: str) -> str:
    """Convert jsonpath-ng's ``str(datum.full_path)`` to dotted-indexed form.

    jsonpath-ng renders a resolved path like ``((postalAddresses.[0]).cityName)`` — parens
    around every ``Child`` node, indices as ``.[n]``. Strip the parens, fold ``.[n]`` to
    ``.n``: ``postalAddresses.0.cityName``. This is exactly ``EffectiveFieldState.path``
    (``rule-dependency-engine.ts:15-35``) and what the portal's ``diffNestedPaths``
    (``src/lib/nested-payload.ts:152``) produces — the alignment the shadow diff depends on.
    """
    p = jsonpath_ng_path.replace("(", "").replace(")", "")
    if p.startswith("$."):
        p = p[2:]
    elif p == "$":
        p = ""
    p = re.sub(r"\.\[(\d+)\]", r".\1", p)
    p = re.sub(r"\[(\d+)\]", r".\1", p)
    return p
