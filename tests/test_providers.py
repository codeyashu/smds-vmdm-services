"""Provider factory selection — pure, no network, no real credentials needed."""

from __future__ import annotations

import importlib

from app.providers.llm import factory as llm_factory
from app.providers.ocr import factory as ocr_factory


def _reload():
    importlib.reload(llm_factory)
    importlib.reload(ocr_factory)


def test_llm_provider_none_with_zero_config(monkeypatch):
    for key in (
        "DOCAI_LLM_PROVIDER",
        "DOCAI_AOAI_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    assert llm_factory.get_llm_provider() is None


def test_llm_provider_azure_when_configured(monkeypatch):
    monkeypatch.setenv("DOCAI_LLM_PROVIDER", "azure")
    monkeypatch.setenv("DOCAI_AOAI_KEY", "k")
    monkeypatch.setenv("DOCAI_AOAI_ENDPOINT", "https://example.openai.azure.com")
    provider = llm_factory.get_llm_provider()
    assert provider is not None and provider.id == "azure"


def test_llm_provider_ollama_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("DOCAI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DOCAI_AOAI_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2-vision")
    provider = llm_factory.get_llm_provider()
    assert provider is not None and provider.id == "ollama"


def test_llm_provider_explicit_ollama_selection(monkeypatch):
    monkeypatch.setenv("DOCAI_LLM_PROVIDER", "ollama")
    provider = llm_factory.get_llm_provider()
    assert provider is not None and provider.id == "ollama"
    assert provider.model  # has a default model even with no OLLAMA_MODEL set


def test_llm_provider_gemini_free_tier(monkeypatch):
    monkeypatch.setenv("DOCAI_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    provider = llm_factory.get_llm_provider()
    assert provider is not None and provider.id == "gemini"


def test_llm_provider_none_explicit(monkeypatch):
    monkeypatch.setenv("DOCAI_LLM_PROVIDER", "none")
    assert llm_factory.get_llm_provider() is None


def test_ocr_provider_defaults_to_free_pymupdf(monkeypatch):
    monkeypatch.delenv("DOCAI_OCR_PROVIDER", raising=False)
    provider = ocr_factory.get_ocr_provider()
    assert provider is not None and provider.id == "pymupdf"


def test_ocr_provider_azure_di_none_without_credentials(monkeypatch):
    monkeypatch.setenv("DOCAI_OCR_PROVIDER", "azure_di")
    monkeypatch.delenv("DOCAI_DI_ENDPOINT", raising=False)
    monkeypatch.delenv("DOCAI_DI_KEY", raising=False)
    assert ocr_factory.get_ocr_provider() is None


def test_ocr_provider_azure_di_when_configured(monkeypatch):
    monkeypatch.setenv("DOCAI_OCR_PROVIDER", "azure_di")
    monkeypatch.setenv("DOCAI_DI_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("DOCAI_DI_KEY", "k")
    provider = ocr_factory.get_ocr_provider()
    assert provider is not None and provider.id == "azure-di"


def test_ocr_provider_auto_prefers_azure_di_when_credentials_present(monkeypatch):
    monkeypatch.delenv("DOCAI_OCR_PROVIDER", raising=False)  # "auto"
    monkeypatch.setenv("DOCAI_DI_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("DOCAI_DI_KEY", "k")
    provider = ocr_factory.get_ocr_provider()
    assert provider is not None and provider.id == "azure-di"


def test_llm_provider_auto_prefers_azure_when_credentials_present(monkeypatch):
    monkeypatch.delenv("DOCAI_LLM_PROVIDER", raising=False)  # "auto" preference
    monkeypatch.setenv("DOCAI_AOAI_KEY", "k")
    monkeypatch.setenv("DOCAI_AOAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    provider = llm_factory.get_llm_provider()
    assert provider is not None and provider.id == "azure"
