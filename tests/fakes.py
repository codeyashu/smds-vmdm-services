"""Shared OCR/LLM fakes for pipeline and API tests. No network, no real credentials."""

from __future__ import annotations

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

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)

    async def complete_json(self, messages, *, schema=None, timeout_s=30.0) -> dict:
        return self._responses.pop(0)


class FailingOnRetryLlm:
    """Returns a malformed payload on the first call (triggering the pipeline's parse-error
    retry), then raises a transport-style exception on the retry (second) call. Used to exercise
    the `_complete_envelope_with_retry` branch that must convert ANY retry-attempt failure —
    not just a narrow parse-error tuple — into `ExtractionUpstreamError`.
    """

    id = "failing-on-retry-llm"
    supports_vision = True

    def __init__(self, first_response: dict, retry_exception: Exception):
        self._first_response = first_response
        self._retry_exception = retry_exception
        self._calls = 0

    async def complete_json(self, messages, *, schema=None, timeout_s=30.0) -> dict:
        self._calls += 1
        if self._calls == 1:
            return self._first_response
        raise self._retry_exception


GST_ENVELOPE: dict = {
    "doc_type": "IN_GST_CERTIFICATE",
    "doc_type_confidence": 0.97,
    "gst": {"gstin": "27AABCA1234F1Z5", "trade_name": "ACME LOGISTICS", "confidence": 0.98},
}
