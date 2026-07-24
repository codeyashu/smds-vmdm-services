"""Free, local OCR-less text + page-image extraction via PyMuPDF (fitz).

Best for digital/native PDFs where the text layer already exists — instant, exact, zero cost,
fully offline. For scanned PDFs the text will be empty; the pipeline then falls back to
Tesseract or a vision LLM on the rendered page images (which this still provides).
"""

from __future__ import annotations

import base64

from app.providers.ocr.base import OcrProvider, OcrResult, OcrWord

_RENDER_DPI = 150


class PyMuPdfTextProvider:
    id = "pymupdf"

    def __init__(self, render_images: bool = True):
        self.render_images = render_images

    async def run(self, content: bytes, mime: str) -> OcrResult:
        import fitz  # PyMuPDF, lazy import

        if mime.startswith("image/"):
            doc = fitz.open(stream=content, filetype=mime.split("/")[-1])
        else:
            doc = fitz.open(stream=content, filetype="pdf")

        words: list[OcrWord] = []
        text_parts: list[str] = []
        images: list[str] = []
        try:
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                text_parts.append(page.get_text("text"))
                for w in page.get_text("words"):
                    x0, y0, x1, y1, token = w[0], w[1], w[2], w[3], w[4]
                    words.append(OcrWord(text=token, page=page_index + 1, bbox=[x0, y0, x1, y1]))
                if self.render_images:
                    pix = page.get_pixmap(dpi=_RENDER_DPI)
                    images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
            return OcrResult(
                text="\n".join(text_parts),
                words=words,
                page_count=doc.page_count,
                page_images_b64=images,
                provider_id=self.id,
            )
        finally:
            doc.close()
