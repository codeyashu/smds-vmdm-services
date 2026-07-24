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


GST_ENVELOPE: dict = {
    "doc_type": "IN_GST_CERTIFICATE",
    "doc_type_confidence": 0.97,
    "gst": {"gstin": "27AABCA1234F1Z5", "trade_name": "ACME LOGISTICS", "confidence": 0.98},
}
