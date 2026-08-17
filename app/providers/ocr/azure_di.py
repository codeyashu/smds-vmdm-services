"""Azure Document Intelligence provider (paid; F0 free tier ~500 pages/month).

Best layout fidelity and native word-level bounding boxes. Uses prebuilt-layout by default.
Also renders page images via PyMuPDF so the vision LLM can read scans DI text alone may miss.
Lazy-imports the Azure SDK so the rest of the service loads without it installed.
"""

from __future__ import annotations

import base64

from app.providers.ocr.base import OcrProvider, OcrResult, OcrWord
from app.providers.ocr.render import render_page_images_b64


class AzureDiProvider:
    id = "azure-di"

    def __init__(self, endpoint: str, key: str, model: str = "prebuilt-layout"):
        self._endpoint = endpoint
        self._key = key
        self._model = model

    async def run(self, content: bytes, mime: str) -> OcrResult:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(self._endpoint, AzureKeyCredential(self._key))
        poller = client.begin_analyze_document(
            self._model,
            AnalyzeDocumentRequest(bytes_source=base64.b64encode(content).decode("ascii")),
        )
        result = poller.result()

        words: list[OcrWord] = []
        for page in result.pages or []:
            for w in page.words or []:
                poly = getattr(w, "polygon", None)
                bbox = None
                if poly and len(poly) >= 4:
                    xs = poly[0::2]
                    ys = poly[1::2]
                    bbox = [min(xs), min(ys), max(xs), max(ys)]
                words.append(
                    OcrWord(
                        text=w.content,
                        page=page.page_number,
                        bbox=bbox,
                        confidence=getattr(w, "confidence", None),
                    )
                )
        page_count = len(result.pages or []) or 1
        try:
            page_images = render_page_images_b64(content, mime)
        except Exception:
            page_images = []

        return OcrResult(
            text=result.content or "",
            words=words,
            page_count=page_count,
            page_images_b64=page_images,
            provider_id=self.id,
        )
