"""Access-policy proxy endpoints for portal and agent callers."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import require_service_bearer
from app.mdm.access_policy import (
    authorize_access,
    get_country_cluster_mappings,
    is_access_policy_configured,
    retrieve_access_policies,
    summarize_user_access,
)
from app.mdm.client import MdmApiError

router = APIRouter(
    prefix="/v1/access-policy",
    tags=["access-policy"],
    dependencies=[Depends(require_service_bearer)],
)


class PoliciesRequest(BaseModel):
    user: str
    relation: str | None = None
    object: str | None = Field(default=None, alias="object")
    sort_by: Literal["subject", "relation", "object"] | None = None
    sort_order: Literal["asc", "desc"] | None = None

    model_config = {"populate_by_name": True}


class AuthorizeRequest(BaseModel):
    user: str
    relation: str
    object: str


def _require_configured() -> None:
    if not is_access_policy_configured():
        raise HTTPException(
            status_code=503,
            detail="Access policy is not configured — set MDM_ACCESS_POLICY_OAUTH_* env vars.",
        )


@router.post("/policies")
async def policies_route(body: PoliciesRequest) -> dict[str, Any]:
    _require_configured()
    try:
        response = await retrieve_access_policies(
            user=body.user,
            relation=body.relation,
            object_id=body.object,
            sort_by=body.sort_by,
            sort_order=body.sort_order,
        )
    except MdmApiError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return summarize_user_access(body.user, response)


@router.post("/authorize")
async def authorize_route(body: AuthorizeRequest) -> dict[str, Any]:
    _require_configured()
    try:
        return await authorize_access(user=body.user, relation=body.relation, object_id=body.object)
    except MdmApiError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/country-cluster-mapping")
async def country_cluster_mapping_route(
    country_code: str | None = Query(default=None, alias="countryCode"),
    cluster_code: str | None = Query(default=None, alias="clusterCode"),
    region_code: str | None = Query(default=None, alias="regionCode"),
) -> list[dict[str, Any]]:
    _require_configured()
    try:
        return await get_country_cluster_mappings(
            country_code=country_code,
            cluster_code=cluster_code,
            region_code=region_code,
        )
    except MdmApiError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
