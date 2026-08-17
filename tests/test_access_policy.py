from __future__ import annotations

import pytest

from app.mdm.access_policy import (
    format_access_policy_user,
    parse_country_code_from_policy_object,
    summarize_user_access,
)


def test_format_access_policy_user_prefixes_email() -> None:
    assert format_access_policy_user("anil.k@maersk.com") == "user:anil.k@maersk.com"


def test_format_access_policy_user_keeps_prefix() -> None:
    assert format_access_policy_user("user:anil") == "user:anil"


def test_parse_country_code_from_policy_object() -> None:
    assert parse_country_code_from_policy_object("country:country_INDIA_IN") == "IN"


def test_summarize_user_access() -> None:
    response = {
        "clientId": "usrSettings",
        "version": "v1",
        "data": [
            {
                "user": "user:anil",
                "relation": "VmdRequester",
                "object": "country:country_INDIA_IN",
                "policy_condition": ["can_write"],
            },
            {
                "user": "user:anil",
                "relation": "VmdRequester",
                "object": "country:country_BANGLADESH_BG",
                "policy_condition": ["can_write", "can_edit"],
            },
        ],
    }
    summary = summarize_user_access("anil.k@maersk.com", response)
    assert summary["user"] == "user:anil.k@maersk.com"
    assert summary["relation"] == "VmdRequester"
    assert summary["countries"] == ["BG", "IN"]
    assert summary["policyConditions"] == ["can_edit", "can_write"]
