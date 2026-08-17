"""Web-trust verification API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import require_service_bearer
from app.web_trust.feedback_store import WebTrustFeedbackRequest, WebTrustFeedbackResponse, record_web_trust_feedback
from app.web_trust.playbook import load_web_trust_playbook, list_web_trust_countries
from app.web_trust.types import WebTrustVerifyRequest, WebTrustVerifyResponse
from app.web_trust.verify import verify_web_trust_async

router = APIRouter(
    prefix="/v1/web-trust",
    tags=["web-trust"],
    dependencies=[Depends(require_service_bearer)],
)


@router.get("/playbook")
async def get_playbook(country: str = Query(..., min_length=2, max_length=2)) -> dict:
    book = load_web_trust_playbook(country)
    if book is None:
        return {"countryCode": country.upper(), "status": "off"}
    return book.model_dump()


@router.get("/countries")
async def list_countries() -> dict[str, list[str]]:
    return {"countries": list_web_trust_countries()}


@router.post("/verify", response_model=WebTrustVerifyResponse)
async def verify_route(body: WebTrustVerifyRequest) -> WebTrustVerifyResponse:
    return await verify_web_trust_async(body)


@router.post("/feedback", response_model=WebTrustFeedbackResponse)
async def feedback_route(body: WebTrustFeedbackRequest) -> WebTrustFeedbackResponse:
    return record_web_trust_feedback(body)
