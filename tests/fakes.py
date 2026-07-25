"""Test doubles for the LlmProvider protocol — no network, deterministic responses."""

from __future__ import annotations

from typing import Any

from app.providers.llm.base import LlmMessage


class FakeLlmProvider:
    """Returns each entry of ``responses`` in order on successive ``complete_json`` calls,
    or repeats the last one forever if only one is given. If ``error`` is set, raises it
    instead of returning."""

    id = "fake"
    supports_vision = False

    def __init__(self, responses: list[dict[str, Any]] | None = None, error: Exception | None = None):
        self.responses = responses or [{}]
        self.error = error
        self.calls: list[list[LlmMessage]] = []
        self._i = 0

    async def complete_json(
        self,
        messages: list[LlmMessage],
        *,
        schema: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        response = self.responses[min(self._i, len(self.responses) - 1)]
        self._i += 1
        return response
