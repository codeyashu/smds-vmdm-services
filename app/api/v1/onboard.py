"""Onboard session API — AG-UI SSE stream endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.onboard import run_store
from app.onboard.graph import run_onboard_graph
from app.onboard.session_store import create_session, get_session, update_session_state

router = APIRouter(prefix="/v1/onboard", tags=["onboard"])

ORCHESTRATOR_VERSION = 2


class CreateSessionRequest(BaseModel):
    countryCode: str = Field(min_length=2, max_length=2)
    stewardId: str | None = None


class CreateSessionResponse(BaseModel):
    sessionId: str
    countryCode: str
    createdAt: str
    expiresAt: str


class OnboardFile(BaseModel):
    name: str
    type: str = "application/octet-stream"
    contentBase64: str


class RunSessionRequest(BaseModel):
    countryCode: str | None = None
    formState: dict | None = None
    docAvailability: str | None = None
    files: list[OnboardFile] = Field(default_factory=list)
    branch: str | None = None
    plan: dict | None = None
    resolvedStages: dict | None = None


class ChatSessionRequest(BaseModel):
    message: str = Field(default="")
    conversationState: str | None = None
    formState: dict | None = None
    docAvailability: str | None = None
    quickReplyId: str | None = None


class ChatSessionResponse(BaseModel):
    reply: str
    conversationState: str
    branch: str = "chat_only"
    uiAction: str | None = None
    card: str | None = None
    gapField: dict | None = None
    quickReplies: list[dict[str, str]] | None = None
    agentTurn: dict | None = None


class OnboardReadyResponse(BaseModel):
    status: str
    orchestratorVersion: int


@router.get("/ready", response_model=OnboardReadyResponse)
async def onboard_ready() -> OnboardReadyResponse:
    return OnboardReadyResponse(status="ok", orchestratorVersion=ORCHESTRATOR_VERSION)


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_onboard_session(body: CreateSessionRequest) -> CreateSessionResponse:
    session = create_session(body.countryCode.upper(), body.stewardId)
    run_store.create_run(session.session_id, session.country_code)
    return CreateSessionResponse(
        sessionId=session.session_id,
        countryCode=session.country_code,
        createdAt=session.created_at.isoformat(),
        expiresAt=session.expires_at.isoformat(),
    )


@router.get("/runs")
async def list_onboard_runs(limit: int = 50) -> dict:
    """Summaries only (counts, not the full stage/tool-call JSON) — see to_summary_dict."""
    capped_limit = max(1, min(limit, 200))
    runs = run_store.list_runs(capped_limit)
    return {"runs": [run_store.to_summary_dict(run) for run in runs]}


@router.get("/runs/{run_id}")
async def get_onboard_run(run_id: str) -> dict:
    """Durable run record — status, stage results, tool-call log. Survives a services restart,
    unlike the session store above, which is why a resumed or externally-polled run reads from
    here rather than from session state."""
    run = run_store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_store.to_dict(run)


@router.post("/sessions/{session_id}/chat", response_model=ChatSessionResponse)
async def chat_onboard_session(session_id: str, body: ChatSessionRequest) -> ChatSessionResponse:
    from app.onboard.agent_turn import chat_planner_to_agent_turn
    from app.onboard.chat_agent import plan_chat_turn_async

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    doc_availability = body.docAvailability or "none"
    planned = await plan_chat_turn_async(
        body.message or "",
        body.conversationState or "intake",
        doc_availability,
        session.country_code,
        body.formState or {},
        body.quickReplyId,
    )

    return ChatSessionResponse(
        reply=planned.reply,
        conversationState=planned.conversationState,
        branch=planned.branch or "chat_only",
        uiAction=planned.uiAction,
        card=planned.card,
        gapField=planned.gapField.model_dump() if planned.gapField else None,
        quickReplies=planned.quickReplies,
        agentTurn=chat_planner_to_agent_turn(planned),
    )


@router.post("/sessions/{session_id}/run")
async def run_onboard_session(session_id: str, body: RunSessionRequest | None = None):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    context: dict = {
        "sessionId": session_id,
        "countryCode": session.country_code,
        "formState": {},
        "files": [],
    }
    if body:
        if body.plan:
            context["plan"] = body.plan
        if body.branch:
            context["branch"] = body.branch
        if body.countryCode:
            context["countryCode"] = body.countryCode
        if body.formState is not None:
            context["formState"] = body.formState
        if body.docAvailability:
            context["docAvailability"] = body.docAvailability
        if body.files:
            context["files"] = [file.model_dump() for file in body.files]
        if body.resolvedStages is not None:
            context["resolvedStages"] = body.resolvedStages

    update_session_state(session_id, {"lastRun": context})
    if run_store.get_run(session_id) is not None:
        run_store.set_working_state(session_id, context.get("formState") or {})

    async def event_stream():
        async for frame in run_onboard_graph(session_id, context):
            _record_frame(session_id, frame)
            yield frame

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _record_frame(run_id: str, frame: str) -> None:
    """Tees an AG-UI SSE frame into the durable run record as it streams past. Best-effort —
    a run record that misses one event is a smaller loss than a stream that breaks on it."""
    if run_store.get_run(run_id) is None:
        return
    try:
        body = json.loads(frame.removeprefix("data: ").strip())
    except (ValueError, AttributeError):
        return
    event_type = body.get("type")
    payload = body.get("payload") or {}
    try:
        if event_type == "RUN_STARTED":
            run_store.update_status(run_id, "running")
        elif event_type == "STEP_FINISHED":
            run_store.append_stage_result(run_id, str(payload.get("step")), payload)
        elif event_type == "TOOL_CALL_START":
            run_store.append_tool_call(run_id, str(payload.get("toolCallId")), str(payload.get("toolCallName")))
        elif event_type == "RUN_FINISHED":
            run_store.update_status(run_id, "done")
    except Exception:
        pass
