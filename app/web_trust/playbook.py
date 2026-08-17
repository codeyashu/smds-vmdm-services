"""Load per-country web-trust playbooks."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from app.web_trust.types import WebTrustPlaybook


def _playbook_root() -> Path:
    env = os.getenv("WEB_TRUST_PLAYBOOK_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config" / "web-trust-playbook"


@lru_cache(maxsize=64)
def load_web_trust_playbook(country_code: str) -> WebTrustPlaybook | None:
    normalized = country_code.strip().upper()
    path = _playbook_root() / f"{normalized}.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return WebTrustPlaybook.model_validate(raw)


def list_web_trust_countries() -> list[str]:
    root = _playbook_root()
    if not root.is_dir():
        return []
    return sorted(p.stem.upper() for p in root.glob("*.json"))
