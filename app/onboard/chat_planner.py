"""Deterministic onboard chat planner — port of portal chat-planner.ts."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field


ConversationState = Literal[
    "intake",
    "collect_docs",
    "enriching",
    "review",
    "gap_fill",
    "duplicate_check",
    "confirm_create",
    "handoff",
]

DocAvailability = Literal["full", "partial", "none"]


class GapField(BaseModel):
    path: str
    label: str
    kind: str = "text"
    validationHint: str | None = None


class ChatPlannerResponse(BaseModel):
    reply: str
    conversationState: ConversationState
    uiAction: str | None = None
    card: str | None = None
    gapField: GapField | None = None
    quickReplies: list[dict[str, str]] | None = None
    branch: str | None = None


INTAKE_REPLIES = [
    {"id": "docs_full", "label": "I have documents"},
    {"id": "docs_partial", "label": "Partial documents"},
    {"id": "docs_none", "label": "No documents"},
]

PRIORITY_GAP_FIELDS = [
    GapField(path="tradingName", label="Trading name", kind="text"),
    GapField(path="vendorGroupType", label="Account group", kind="select"),
]

ADDRESS_CITY_PATH = "postalAddresses.0.cityName"
ADDRESS_POSTAL_PATH = "postalAddresses.0.postalCode"
ADDRESS_GAP_FIELD = GapField(
    path=ADDRESS_CITY_PATH,
    label="City and postal code",
    kind="text",
)


def _address_gap_needed(form_state: dict[str, Any]) -> bool:
    city = _read_path(form_state, ADDRESS_CITY_PATH)
    postal = _read_path(form_state, ADDRESS_POSTAL_PATH)
    return _is_empty(city) or _is_empty(postal)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _patch_from_message(message: str, form_state: dict[str, Any]) -> dict[str, Any] | None:
    trimmed = message.strip()
    if not trimmed:
        return None

    if re.fullmatch(r"IN", trimmed, re.I):
        addresses = form_state.get("postalAddresses")
        first = addresses[0] if isinstance(addresses, list) and addresses else {}
        if not isinstance(first, dict):
            first = {}
        return {
            **form_state,
            "postalAddresses": [{"addressPurpose": "BILL_TO", "countryCode": "IN", **first}],
        }

    pan_match = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", trimmed, re.I)
    if pan_match:
        out = deepcopy(form_state)
        tax = out.get("taxInformation")
        if not isinstance(tax, dict):
            tax = {}
            out["taxInformation"] = tax
        tins = tax.get("taxIdentificationNumbers")
        if not isinstance(tins, list):
            tins = []
            tax["taxIdentificationNumbers"] = tins
        while len(tins) < 3:
            tins.append({})
        slot = tins[2] if isinstance(tins[2], dict) else {}
        tins[2] = {**slot, "taxIdentificationNumber": pan_match.group(1).upper()}
        return out

    if len(trimmed) >= 2 and " " not in trimmed:
        return {**form_state, "tradingName": trimmed}

    return None


def plan_chat_turn(
    message: str,
    conversation_state: ConversationState,
    doc_availability: DocAvailability,
    country_code: str,
    form_state: dict[str, Any],
    quick_reply_id: str | None = None,
) -> ChatPlannerResponse:
    """Rule-based planner — gap analysis delegated to portal BFF when needed."""
    state = conversation_state
    doc_avail = doc_availability
    working = deepcopy(form_state)
    reply_id = quick_reply_id or message.lower().replace(" ", "_")
    lower = message.lower()

    if state == "intake":
        if reply_id == "docs_full" or "have document" in lower:
            return ChatPlannerResponse(
                reply="Great — upload your vendor documents (PAN, GST, cancelled cheque). I will extract and enrich automatically.",
                conversationState="collect_docs",
                uiAction="show_card",
                card="upload",
                branch="full_enrichment",
            )
        if reply_id == "docs_partial" or "partial" in lower:
            return ChatPlannerResponse(
                reply="Upload whatever you have — I will extract from those and ask for the rest conversationally.",
                conversationState="collect_docs",
                uiAction="show_card",
                card="upload",
                branch="partial_docs",
            )
        if reply_id == "docs_none" or "no document" in lower:
            return ChatPlannerResponse(
                reply="No problem. What is the vendor trading name?",
                conversationState="gap_fill",
                uiAction="ask_field",
                card="micro_form",
                gapField=GapField(path="tradingName", label="Trading name", kind="text"),
                branch="no_docs",
            )
        # Default new sessions to document upload; manual entry via skip / docs_none.
        return ChatPlannerResponse(
            reply="Upload your vendor documents (PAN, GST, cancelled cheque). I will extract and enrich automatically.",
            conversationState="collect_docs",
            uiAction="show_card",
            card="upload",
            branch="full_enrichment",
        )

    working = deepcopy(form_state)
    if state not in ("gap_fill",):
        patch = _patch_from_message(message, working)
        if patch:
            working = patch

    if state in ("gap_fill",) or (state == "collect_docs" and doc_avail == "none"):
        for field in PRIORITY_GAP_FIELDS:
            val = _read_path(working, field.path)
            if _is_empty(val):
                return ChatPlannerResponse(
                    reply=f"Please provide: {field.label}",
                    conversationState="gap_fill",
                    uiAction="ask_field",
                    card="micro_form",
                    gapField=field,
                )

        if _address_gap_needed(working):
            return ChatPlannerResponse(
                reply=f"Please provide: {ADDRESS_GAP_FIELD.label}",
                conversationState="gap_fill",
                uiAction="ask_field",
                card="micro_form",
                gapField=ADDRESS_GAP_FIELD,
            )

        return ChatPlannerResponse(
            reply="All required fields look good. Ready to create the prospect when you confirm.",
            conversationState="confirm_create",
            uiAction="show_card",
            card="confirm_action",
        )

    if state == "review":
        return ChatPlannerResponse(
            reply="Review the suggested fields in the card above, then apply selected values.",
            conversationState="review",
            uiAction="show_card",
            card="enrichment_review",
        )

    if state == "collect_docs" and doc_avail in ("full", "partial"):
        reply = (
            "Upload whatever you have — I will extract from those and ask for the rest conversationally."
            if doc_avail == "partial"
            else "Upload your vendor documents (PAN, GST, cancelled cheque). I will extract and enrich automatically."
        )
        return ChatPlannerResponse(
            reply=reply,
            conversationState="collect_docs",
            uiAction="show_card",
            card="upload",
        )

    if state == "enriching":
        return ChatPlannerResponse(
            reply="Enrichment is still running — check the progress card above.",
            conversationState="enriching",
            uiAction="show_card",
            card="progress",
        )

    return ChatPlannerResponse(
        reply="How can I help with this vendor onboarding?",
        conversationState=state,
    )


def _read_path(obj: Any, path: str) -> Any:
    current: Any = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            if not part.isdigit():
                return None
            index = int(part)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        if isinstance(current, dict):
            current = current.get(part)
            continue
        return None
    return current

