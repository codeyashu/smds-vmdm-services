#!/usr/bin/env python3
"""Adjudicate pre-uploaded extraction JSON fixtures (offline eval helper)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.documents.validation.adjudicate import adjudicate_bundle


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: adjudicate_fixture.py <countryCode> <fixture.json>", file=sys.stderr)
        return 2

    country = sys.argv[1]
    path = Path(sys.argv[2])
    raw = json.loads(path.read_text(encoding="utf-8"))
    extractions = raw.get("extractions") or raw
    form_snapshot = raw.get("formSnapshot") or {}
    existing_documents = raw.get("existingDocuments")
    result = adjudicate_bundle(
        country,
        extractions,
        form_snapshot=form_snapshot,
        existing_documents=existing_documents,
    )
    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
