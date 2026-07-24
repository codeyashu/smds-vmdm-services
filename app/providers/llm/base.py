"""LLM provider interface.

Any backend that can take a chat-style prompt (optionally with page images) and return a
JSON object satisfies this. Implementations: Azure OpenAI, OpenAI-compatible (OpenAI proper,
Ollama, Gemini, Groq — all speak the same /chat/completions shape). Selection is by env, so
the same extraction pipeline runs against a paid Azure deployment or a free local Ollama
model with no code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LlmMessage:
    role: str  # "system" | "user" | "assistant"
    text: str
    # Optional base64-encoded page images (PNG/JPEG) for vision models.
    images_b64: list[str] = field(default_factory=list)


class LlmProvider(Protocol):
    id: str
    supports_vision: bool

    async def complete_json(
        self,
        messages: list[LlmMessage],
        *,
        schema: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        """Return a parsed JSON object. Raise on transport/parse failure — the pipeline
        decides whether to degrade or surface the error."""
        ...
