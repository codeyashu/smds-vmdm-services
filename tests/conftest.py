"""Every test gets its own SQLite file so requirements-store state never leaks between tests."""

from __future__ import annotations

import pytest

_PROVIDER_ENV_KEYS = (
    "DOCAI_LLM_PROVIDER",
    "DOCAI_OCR_PROVIDER",
    "DOCAI_AOAI_KEY",
    "DOCAI_AOAI_ENDPOINT",
    "DOCAI_AOAI_DEPLOYMENT",
    "DOCAI_AOAI_API_VERSION",
    "DOCAI_DI_ENDPOINT",
    "DOCAI_DI_KEY",
    "DOCAI_DI_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_BASE_URL",
    "GEMINI_MODEL",
    "GROQ_API_KEY",
    "GROQ_BASE_URL",
    "GROQ_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_API_KEY",
    "DOCAI_SERVICE_BEARER_TOKEN",
)


@pytest.fixture(autouse=True)
def zero_provider_config(monkeypatch):
    """Isolate tests from repo `.env` so unconfigured paths return 503 and auth stays open."""
    for key in _PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DOCAI_LLM_PROVIDER", "none")
    monkeypatch.setenv("DOCAI_OCR_PROVIDER", "azure_di")
    monkeypatch.setenv("DOCAI_SERVICE_BEARER_TOKEN", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_docai_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCAI_DB_PATH", str(tmp_path / "test.db"))
    from app.requirements import store
    from app.onboard import run_store

    store.reset_engine_for_tests()
    run_store.reset_engine_for_tests()
    yield
    store.reset_engine_for_tests()
    run_store.reset_engine_for_tests()


@pytest.fixture(autouse=True)
def isolated_rules_store(tmp_path, monkeypatch):
    """Rulesets live in ``config/rules/**``, loaded through an ``lru_cache`` keyed only by
    country code (``app/rules/store.py``) — not by ``RULES_CONFIG_DIR``. Without this
    fixture, a test that imports a country ruleset would leave it cached in-process and
    visible to every later test, regardless of which directory that later test points at.
    """
    monkeypatch.setenv("RULES_CONFIG_DIR", str(tmp_path / "rules"))
    from app.rules import store

    store.reset_cache_for_tests()
    yield
    store.reset_cache_for_tests()
