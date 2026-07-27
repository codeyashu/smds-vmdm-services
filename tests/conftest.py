"""Every test gets its own SQLite file so requirements-store state never leaks between tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_docai_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCAI_DB_PATH", str(tmp_path / "test.db"))
    from app.requirements import store

    store.reset_engine_for_tests()
    yield
    store.reset_engine_for_tests()
