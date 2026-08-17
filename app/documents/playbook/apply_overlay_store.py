"""Persist admin-editable apply UI config — overlays playbook defaults."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ApplyAttribute(BaseModel):
    id: str
    label: str
    form_path: str = Field(alias="formPath")
    enabled: bool = True
    mandatory: bool = False
    writable: bool = True
    needs_resolution: str | None = Field(default=None, alias="needsResolution")

    model_config = {"populate_by_name": True}


class ApplyDocument(BaseModel):
    doc_type: str = Field(alias="docType")
    writable: bool = True
    attributes: list[ApplyAttribute] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CountryApplyConfig(BaseModel):
    country_code: str = Field(alias="countryCode")
    documents: list[ApplyDocument] = Field(default_factory=list)
    multi_source_fields: dict[str, list[str]] = Field(default_factory=dict, alias="multiSourceFields")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


def _overlay_root() -> Path:
    env = os.getenv("DOC_APPLY_OVERLAY_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config" / "document-apply-overlay"


def overlay_path(country_code: str) -> Path:
    return _overlay_root() / f"{country_code.strip().upper()}.json"


def load_apply_overlay(country_code: str) -> CountryApplyConfig | None:
    path = overlay_path(country_code)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CountryApplyConfig.model_validate(raw)


def save_apply_overlay(config: CountryApplyConfig) -> CountryApplyConfig:
    normalized = CountryApplyConfig.model_validate(
        {
            **config.model_dump(by_alias=True),
            "countryCode": config.country_code.upper(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    )
    root = _overlay_root()
    root.mkdir(parents=True, exist_ok=True)
    overlay_path(normalized.country_code).write_text(
        json.dumps(normalized.as_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized
