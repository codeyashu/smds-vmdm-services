"""Onboard session API — AG-UI SSE stream endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.onboard.graph import run_onboard_graph
from app.onboard.session_store import create_session, get_session

router = APIRouter(prefix="/v1/onboard", tags=["onboard"])


class CreateSessionRequest(BaseModel):
    countryCode: str = Field(min_length=2, max_length=2)
    stewardId: str | None = None


class CreateSessionResponse(BaseModel):
    sessionId: str
    countryCode: str
    createdAt: str
    expiresAt: str


class RunSessionRequest(BaseModel):
    plan: dict | None = None
    branch: str | None = None


class ChatSessionRequest(BaseModel):
    message: str = Field(default="")
    conversationState: str | None = None
    formState: dict | None = None


class ChatSessionResponse(BaseModel):
    reply: str
    conversationState: str
    branch: str = "chat_only"


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_onboard_session(body: CreateSessionRequest) -> CreateSessionResponse:
    session = create_session(body.countryCode.upper(), body.stewardId)
    return CreateSessionResponse(
        sessionId=session.session_id,
        countryCode=session.country_code,
        createdAt=session.created_at.isoformat(),
        expiresAt=session.expires_at.isoformat(),
    )


@router.post("/sessions/{session_id}/chat", response_model=ChatSessionResponse)
async def chat_onboard_session(session_id: str, body: ChatSessionRequest) -> ChatSessionResponse:
    """Deterministic chat planner stub — portal BFF owns rule-engine gap fill for MVP."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    state = body.conversationState or "intake"
    message = (body.message or "").strip().lower()

    if state == "intake":
        if "no document" in message or message == "docs_none":
            return ChatSessionResponse(
                reply="No problem. What is the vendor trading name?",
                conversationState="gap_fill",
                branch="no_docs",
            )
        if "partial" in message:
            return ChatSessionResponse(
                reply="Upload whatever you have — I will extract and ask for the rest.",
                conversationState="collect_docs",
                branch="partial_docs",
            )
        if "document" in message or message == "docs_full":
            return ChatSessionResponse(
                reply="Upload your vendor documents and I will extract fields automatically.",
                conversationState="collect_docs",
                branch="full_enrichment",
            )
        return ChatSessionResponse(
            reply="Welcome. Do you have vendor documents, partial documents, or none?",
            conversationState="intake",
        )

    return ChatSessionResponse(
        reply="Continue in the portal chat — gap analysis runs server-side in the BFF.",
        conversationState=state,
    )


@router.post("/sessions/{session_id}/run")
async def run_onboard_session(session_id: str, body: RunSessionRequest | None = None):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    context: dict = {"plan": (body.plan if body else None)}
    if body and body.branch:
        context["branch"] = body.branch

    async def event_stream():
        async for frame in run_onboard_graph(session_id, context):
            yield frame

    return StreamingResponse(event_stream(), media_type="text/event-stream")
