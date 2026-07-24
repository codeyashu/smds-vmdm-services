"""OCR provider selection by env.

`DOCAI_OCR_PROVIDER`:
  azure_di -> Azure Document Intelligence (best layout + native word boxes)
  pymupdf  -> PyMuPDF text + page images  (free, offline; digital PDFs)
  tesseract-> Tesseract OCR               (free, offline; scans)   [optional dep]
  auto     -> Azure DI when DOCAI_DI_ENDPOINT/DOCAI_DI_KEY are set, else the free
              PyMuPDF extractor (default)
"""

from __future__ import annotations

import os

from app.providers.ocr.base import OcrProvider


def _azure_di_or_none() -> OcrProvider | None:
    endpoint = os.getenv("DOCAI_DI_ENDPOINT")
    key = os.getenv("DOCAI_DI_KEY")
    if not endpoint or not key:
        return None
    from app.providers.ocr.azure_di import AzureDiProvider

    return AzureDiProvider(endpoint, key, os.getenv("DOCAI_DI_MODEL", "prebuilt-layout"))


def get_ocr_provider() -> OcrProvider | None:
    pref = os.getenv("DOCAI_OCR_PROVIDER", "auto").strip().lower()

    if pref in ("azure_di", "azure-di", "azure"):
        return _azure_di_or_none()

    if pref == "tesseract":
        from app.providers.ocr.tesseract import TesseractProvider

        return TesseractProvider()

    if pref == "pymupdf":
        from app.providers.ocr.pymupdf_text import PyMuPdfTextProvider

        return PyMuPdfTextProvider(render_images=True)

    # auto: prefer Azure DI when its credentials are present (matches the LLM factory's
    # auto-detect of DOCAI_AOAI_KEY), otherwise fall back to the free local extractor.
    azure = _azure_di_or_none()
    if azure is not None:
        return azure

    from app.providers.ocr.pymupdf_text import PyMuPdfTextProvider

    return PyMuPdfTextProvider(render_images=True)
