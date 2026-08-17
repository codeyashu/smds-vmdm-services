"""Document apply-patches API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import require_service_bearer
from app.documents.apply_patches import apply_document_options

router = APIRouter(prefix="/v1", tags=["documents"])


class ApplyOption(BaseModel):
    path: str
    label: str
    incoming_value: Any = Field(alias="incomingValue")
    source_doc_type: str | None = Field(default=None, alias="sourceDocType")
    source_doc_type_label: str | None = Field(default=None, alias="sourceDocTypeLabel")
    needs_resolution: str | None = Field(default=None, alias="needsResolution")

    model_config = {"populate_by_name": True}


class ApplyPatchesRequest(BaseModel):
    country_code: str = Field(alias="countryCode")
    form_state: dict[str, Any] = Field(default_factory=dict, alias="formState")
    selected: list[ApplyOption]
    remap_path: Literal["edit_bank_accounts"] | None = Field(default=None, alias="remapPath")

    model_config = {"populate_by_name": True}


@router.post("/documents/apply-patches", dependencies=[Depends(require_service_bearer)])
async def apply_patches_route(body: ApplyPatchesRequest) -> dict[str, Any]:
    selected = [opt.model_dump(by_alias=True) for opt in body.selected]
    return await apply_document_options(
        body.form_state,
        selected,
        country_code=body.country_code,
        remap_path=body.remap_path,
    )
