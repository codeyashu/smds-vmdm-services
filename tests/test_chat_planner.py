"""Tests for deterministic chat planner."""

from app.onboard.chat_planner import plan_chat_turn


def test_intake_docs_full():
    result = plan_chat_turn("", "intake", "none", "IN", {}, quick_reply_id="docs_full")
    assert result.conversationState == "collect_docs"
    assert result.card == "upload"


def test_intake_defaults_to_collect_docs():
    result = plan_chat_turn("", "intake", "none", "IN", {})
    assert result.conversationState == "collect_docs"
    assert result.card == "upload"
    assert result.branch == "full_enrichment"


def test_intake_docs_none():
    result = plan_chat_turn("", "intake", "none", "IN", {}, quick_reply_id="docs_none")
    assert result.conversationState == "gap_fill"
    assert result.gapField is not None
    assert result.gapField.path == "tradingName"


def test_gap_fill_groups_city_and_postal():
    result = plan_chat_turn(
        "",
        "gap_fill",
        "none",
        "IN",
        {
            "tradingName": "Acme Pvt Ltd",
            "vendorGroupType": "ZEXT",
            "postalAddresses": [{"postalCode": "641652"}],
        },
    )
    assert result.gapField is not None
    assert result.gapField.path == "postalAddresses.0.cityName"
    assert result.gapField.label == "City and postal code"
    assert "City and postal code" in result.reply


def test_gap_fill_reads_nested_pan_path():
    result = plan_chat_turn(
        "CDHSP3378H",
        "gap_fill",
        "none",
        "IN",
        {
            "tradingName": "Acme Pvt Ltd",
            "vendorGroupType": "ZEXT",
            "taxInformation": {
                "taxIdentificationNumbers": [{}, {}, {"taxIdentificationNumber": "CDHSP3378H"}],
            },
            "postalAddresses": [{"cityName": "Mumbai", "postalCode": "400001"}],
        },
    )
    assert result.conversationState == "confirm_create"
    assert result.card == "confirm_action"
