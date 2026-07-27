# smds-vmdm-services

Backend for the Maersk vendor MDM portal (`smds-vmdmportal`). The portal's own Next.js API
routes are its BFF layer (see `smds-vmdmportal`'s ADR 0001); this repo is a downstream service
that BFF proxies to for logic too heavy or too AI-heavy to live in the portal itself: document
upload & auto-extraction (India first) — accepts a PAN card, GST certificate, cancelled cheque,
etc., and returns portal-shaped field patches for the steward to review in the existing
Current-vs-Incoming field picker — plus company-search and natural-language-search LLM assist
(address/name/tax normalization, term expansion, match adjudication, semantic similarity, query
parsing) migrated out of the portal. The repo name is deliberately generic (not `ai-services` or
`docai-only`) so both AI-backed capabilities and plain business logic for the portal land here
too, sharing the same provider layer, auth, and deploy pipeline instead of each spinning up its
own service.

Uploaded files are **ephemeral**: held in memory for the request only, deleted after, never
persisted. These documents carry PAN / GSTIN / bank-account PII.

## Providers — Azure by default, free ones available if ever needed

Every AI/OCR call goes through a provider interface, chosen by env var. **Azure is the primary
path**: set the Azure creds below and nothing else — both factories auto-detect them and select
Azure Document Intelligence + Azure OpenAI with no `DOCAI_*_PROVIDER` override required.

```bash
DOCAI_DI_ENDPOINT=https://<resource>.cognitiveservices.azure.com
DOCAI_DI_KEY=<key>
DOCAI_AOAI_ENDPOINT=https://<resource>.openai.azure.com
DOCAI_AOAI_KEY=<key>
DOCAI_AOAI_DEPLOYMENT=gpt-4o     # your vision-capable deployment name
```

That's the whole setup — `DOCAI_OCR_PROVIDER`/`DOCAI_LLM_PROVIDER` default to `auto`, which
picks Azure whenever these are present. With zero config, extraction reports `503` rather than
silently falling back to anything.

| | Provider | Notes |
|---|---|---|
| **OCR / layout** | Azure Document Intelligence | Best layout fidelity + native word bounding boxes. Has an F0 free tier (~500 pages/month) if cost matters during dev. |
| **LLM (semantic mapping)** | Azure OpenAI | Reuse the same tenant credentials as the portal. Needs a vision-capable deployment (e.g. `gpt-4o`) since cheques/stamped certs are sent as page images. |

### Free/local alternatives (optional — not needed if you're on Azure)

The provider interfaces also support a fully free, offline stack (PyMuPDF for text, Ollama for
the LLM) plus hosted free tiers (Gemini, Groq) — useful for local dev without Azure access, or
if Azure quota/cost ever becomes a constraint. None of these activate automatically; each needs
an explicit `DOCAI_OCR_PROVIDER`/`DOCAI_LLM_PROVIDER` value or provider-specific env var:

```bash
DOCAI_OCR_PROVIDER=pymupdf|tesseract
DOCAI_LLM_PROVIDER=ollama|gemini|groq|none
```

See `app/providers/llm/factory.py` and `app/providers/ocr/factory.py` for the full option list.

## Layout

```
app/
├─ core/                 # config (env-driven Settings), structured logging (PII-redacting)
├─ providers/
│  ├─ llm/               # base.py (Protocol), openai_compatible.py (works for OpenAI/Azure/
│  │                      #   Ollama/Gemini/Groq — same wire shape), azure-specific routing
│  │                      #   in factory.py, factory.py (env -> provider)
│  └─ ocr/                # base.py (Protocol), pymupdf_text.py (free), tesseract.py (free),
│                          #   azure_di.py (paid), factory.py (env -> provider)
├─ documents/             # the document-extraction capability, built on the providers above
│  ├─ rules/              # in_patterns.py (PAN/GSTIN/IFSC regex, state->region table),
│  │                      #   crosscheck.py (deterministic consistency checks)
│  ├─ mapping/            # field_paths.py (doc field -> portal form path + regex gate),
│  │                      #   to_patches.py (extraction -> portal Patch objects)
│  ├─ extract/schemas/india/  # per-doctype pydantic extraction schemas
│  ├─ classify/           # keyword-anchor doc-type classifier
│  └─ ingestion/          # upload validation (MIME allowlist, size cap, magic-byte sniff)
└─ api/v1/                # FastAPI routes: POST /v1/extract, GET /v1/doctypes

# Future AI capabilities for the portal live as siblings of `documents/`, reusing
# `providers/llm` and `providers/ocr` rather than each owning a provider integration.
```

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload
```

`GET /health` — liveness. `GET /ready` — reports which OCR/LLM provider (if any) is active
and whether extraction is currently available.

## Test

The whole pure surface — cross-checks, mapping, regex gate, classification, upload
validation, provider selection, API boot — runs with **zero configuration, zero network**:

```bash
uv run pytest -q
```

## Config reference

All settings are prefixed `DOCAI_` (pydantic-settings, `.env` supported). Copy `.env.example` → `.env` to start.

```
DOCAI_OCR_PROVIDER=auto|azure_di|pymupdf|tesseract   # auto = azure_di when DI creds present
DOCAI_LLM_PROVIDER=auto|azure|openai|gemini|groq|ollama|none  # auto = azure when AOAI creds present

# Azure Document Intelligence
DOCAI_DI_ENDPOINT=   DOCAI_DI_KEY=   DOCAI_DI_MODEL=prebuilt-layout

# Azure OpenAI
DOCAI_AOAI_ENDPOINT=  DOCAI_AOAI_KEY=  DOCAI_AOAI_DEPLOYMENT=gpt-4o

# Free local LLM (opt-in: DOCAI_LLM_PROVIDER=ollama, or set either var below)
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1   OLLAMA_MODEL=llama3.2-vision

# Free hosted LLM tiers (DOCAI_LLM_PROVIDER=gemini|groq)
GEMINI_API_KEY=   GROQ_API_KEY=

DOCAI_SERVICE_BEARER_TOKEN=   # token the portal BFF presents; unset disables auth (dev only)
DOCAI_MAX_FILE_BYTES=10485760   DOCAI_MAX_PAGES=20   DOCAI_MAX_BATCH_FILES=5
```

Install: `uv sync` covers the default Azure path. `uv sync --extra tesseract` only if you opt
into local OCR (also needs the system `tesseract` binary).

## Document requirements rule engine

`GET /v1/doc-requirements?country=IN` lists which document types a country expects (mandatory
vs optional) — this is what backs `GET /v1/doctypes` and the portal's requirements checklist.
Writes (`POST`/`PUT`/`DELETE /v1/doc-requirements[/{id}]`) are gated by
`DOCAI_SERVICE_BEARER_TOKEN` when one is set; open otherwise (dev only).

Backed by SQLite at `DOCAI_DB_PATH` (default `./data/docai.db`), seeded on first run with
India's defaults: PAN card, GST certificate, and cancelled cheque are mandatory; Udyam
certificate and Certificate of Incorporation are optional. This store holds document *type*
configuration only — never an uploaded document's bytes, which stay ephemeral as documented
above.

## Status

Extraction pipeline is wired end to end: `POST /v1/extract` runs OCR -> a single classify+extract
LLM call -> deterministic cross-checks -> portal-shaped patches, against real Azure DI + Azure
OpenAI (or any configured provider). Accepts PDF, JPEG, PNG, and DOCX. The document-requirements
rule engine (SQLite + CRUD API) is live and seeded for India. Portal-side wiring (upload UI,
apply-to-form, drift detection, requirements admin screen) is a separate plan in the
`smds-vmdmportal` repo.
