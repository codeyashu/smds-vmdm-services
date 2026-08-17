#!/usr/bin/env python3
"""Verify all country playbooks load and bindings resolve."""

from __future__ import annotations

import sys

from app.documents.playbook.binding_resolver import resolve_binding
from app.documents.playbook.config_store import list_playbook_countries, load_country_playbook


def main() -> int:
    countries = list_playbook_countries()
    if not countries:
        print("FAIL: no playbooks found")
        return 1

    errors: list[str] = []
    for country in countries:
        book = load_country_playbook(country)
        if book is None:
            errors.append(f"{country}: load failed")
            continue
        for binding in book.bindings:
            resolved = resolve_binding(binding)
            if not resolved.path:
                errors.append(f"{country}: {binding.logical_field_id} empty path")

    if errors:
        for err in errors:
            print(f"FAIL {err}")
        return 1

    print(f"OK {len(countries)} playbook(s), bindings resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
