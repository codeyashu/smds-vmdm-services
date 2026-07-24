"""OCR / layout provider interface.

Turns raw document bytes into text (and, where available, word-level bounding boxes and page
images). Implementations:
  - Azure Document Intelligence (paid; F0 free tier exists) — best layout + boxes
  - PyMuPDF text (free) — instant for digital/native PDFs, no OCR
  - Tesseract (free, local) — OCR for scans/images
The extraction pipeline consumes `OcrResult` uniformly regardless of which produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class OcrWord:
    text: str
    page: int
    bbox: list[float] | None = None  # [x0, y0, x1, y1] in page points
    confidence: float | None = None


@dataclass
class OcrResult:
    text: str  # full concatenated text, reading order
    words: list[OcrWord] = field(default_factory=list)
    page_count: int = 1
    # base64 PNGs per page, for handing to a vision LLM. May be empty (text-only providers).
    page_images_b64: list[str] = field(default_factory=list)
    provider_id: str = "unknown"


class OcrProvider(Protocol):
    id: str

    async def run(self, content: bytes, mime: str) -> OcrResult:
        ...
