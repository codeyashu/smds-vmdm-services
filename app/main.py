from __future__ import annotations

from fastapi import FastAPI

from app.api.v1 import agents, adjudicate, apply_patches, attachments, access_policy, company_search, doctypes, extract, nl_search, observability, onboard, requirements, rules, web_trust
from app.core.config import bootstrap_process_env, get_settings
from app.core.logging import configure_logging
from app.mcp.server import router as mcp_router
from app.providers.llm.factory import get_llm_provider
from app.providers.ocr.factory import get_ocr_provider

configure_logging()
bootstrap_process_env()

from app.observability.langfuse_model import ensure_default_langfuse_model_pricing

ensure_default_langfuse_model_pricing()

app = FastAPI(title="smds-vmdm-services", version="0.1.0")
app.include_router(extract.router)
app.include_router(adjudicate.router)
app.include_router(apply_patches.router)
app.include_router(attachments.router)
app.include_router(doctypes.router)
app.include_router(requirements.router)
app.include_router(company_search.router)
app.include_router(access_policy.router)
app.include_router(nl_search.router)
app.include_router(observability.router)
app.include_router(onboard.router)
app.include_router(agents.router)
app.include_router(web_trust.router)
app.include_router(rules.router)
app.include_router(mcp_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    from app.mdm.config import is_mdm_configured
    from app.mdm.validation_rules import is_validation_rules_configured
    from app.observability.langfuse_trace import is_langfuse_enabled
    from app.rules.store import list_ruleset_countries

    llm = get_llm_provider()
    ocr = get_ocr_provider()
    return {
        "status": "ok",
        "azureConfigured": get_settings().azure_ready,
        "llmProvider": llm.id if llm else None,
        "ocrProvider": ocr.id if ocr else None,
        "extractionAvailable": bool(llm and ocr),
        "langfuseEnabled": is_langfuse_enabled(),
        "mdmConfigured": is_mdm_configured(),
        "rulesImportConfigured": is_validation_rules_configured(),
        "rulesCountriesImported": len(list_ruleset_countries()),
    }
