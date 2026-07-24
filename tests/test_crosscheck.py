"""Pure cross-check tests — must pass with zero Azure configuration."""

from __future__ import annotations

from app.documents.rules import crosscheck as cc
from app.documents.rules.in_patterns import (
    is_natural_person,
    pan_from_gstin,
    region_for_gstin,
)

# A self-consistent Maharashtra example: GSTIN embeds PAN AABCA1234F, state 27 -> MH.
GSTIN_MH = "27AABCA1234F1Z5"
PAN_CO = "AABCA1234F"   # 4th char C -> company
PAN_INDIV = "AABPA1234F"  # 4th char P -> individual


def test_pan_from_gstin_extracts_embedded_pan():
    assert pan_from_gstin(GSTIN_MH) == PAN_CO


def test_region_for_gstin_maps_state_code():
    assert region_for_gstin(GSTIN_MH) == "MH"
    assert region_for_gstin("29ABCDE1234F1Z5") == "KA"
    assert region_for_gstin("07ABCDE1234F1Z5") == "DL"


def test_is_natural_person_from_pan_4th_char():
    assert is_natural_person(PAN_INDIV) is True
    assert is_natural_person(PAN_CO) is False
    assert is_natural_person("BADPAN") is None


def test_gstin_contains_pan_pass_and_fail():
    assert cc.check_gstin_contains_pan(GSTIN_MH, PAN_CO).status == "pass"
    fail = cc.check_gstin_contains_pan(GSTIN_MH, "ZZZZZ9999Z")
    assert fail.status == "fail"


def test_gstin_state_vs_region_warns_on_mismatch():
    assert cc.check_gstin_state_vs_region(GSTIN_MH, "MH").status == "pass"
    assert cc.check_gstin_state_vs_region(GSTIN_MH, "KA").status == "warn"


def test_ifsc_shape():
    assert cc.check_ifsc_shape("HDFC0001234").status == "pass"
    assert cc.check_ifsc_shape("HDFCX001234").status == "fail"  # 5th char must be 0


def test_pan_entity_type_warns_on_conflict():
    # PAN says company (False); context claims natural person (True) -> warn.
    assert cc.check_pan_entity_type(PAN_CO, True).status == "warn"
    assert cc.check_pan_entity_type(PAN_CO, False).status == "pass"


def test_run_all_drops_skips_and_flags_blocking_failure():
    ident = cc.ExtractedIdentity(pan="ZZZZZ9999Z", gstin=GSTIN_MH, region_code="MH")
    results = cc.run_all(ident)
    ids = {c.id for c in results}
    assert "ifsc_shape" not in ids  # skipped, no IFSC given
    assert cc.has_blocking_failure(results) is True  # PAN doesn't match GSTIN's embedded PAN


def test_case_and_whitespace_insensitive():
    assert cc.check_gstin_contains_pan(" 27aabca1234f1z5 ", "aabca1234f").status == "pass"
