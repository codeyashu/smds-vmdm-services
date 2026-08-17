"""Tests for document apply-config overlay mutations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.documents.playbook.apply_mutations import (
    remove_extraction_attribute,
    upsert_extraction_attribute,
)
from app.documents.playbook.apply_overlay_store import overlay_path


@pytest.fixture
def overlay_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DOC_APPLY_OVERLAY_DIR", str(tmp_path))
    return tmp_path


def test_upsert_and_remove_attribute(overlay_dir: Path):
  # Seed overlay from committed IN overlay
  repo_overlay = Path(__file__).resolve().parents[1] / "config" / "document-apply-overlay" / "IN.json"
  overlay_dir.joinpath("IN.json").write_text(repo_overlay.read_text(encoding="utf-8"), encoding="utf-8")

  updated = upsert_extraction_attribute(
      "IN",
      "IN_PAN_CARD",
      {
          "label": "Custom trading name",
          "formPath": "tradingName",
          "enabled": False,
      },
  )
  pan = next(doc for doc in updated["documents"] if doc["docType"] == "IN_PAN_CARD")
  trading = next(attr for attr in pan["attributes"] if attr["formPath"] == "tradingName")
  assert trading["enabled"] is False
  assert trading["label"] == "Custom trading name"

  remove_extraction_attribute("IN", "IN_PAN_CARD", trading["id"])
  persisted = json.loads(overlay_path("IN").read_text(encoding="utf-8"))
  pan = next(doc for doc in persisted["documents"] if doc["docType"] == "IN_PAN_CARD")
  assert not any(attr["formPath"] == "tradingName" for attr in pan["attributes"])
