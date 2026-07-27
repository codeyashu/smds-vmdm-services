"""Runtime settings. Azure creds are optional at import time so pure logic and its tests
run with zero configuration; the extraction path checks for them and fails clearly when
they are missing.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCAI_", env_file=".env", extra="ignore")

    # Provider selection (see app/providers/{ocr,llm}/factory.py for the full option list and
    # the actual auto-detect logic — these fields are descriptive; the factories read env
    # directly). "auto" prefers Azure (DI / OpenAI) whenever its credentials are present and
    # falls back to the free local stack (PyMuPDF; Ollama only on explicit opt-in) otherwise.
    ocr_provider: str = "auto"      # auto | azure_di | pymupdf | tesseract
    llm_provider: str = "auto"      # auto | azure | openai | gemini | groq | ollama | none

    # Azure Document Intelligence (used when ocr_provider=azure_di)
    di_endpoint: str | None = None
    di_key: str | None = None
    di_model: str = "prebuilt-layout"

    # Azure OpenAI (used when llm_provider=azure; reuses the portal tenant)
    aoai_endpoint: str | None = None
    aoai_key: str | None = None
    aoai_deployment: str = "gpt-4o"
    aoai_api_version: str = "2024-08-01-preview"

    # Upload caps
    max_file_bytes: int = 10 * 1024 * 1024
    max_pages: int = 20
    max_batch_files: int = 5
    allowed_mime: tuple[str, ...] = (
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    # Service auth — token the portal BFF presents. When unset, auth is disabled (dev only).
    service_bearer_token: str | None = None

    llm_timeout_s: float = Field(default=30.0)

    @property
    def azure_ready(self) -> bool:
        """True when the fully-Azure path (DI + AOAI) is configured."""
        return bool(self.di_endpoint and self.di_key and self.aoai_endpoint and self.aoai_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def bootstrap_process_env() -> None:
    """Expose pydantic-loaded `.env` values to `os.environ` for factory helpers."""
    import os

    settings = get_settings()
    for env_key, value in (
        ("DOCAI_OCR_PROVIDER", settings.ocr_provider),
        ("DOCAI_LLM_PROVIDER", settings.llm_provider),
        ("DOCAI_DI_ENDPOINT", settings.di_endpoint),
        ("DOCAI_DI_KEY", settings.di_key),
        ("DOCAI_DI_MODEL", settings.di_model),
        ("DOCAI_AOAI_ENDPOINT", settings.aoai_endpoint),
        ("DOCAI_AOAI_KEY", settings.aoai_key),
        ("DOCAI_AOAI_DEPLOYMENT", settings.aoai_deployment),
        ("DOCAI_AOAI_API_VERSION", settings.aoai_api_version),
        ("DOCAI_SERVICE_BEARER_TOKEN", settings.service_bearer_token),
    ):
        if value and str(value).lower() != "auto" and not os.getenv(env_key):
            os.environ[env_key] = str(value)
