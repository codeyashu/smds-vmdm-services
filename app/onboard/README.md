# Onboard orchestrator (services brain)

Deterministic enrichment stage pipeline in `app/onboard/graph.py`.

## Stages

| Stage | Implementation |
|---|---|
| `extract` | In-process `run_extraction` + `extraction_mapping` |
| `address_enrich` | Portal BFF `POST /api/addresses/enrich` (MDM proxy transition) |
| `registry` | Portal BFF `GET /api/companies/search` |
| `duplicate_precheck` | Portal BFF `POST /api/vendors/duplicates` |
| `build_plan` | In-process `enrichment_merge.merge_enrichment_plan` |

Chat planner: `app/onboard/chat_planner.py` (+ optional Pydantic AI via `DOCAI_ONBOARD_CHAT_LLM=true`).

## Environment

| Variable | Purpose |
|---|---|
| `VMDM_PORTAL_BFF_URL` | Portal base for enrich/registry/duplicate BFF calls |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Optional LLM tracing |
| `DOCAI_ONBOARD_CHAT_LLM` | Enable Pydantic AI chat planner |

## Readiness

`GET /v1/onboard/ready` returns `{ "status": "ok", "orchestratorVersion": 2 }`.
