"""Shared page-image rendering for vision LLM fallback."""

from __future__ import annotations

import base64
import os

_DEFAULT_DPI = 250


def _render_dpi() -> int:
    raw = os.getenv("DOCAI_PAGE_RENDER_DPI", str(_DEFAULT_DPI))
    try:
        return max(72, min(int(raw), 300))
    except ValueError:
        return _DEFAULT_DPI


def render_page_images_b64(content: bytes, mime: str, *, dpi: int | None = None) -> list[str]:
    """Render each page of a PDF or a single image to base64 PNGs."""
    import fitz  # PyMuPDF, lazy import

    render_dpi = dpi if dpi is not None else _render_dpi()

    if mime.startswith("image/"):
        doc = fitz.open(stream=content, filetype=mime.split("/")[-1])
    else:
        doc = fitz.open(stream=content, filetype="pdf")

    images: list[str] = []
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=render_dpi)
            images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
        return images
    finally:
        doc.close()


def render_page_half_crops_b64(content: bytes, mime: str, *, dpi: int = 300) -> list[str]:
    """Top and bottom half crops — helps composite PAN+Aadhaar scans on one page."""
    import fitz

    if mime.startswith("image/"):
        doc = fitz.open(stream=content, filetype=mime.split("/")[-1])
    else:
        doc = fitz.open(stream=content, filetype="pdf")

    crops: list[str] = []
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            rect = page.rect
            mid_y = (rect.y0 + rect.y1) / 2
            for clip in (
                fitz.Rect(rect.x0, rect.y0, rect.x1, mid_y),
                fitz.Rect(rect.x0, mid_y, rect.x1, rect.y1),
            ):
                pix = page.get_pixmap(dpi=dpi, clip=clip)
                crops.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
        return crops
    finally:
        doc.close()


def _can_render(content: bytes, mime: str) -> bool:
    if not content:
        return False
    if mime.startswith("image/"):
        return True
    return mime == "application/pdf" and content.startswith(b"%PDF")


def vision_focus_images_b64(
    content: bytes,
    mime: str,
    *,
    doc_type: str,
    filename: str | None = None,
    base_images: list[str] | None = None,
) -> list[str]:
    """Pick the best image set for a focused vision call (higher DPI, crops when needed)."""
    if not _can_render(content, mime):
        return list(base_images or [])

    hi_dpi = min(_render_dpi() + 50, 300)
    try:
        images = render_page_images_b64(content, mime, dpi=hi_dpi)
    except Exception:
        return list(base_images or [])

    name = (filename or "").lower()
    if doc_type == "IN_PAN_CARD" and ("aadhaar" in name or "pan_aadhaar" in name):
        try:
            crops = render_page_half_crops_b64(content, mime, dpi=300)
            images = crops + images
        except Exception:
            pass
    return images[:5]
