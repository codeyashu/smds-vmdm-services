"""Free, local OCR for scanned pages via Tesseract (pytesseract + Pillow).

Requires the system `tesseract` binary and the `pytesseract` package. Rendered page images
come from PyMuPDF. Use for scanned PDFs / photos where there is no text layer.
"""

from __future__ import annotations

import base64
import io

from app.providers.ocr.base import OcrProvider, OcrResult, OcrWord

_RENDER_DPI = 200


class TesseractProvider:
    id = "tesseract"

    async def run(self, content: bytes, mime: str) -> OcrResult:
        import fitz
        import pytesseract
        from PIL import Image

        if mime.startswith("image/"):
            page_pngs = [content]
        else:
            doc = fitz.open(stream=content, filetype="pdf")
            page_pngs = []
            try:
                for i in range(doc.page_count):
                    pix = doc.load_page(i).get_pixmap(dpi=_RENDER_DPI)
                    page_pngs.append(pix.tobytes("png"))
            finally:
                doc.close()

        words: list[OcrWord] = []
        text_parts: list[str] = []
        images_b64: list[str] = []
        for page_index, png in enumerate(page_pngs, start=1):
            image = Image.open(io.BytesIO(png))
            text_parts.append(pytesseract.image_to_string(image))
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            for i, token in enumerate(data["text"]):
                if not token.strip():
                    continue
                conf = float(data["conf"][i]) / 100.0 if data["conf"][i] not in ("-1", -1) else None
                bbox = [
                    float(data["left"][i]),
                    float(data["top"][i]),
                    float(data["left"][i] + data["width"][i]),
                    float(data["top"][i] + data["height"][i]),
                ]
                words.append(OcrWord(text=token, page=page_index, bbox=bbox, confidence=conf))
            images_b64.append(base64.b64encode(png).decode("ascii"))

        return OcrResult(
            text="\n".join(text_parts),
            words=words,
            page_count=len(page_pngs),
            page_images_b64=images_b64,
            provider_id=self.id,
        )
