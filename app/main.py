from __future__ import annotations

from fastapi import FastAPI

from app.api.v1 import company_search, doctypes, extract, nl_search
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.providers.llm.factory import get_llm_provider
from app.providers.ocr.factory import get_ocr_provider

configure_logging()

app = FastAPI(title="smds-vmdm-services", version="0.1.0")
app.include_router(extract.router)
app.include_router(doctypes.router)
app.include_router(company_search.router)
app.include_router(nl_search.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    llm = get_llm_provider()
    ocr = get_ocr_provider()
    return {
        "status": "ok",
        "azureConfigured": get_settings().azure_ready,
        "llmProvider": llm.id if llm else None,
        "ocrProvider": ocr.id if ocr else None,
        "extractionAvailable": bool(llm and ocr),
    }
