"""Customer Identity access-policy client (CDT api-cdt gateway)."""

from __future__ import annotations

from typing import Any

from app.mdm.auth import get_access_policy_token
from app.mdm.client import mdm_request_json
from app.mdm.config import get_mdm_settings


def format_access_policy_user(user: str) -> str:
    trimmed = user.strip()
    if not trimmed:
        return trimmed
    return trimmed if trimmed.startswith("user:") else f"user:{trimmed}"


def parse_country_code_from_policy_object(object_id: str) -> str | None:
    if len(object_id) >= 2 and object_id[-3] == "_":
        suffix = object_id[-2:]
        if suffix.isalpha() and suffix.isupper():
            return suffix
    return None


def is_access_policy_configured() -> bool:
    from app.mdm.config import get_mdm_settings_optional

    settings = get_mdm_settings_optional()
    return settings is not None and bool(settings.access_policy_oauth_client_id)


async def retrieve_access_policies(
    *,
    user: str | None = None,
    relation: str | None = None,
    object_id: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> dict[str, Any]:
    settings = get_mdm_settings()
    body: dict[str, Any] = {}
    if user:
        body["user"] = format_access_policy_user(user)
    if relation:
        body["relation"] = relation
    if object_id:
        body["object"] = object_id
    if sort_by:
        body["sort_by"] = sort_by
    if sort_order:
        body["sort_order"] = sort_order

    url = f"{settings.access_policy_base_url}/access/{settings.access_policy_client_id}/policies"
    token = await get_access_policy_token(settings)
    data = await mdm_request_json(
        url,
        token,
        method="POST",
        json_body=body,
        headers={"API-Version": "v1", "Consumer-Key": settings.access_policy_consumer_key},
        api_version="",
    )
    if not isinstance(data, dict):
        raise RuntimeError("unexpected access-policy policies response shape")
    return data


async def authorize_access(*, user: str, relation: str, object_id: str) -> dict[str, Any]:
    settings = get_mdm_settings()
    url = f"{settings.access_policy_base_url}/access/{settings.access_policy_client_id}/authorize"
    token = await get_access_policy_token(settings)
    data = await mdm_request_json(
        url,
        token,
        method="POST",
        json_body={
            "user": format_access_policy_user(user),
            "relation": relation,
            "object": object_id,
        },
        headers={"API-Version": "v1", "Consumer-Key": settings.access_policy_consumer_key},
        api_version="",
    )
    if not isinstance(data, dict):
        raise RuntimeError("unexpected access-policy authorize response shape")
    return data


async def get_country_cluster_mappings(
    *,
    country_code: str | None = None,
    cluster_code: str | None = None,
    region_code: str | None = None,
) -> list[dict[str, Any]]:
    settings = get_mdm_settings()
    params: list[str] = []
    if country_code:
        params.append(f"countryCode={country_code}")
    if cluster_code:
        params.append(f"clusterCode={cluster_code}")
    if region_code:
        params.append(f"regionCode={region_code}")
    query = f"?{'&'.join(params)}" if params else ""
    url = f"{settings.access_policy_base_url}/country-cluster-mapping{query}"
    token = await get_access_policy_token(settings)
    data = await mdm_request_json(
        url,
        token,
        method="GET",
        headers={"API-Version": "v1", "Consumer-Key": settings.access_policy_consumer_key},
        api_version="",
    )
    if not isinstance(data, list):
        raise RuntimeError("unexpected country-cluster-mapping response shape")
    return data


def summarize_user_access(user_email: str, response: dict[str, Any]) -> dict[str, Any]:
    policies = response.get("data") if isinstance(response.get("data"), list) else []
    countries: set[str] = set()
    objects: set[str] = set()
    policy_conditions: set[str] = set()
    relation = ""
    if policies and isinstance(policies[0], dict):
        relation = str(policies[0].get("relation") or "")

    for policy in policies:
        if not isinstance(policy, dict):
            continue
        object_id = str(policy.get("object") or "")
        if object_id:
            objects.add(object_id)
        country = parse_country_code_from_policy_object(object_id)
        if country:
            countries.add(country)
        conditions = policy.get("policy_condition")
        if isinstance(conditions, list):
            for condition in conditions:
                policy_conditions.add(str(condition))

    return {
        "user": format_access_policy_user(user_email),
        "relation": relation,
        "countries": sorted(countries),
        "objects": sorted(objects),
        "policyConditions": sorted(policy_conditions),
        "policies": policies,
    }
