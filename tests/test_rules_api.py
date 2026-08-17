"""End-to-end check of the /v1/rules router: import a fixture into the (isolated) store,
then hit the endpoints a real caller would — ``compiled`` (the compat projection the
portal's source facade will call in phase 2) and ``simulate`` (the shadow-diff/authoring
primitive)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.rules.importer import import_from_mdm_response
from app.rules.store import save_country_ruleset

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "rules"


def _import_fixture(name: str) -> dict:
    mdm_response = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    ruleset = import_from_mdm_response(mdm_response)
    save_country_ruleset(ruleset)
    return mdm_response


def test_compiled_endpoint_reproduces_the_import(monkeypatch):
    mdm_response = _import_fixture("br-prospect-vendor.json")
    client = TestClient(app)

    resp = client.get("/v1/rules/BR/compiled")
    assert resp.status_code == 200
    body = resp.json()

    assert body["ledger"] == []
    assert body["excludedInactiveCount"] == 0
    assert {"iso2CountryCode": body["iso2CountryCode"], "vendorStatusReason": body["vendorStatusReason"],
            "rules": body["rules"]} == mdm_response


def test_compiled_endpoint_404_for_unimported_country():
    client = TestClient(app)
    resp = client.get("/v1/rules/ZZ/compiled")
    assert resp.status_code == 404


def test_simulate_reflects_a_conditional_dependency():
    _import_fixture("br-prospect-vendor.json")
    client = TestClient(app)

    resp = client.post("/v1/rules/simulate", json={
        "country": "BR",
        "payload": {"vendorGroupType": "ZINT"},
    })
    assert resp.status_code == 200
    fields = {f["path"]: f for f in resp.json()["fields"]}
    assert fields["tradingPartnerCode"]["isRequired"] is True
    assert "br.vendor-core-details.vendorgrouptype" in fields["tradingPartnerCode"]["contributingRuleIds"]


def test_countries_endpoint_lists_imported_countries():
    _import_fixture("br-prospect-vendor.json")
    _import_fixture("in-prospect-vendor.json")
    client = TestClient(app)
    resp = client.get("/v1/rules/countries")
    assert resp.status_code == 200
    assert set(resp.json()["countries"]) == {"BR", "IN"}
