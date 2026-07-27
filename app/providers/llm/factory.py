"""LLM provider selection by env, mirroring the portal's get-llm-provider.ts.

`DOCAI_LLM_PROVIDER` picks the backend:
  azure  -> Azure OpenAI      (paid; reuses the portal tenant)
  openai -> OpenAI            (paid)
  gemini -> Google Gemini     (free tier available)
  groq   -> Groq              (free tier available)
  ollama -> local Ollama      (free, offline)
  none   -> disabled          (extraction returns 503)

Nothing is auto-selected with zero configuration — an unconfigured service must report
unavailable rather than silently assume a local Ollama daemon is running. Opt into the free
local path explicitly with `DOCAI_LLM_PROVIDER=ollama` (or set `OLLAMA_BASE_URL`/`OLLAMA_MODEL`).
"""

from __future__ import annotations

import os

from app.providers.llm.base import LlmProvider
from app.providers.llm.openai_compatible import OpenAiCompatibleProvider


def _normalize_aoai_endpoint(endpoint: str) -> str:
    """Strip deployment paths and query strings — portal often stores the full chat URL."""
    cleaned = endpoint.strip()
    if "?" in cleaned:
        cleaned = cleaned.split("?", 1)[0]
    marker = "/openai/"
    idx = cleaned.find(marker)
    if idx != -1:
        cleaned = cleaned[:idx]
    return cleaned.rstrip("/")


def _pref() -> str:
    p = os.getenv("DOCAI_LLM_PROVIDER", "").strip().lower()
    if p and p != "auto":
        return p
    if os.getenv("DOCAI_AOAI_KEY"):
        return "azure"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_MODEL"):
        return "ollama"
    return "none"


def get_llm_provider() -> LlmProvider | None:
    provider = _pref()

    if provider in ("none", "off"):
        return None

    if provider == "azure":
        key = os.getenv("DOCAI_AOAI_KEY")
        endpoint = os.getenv("DOCAI_AOAI_ENDPOINT")
        deployment = os.getenv("DOCAI_AOAI_DEPLOYMENT", "gpt-4o")
        version = os.getenv("DOCAI_AOAI_API_VERSION", "2024-08-01-preview")
        if not key or not endpoint:
            return None
        resource = _normalize_aoai_endpoint(endpoint)
        # Azure OpenAI is reached through the deployment path + api-version query.
        base_url = f"{resource}/openai/deployments/{deployment}"
        return OpenAiCompatibleProvider(
            id="azure",
            base_url=base_url,
            api_key=key,
            model=deployment,
            default_headers={"api-key": key},
            default_query={"api-version": version},
        )

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        return OpenAiCompatibleProvider(
            id="openai",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=key,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            return None
        return OpenAiCompatibleProvider(
            id="gemini",
            base_url=os.getenv(
                "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
            ),
            api_key=key,
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        )

    if provider == "groq":
        key = os.getenv("GROQ_API_KEY")
        if not key:
            return None
        return OpenAiCompatibleProvider(
            id="groq",
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=key,
            # Groq's Llama vision model; text-only default if the doc is digital.
            model=os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
        )

    # Ollama — local, free, offline. Any pulled vision model works (llama3.2-vision, qwen2-vl).
    return OpenAiCompatibleProvider(
        id="ollama",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "ollama"),  # Ollama ignores the value
        model=os.getenv("OLLAMA_MODEL", "llama3.2-vision"),
    )
