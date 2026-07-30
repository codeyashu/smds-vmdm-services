# Onboard orchestrator (services)

LangGraph-style enrichment graph in `app/onboard/graph.py` (deterministic v2).

## Tool → stage mapping (MCP gateway)

| Graph stage | MCP read tool | Portal BFF backing |
|---|---|---|
| `extract` | `map_extraction_results` (after in-process OCR) | `POST /api/onboard/internal/map-extraction` |
| `address_enrich` | `enrich_address` | `POST /api/addresses/enrich` |
| `registry` | `search_company_registry` | `GET /api/companies/search` |
| `duplicate_precheck` | `search_duplicates` | `POST /api/vendors/duplicates` |
| `build_plan` | `propose_vendor_patch` | `POST /api/onboard/internal/build-plan` |

Write tools (`apply_vendor_patch`, `create_prospect`, etc.) are **not** invoked by the graph — HITL writes stay in the portal.

## Environment

| Variable | Purpose |
|---|---|
| `VMDM_PORTAL_BFF_URL` | Portal base URL for BFF tool calls (default `http://localhost:3000`) |
| `ONBOARD_INTERNAL_SECRET` | Must match portal `ONBOARD_INTERNAL_SECRET` for internal routes |

## Readiness

`GET /v1/onboard/ready` returns `{ "status": "ok", "orchestratorVersion": 2 }` when the real graph is active.
