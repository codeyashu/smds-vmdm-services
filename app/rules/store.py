"""Ruleset file storage — ``config/rules/**``.

Follows the repo's established convention: ``config/`` holds authored/committed
configuration (mirroring ``app/documents/playbook/config_store.py`` and
``app/documents/playbook/apply_overlay_store.py``), ``data/`` holds runtime state. Rulesets
are git-versioned YAML files, not a database — git already supplies author, diff, review,
and revert, and ``scripts/verify_rules.py`` becomes a CI gate on the same PR that changes a
ruleset (design plan §B.1).

**Phase 1 scope:** this module loads a single country ruleset file. It does NOT resolve
``extends``/``disable``/``patch`` against a ``global`` layer yet — that resolution
(design plan §B.7, "Country scaling — layering and resolution") ships in phase 2 alongside
conflict detection, because patch/disable only become safe to resolve automatically once
conflicts between layers can be detected. The ``Ruleset`` model already carries those fields
so phase-1-authored files are forward-compatible with zero migration.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from app.rules.models import Ruleset


def rules_root() -> Path:
    env = os.getenv("RULES_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config" / "rules"


def country_ruleset_path(iso2_country_code: str) -> Path:
    cc = iso2_country_code.strip().upper()
    return rules_root() / "countries" / cc / "ruleset.yaml"


def global_ruleset_path() -> Path:
    return rules_root() / "global" / "ruleset.yaml"


@lru_cache(maxsize=64)
def load_country_ruleset(iso2_country_code: str) -> Ruleset | None:
    path = country_ruleset_path(iso2_country_code)
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Ruleset.model_validate(raw)


def list_ruleset_countries() -> list[str]:
    root = rules_root() / "countries"
    if not root.is_dir():
        return []
    return sorted(p.name.upper() for p in root.iterdir() if p.is_dir() and (p / "ruleset.yaml").is_file())


def save_country_ruleset(ruleset: Ruleset) -> Ruleset:
    """Whole-file rewrite, matching the ``apply_overlay_store.py`` idiom — no partial
    writes, no locking (single authoring session assumed in phase 1; concurrent-author
    safety is deferred to the sqlmodel migration mentioned as a maybe in the design plan,
    only if the authoring UI ever needs it)."""
    countries = ruleset.selector.iso2_country_code or []
    if len(countries) != 1:
        raise ValueError(
            "save_country_ruleset expects exactly one country in selector.iso2CountryCode"
        )
    path = country_ruleset_path(countries[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = ruleset.model_dump(by_alias=True, exclude_none=True, mode="json")
    path.write_text(yaml.safe_dump(dumped, sort_keys=False, allow_unicode=True), encoding="utf-8")
    reset_cache_for_tests()
    return ruleset


def reset_cache_for_tests() -> None:
    load_country_ruleset.cache_clear()
