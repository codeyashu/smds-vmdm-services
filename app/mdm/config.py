"""MDM environment — mirrors portal `src/lib/mdm/env.ts` keys."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_COMPANY_SEARCH_BASE_URL = (
    "https://smds-company-external-search-cdt.maersk-digital.net/global-mdm"
)
DEFAULT_EXTERNAL_SERVICE_BASE_URL = (
    "https://smds-cmd-external-cdt.maersk-digital.net/global-mdm"
)
DEFAULT_ACCESS_POLICY_BASE_URL = "https://api-cdt.maersk.com/customer-identity/access-policy"
DEFAULT_ACCESS_POLICY_CLIENT_ID = "usrSettings"

REQUIRED_KEYS = (
    "MDM_OAUTH_TOKEN_URL",
    "MDM_OAUTH_CLIENT_ID",
    "MDM_OAUTH_CLIENT_SECRET",
    "MDM_VENDOR_SEARCH_BASE_URL",
)


@dataclass(frozen=True)
class MdmSettings:
    oauth_token_url: str
    oauth_client_id: str
    oauth_client_secret: str
    vendor_search_base_url: str
    vendor_reference_base_url: str | None
    vendor_ingestion_base_url: str | None
    company_search_base_url: str
    company_search_consumer_key: str
    company_search_oauth_client_id: str
    company_search_oauth_client_secret: str
    external_service_base_url: str
    external_service_consumer_key: str
    access_policy_base_url: str
    access_policy_client_id: str
    access_policy_oauth_client_id: str
    access_policy_oauth_client_secret: str
    access_policy_consumer_key: str


@lru_cache
def get_mdm_settings() -> MdmSettings:
    missing = [key for key in REQUIRED_KEYS if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing MDM env: {', '.join(missing)}")

    oauth_client_id = os.environ["MDM_OAUTH_CLIENT_ID"]
    oauth_secret = os.environ["MDM_OAUTH_CLIENT_SECRET"]

    return MdmSettings(
        oauth_token_url=os.environ["MDM_OAUTH_TOKEN_URL"],
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_secret,
        vendor_search_base_url=os.environ["MDM_VENDOR_SEARCH_BASE_URL"].rstrip("/"),
        vendor_reference_base_url=(os.getenv("MDM_VENDOR_REFERENCE_BASE_URL") or "").rstrip("/") or None,
        # Same key the portal reads for `getValidationRules` (`src/lib/mdm/env.ts`,
        # `MDM_VENDOR_INGESTION_BASE_URL`) — optional here too, since the rules importer
        # is the only phase-1 consumer and every other MDM capability works without it.
        vendor_ingestion_base_url=(os.getenv("MDM_VENDOR_INGESTION_BASE_URL") or "").rstrip("/") or None,
        company_search_base_url=(
            os.getenv("MDM_COMPANY_SEARCH_BASE_URL") or DEFAULT_COMPANY_SEARCH_BASE_URL
        ).rstrip("/"),
        company_search_consumer_key=(
            os.getenv("MDM_COMPANY_SEARCH_CONSUMER_KEY")
            or os.getenv("MDM_COMPANY_SEARCH_OAUTH_CLIENT_ID")
            or oauth_client_id
        ),
        company_search_oauth_client_id=os.getenv("MDM_COMPANY_SEARCH_OAUTH_CLIENT_ID") or oauth_client_id,
        company_search_oauth_client_secret=os.getenv("MDM_COMPANY_SEARCH_OAUTH_CLIENT_SECRET")
        or oauth_secret,
        external_service_base_url=(
            os.getenv("MDM_EXTERNAL_SERVICE_BASE_URL") or DEFAULT_EXTERNAL_SERVICE_BASE_URL
        ).rstrip("/"),
        external_service_consumer_key=os.getenv("MDM_EXTERNAL_SERVICE_CONSUMER_KEY") or oauth_client_id,
        access_policy_base_url=(
            os.getenv("MDM_ACCESS_POLICY_BASE_URL") or DEFAULT_ACCESS_POLICY_BASE_URL
        ).rstrip("/"),
        access_policy_client_id=os.getenv("MDM_ACCESS_POLICY_CLIENT_ID") or DEFAULT_ACCESS_POLICY_CLIENT_ID,
        access_policy_oauth_client_id=os.getenv("MDM_ACCESS_POLICY_OAUTH_CLIENT_ID") or oauth_client_id,
        access_policy_oauth_client_secret=os.getenv("MDM_ACCESS_POLICY_OAUTH_CLIENT_SECRET")
        or oauth_secret,
        access_policy_consumer_key=os.getenv("MDM_ACCESS_POLICY_CONSUMER_KEY") or oauth_client_id,
    )


def is_mdm_configured() -> bool:
    return all(os.getenv(key) for key in REQUIRED_KEYS)


def get_mdm_settings_optional() -> MdmSettings | None:
    if not is_mdm_configured():
        return None
    return get_mdm_settings()
