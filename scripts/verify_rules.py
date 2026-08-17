#!/usr/bin/env python3
"""Verify every ruleset under ``config/rules/countries/**`` loads, its VPaths stay inside
the allowed profile, its validator references resolve, and its internal ``overrides``
references exist.

Phase-1 scope (see the design plan's §Phasing): this does NOT yet run
finite-domain conflict detection (C1-C8) or resolve ``extends``/``disable``/``patch``
overlay layering — both land in phase 2. What it *does* check is still real: schema
validity (via pydantic, on load), the VPath allowlist (``$..`` etc — the one restriction
conflict detection depends on later, so it must never silently slip into a committed file),
unknown validator names, and a ``v2-only-operator`` lossiness-ledger finding, which is
HIGH severity because it means the compat projection would silently corrupt v1 evaluator
behavior (an operator string the v1 switch doesn't recognize defaults to `false`) rather
than merely dropping a rule.

Mirrors ``scripts/verify_document_playbook.py``'s CLI contract: prints ``FAIL <msg>`` per
problem, ``OK <summary>`` on success, exit 0/1.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rules.compat import compile_ruleset
from app.rules.models import Ruleset
from app.rules.store import list_ruleset_countries, load_country_ruleset
from app.rules.validators import get_validator
from app.rules.vpath import VPathError, validate_vpath


def _check_vpaths(ruleset: Ruleset) -> list[str]:
    errors: list[str] = []
    for rule in ruleset.rules:
        if rule.x is not None:
            try:
                if rule.x.scope != "$":
                    validate_vpath(rule.x.scope)
                for target in rule.x.targets:
                    validate_vpath(target)
            except VPathError as exc:
                errors.append(f"{rule.field_name}: {exc}")
        for dependency in rule.dependencies or []:
            for condition in dependency.conditions or []:
                for p in (condition.path, *(condition.target_paths or [])):
                    if p is None:
                        continue
                    try:
                        validate_vpath(p)
                    except VPathError as exc:
                        errors.append(f"{rule.field_name}: {exc}")
    return errors


def _check_validators(ruleset: Ruleset) -> list[str]:
    errors: list[str] = []
    for rule in ruleset.rules:
        if rule.x is None:
            continue
        for effect in rule.x.effects:
            if effect.kind == "applyValidator":
                if not effect.validator or get_validator(effect.validator) is None:
                    errors.append(
                        f"{rule.field_name}: applyValidator references unknown validator "
                        f"{effect.validator!r}"
                    )
    return errors


def _check_duplicate_rule_ids(ruleset: Ruleset) -> list[str]:
    seen: dict[str, int] = {}
    for rule in ruleset.rules:
        if rule.x is None:
            continue
        seen[rule.x.rule_id] = seen.get(rule.x.rule_id, 0) + 1
    return [f"duplicate ruleId {rid!r} ({count} occurrences)" for rid, count in seen.items() if count > 1]


def _check_overlay_shape(ruleset: Ruleset) -> list[str]:
    errors: list[str] = []
    all_ids = {r.x.rule_id for r in ruleset.rules if r.x is not None}
    if (ruleset.disable or ruleset.patch) and not ruleset.extends:
        errors.append("disable/patch entries present but 'extends' is unset")
    for d in ruleset.disable:
        pass  # phase 2: verify d.rule_id exists in the extended (global) ruleset once
        # overlay resolution is implemented; nothing to check against in phase 1.
    for p in ruleset.patch:
        pass
    for rule in ruleset.rules:
        if rule.x is None:
            continue
        for override_id in rule.x.overrides:
            if override_id not in all_ids:
                errors.append(
                    f"{rule.field_name} ({rule.x.rule_id}): overrides unknown ruleId "
                    f"{override_id!r} (cross-layer overrides aren't resolvable until "
                    "phase 2's overlay resolution lands)"
                )
    return errors


def _check_ledger(ruleset: Ruleset, country: str) -> tuple[list[str], list[str]]:
    """Returns (fatal_errors, informational_notes)."""
    result = compile_ruleset(ruleset.rules, iso2_country_code=country)
    fatal: list[str] = []
    info: list[str] = []
    for entry in result.ledger:
        line = f"{entry.field_name} ({entry.rule_id}): {entry.reason} — {entry.detail}"
        if entry.reason == "v2-only-operator":
            fatal.append(line)
        else:
            info.append(line)
    return fatal, info


def main() -> int:
    countries = list_ruleset_countries()
    if not countries:
        print("OK 0 ruleset(s) — nothing imported yet")
        return 0

    errors: list[str] = []
    notes: list[str] = []

    for country in countries:
        ruleset = load_country_ruleset(country)
        if ruleset is None:
            errors.append(f"{country}: load failed")
            continue

        for msg in _check_vpaths(ruleset):
            errors.append(f"{country}: {msg}")
        for msg in _check_validators(ruleset):
            errors.append(f"{country}: {msg}")
        for msg in _check_duplicate_rule_ids(ruleset):
            errors.append(f"{country}: {msg}")
        for msg in _check_overlay_shape(ruleset):
            errors.append(f"{country}: {msg}")

        fatal, info = _check_ledger(ruleset, country)
        errors.extend(f"{country}: {m}" for m in fatal)
        notes.extend(f"{country}: {m}" for m in info)

    for note in notes:
        print(f"NOTE ledger: {note}")

    if errors:
        for err in errors:
            print(f"FAIL {err}")
        return 1

    print(f"OK {len(countries)} ruleset(s), VPaths valid, validators resolve, no dangling overrides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
