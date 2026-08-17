"""Load country playbooks from JSON (vault-ready)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.documents.playbook.types import CountryPlaybook


def _playbook_root() -> Path:
    env = os.getenv("DOC_PLAYBOOK_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config" / "document-playbook"


@lru_cache(maxsize=32)
def load_country_playbook(country_code: str) -> CountryPlaybook | None:
    normalized = country_code.strip().upper()
    path = _playbook_root() / f"{normalized}.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CountryPlaybook.model_validate(raw)


def list_playbook_countries() -> list[str]:
    root = _playbook_root()
    if not root.is_dir():
        return []
    return sorted(p.stem.upper() for p in root.glob("*.json"))


def playbook_as_dict(country_code: str) -> dict[str, Any] | None:
    book = load_country_playbook(country_code)
    return book.model_dump(by_alias=True) if book else None
