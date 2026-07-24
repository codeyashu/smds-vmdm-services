"""One client for every OpenAI-compatible /chat/completions endpoint.

Covers OpenAI proper, Azure OpenAI, Ollama (`/v1`), Gemini (OpenAI-compat base), and Groq —
they differ only in base URL, auth header, and model id. Uses the `openai` SDK, which handles
Azure vs standard routing when given the right base_url/api_key.
"""

from __future__ import annotations

import json
from typing import Any

from app.providers.llm.base import LlmMessage


def _to_openai_messages(messages: list[LlmMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.images_b64:
            content: list[dict[str, Any]] = [{"type": "text", "text": m.text}]
            for b64 in m.images_b64:
                content.append(
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                )
            out.append({"role": m.role, "content": content})
        else:
            out.append({"role": m.role, "content": m.text})
    return out


class OpenAiCompatibleProvider:
    def __init__(
        self,
        *,
        id: str,
        base_url: str,
        api_key: str,
        model: str,
        supports_vision: bool = True,
        default_headers: dict[str, str] | None = None,
    ):
        self.id = id
        self.model = model
        self.supports_vision = supports_vision
        self._base_url = base_url
        self._api_key = api_key
        self._default_headers = default_headers

    def _client(self):
        # Imported lazily so the module (and the pure test surface) loads without the SDK.
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            default_headers=self._default_headers,
        )

    async def complete_json(
        self,
        messages: list[LlmMessage],
        *,
        schema: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": 0,
            "timeout": timeout_s,
        }
        # Prefer strict JSON-schema when the endpoint supports it; fall back to json_object.
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema, "strict": True},
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
