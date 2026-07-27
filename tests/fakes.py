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


from app.providers.ocr.base import OcrResult


class FakeOcr:
    id = "fake-ocr"

    def __init__(self, text: str = "GSTIN 27AABCA1234F1Z5 Trade Name: ACME"):
        self._text = text

    async def run(self, content: bytes, mime: str) -> OcrResult:
        return OcrResult(text=self._text, page_count=1, page_images_b64=["img"], provider_id=self.id)


class FailingOcr:
    id = "failing-ocr"

    async def run(self, content: bytes, mime: str) -> OcrResult:
        raise RuntimeError("boom")


class FakeLlm:
    id = "fake-llm"
    supports_vision = True

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)

    async def complete_json(self, messages, *, schema=None, timeout_s=30.0) -> dict[str, Any]:
        return self._responses.pop(0)


class FailingOnRetryLlm:
    id = "failing-on-retry-llm"
    supports_vision = True

    def __init__(self, first_response: dict[str, Any], retry_exception: Exception):
        self._first_response = first_response
        self._retry_exception = retry_exception
        self._calls = 0

    async def complete_json(self, messages, *, schema=None, timeout_s=30.0) -> dict[str, Any]:
        self._calls += 1
        if self._calls == 1:
            return self._first_response
        raise self._retry_exception


GST_ENVELOPE: dict[str, Any] = {
    "doc_type": "IN_GST_CERTIFICATE",
    "doc_type_confidence": 0.97,
    "gst": {"gstin": "27AABCA1234F1Z5", "trade_name": "ACME LOGISTICS", "confidence": 0.98},
}
