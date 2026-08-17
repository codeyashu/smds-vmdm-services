"""Bank master IFSC lookup — port of portal resolve-bank-from-ifsc."""

from __future__ import annotations

import os
from typing import Any

from app.mdm.auth import get_mdm_token
from app.mdm.client import mdm_request_json


def _bank_base_url() -> str:
    default = "https://smds-bank-master-cdt.maersk-digital.net/global-mdm"
    return (os.getenv("MDM_BANK_MASTER_BASE_URL") or default).rstrip("/")


def _bank_consumer_key() -> str:
    return os.getenv("MDM_BANK_MASTER_CONSUMER_KEY") or os.getenv("MDM_OAUTH_CLIENT_ID") or ""


def _map_bank_detail(bank: dict[str, Any]) -> dict[str, str] | None:
    code = str(bank.get("bankNumber") or "").strip()
    if not code:
        return None
    out: dict[str, str] = {"bankingInstitutionCode": code}
    if bank.get("bankName"):
        out["bankName"] = str(bank["bankName"])
    if bank.get("swiftCode"):
        out["swiftCode"] = str(bank["swiftCode"])
    if bank.get("bankBranchName"):
        out["bankBranchName"] = str(bank["bankBranchName"])
    if bank.get("bankISOCountryCode"):
        out["iso2CountryCode"] = str(bank["bankISOCountryCode"])
    return out


async def resolve_bank_from_ifsc(country_code: str, ifsc: str) -> dict[str, str] | None:
    normalized = ifsc.strip().upper()
    if not normalized:
        return None

    token = await get_mdm_token()
    params = f"top=5&bankNumber={normalized}&bankISOCountryCode={country_code.upper()}"
    url = f"{_bank_base_url()}/bank-master?{params}"
    data = await mdm_request_json(
        url,
        token,
        headers={"Consumer-Key": _bank_consumer_key()},
    )
    raw_details = data.get("bankDetails") if isinstance(data, dict) else None
    if not isinstance(raw_details, list):
        raw_details = [raw_details] if isinstance(raw_details, dict) else []

    matches = [row for row in raw_details if isinstance(row, dict) and not row.get("deletionMark")]
    if len(matches) == 1:
        return _map_bank_detail(matches[0])

    exact = [
        row
        for row in matches
        if str(row.get("bankNumber") or "").strip().upper() == normalized
    ]
    if len(exact) == 1:
        return _map_bank_detail(exact[0])
    return None
