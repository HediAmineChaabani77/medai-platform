# MedAI Assistant Platform

Hybrid local/cloud clinical assistant for practicing physicians. Supports
four use cases: diagnostic assistance (UC1), automated structured report
generation (UC2), prescription safety checks (UC3), and admin monitoring (UC4).

Designed for HIPAA/GDPR scope, with:
- Rule-based local/cloud router (no RL, no learned policy)
- Fully offline-capable RAG via local Qdrant + local Ollama embeddings
- Append-only HMAC-chained audit log
- Pluggable cloud LLM provider (OpenAI-compatible API shape)

This repository is bootstrapped for **local-only** operation. The cloud
provider is wired but not required for the platform to function.

---

## Prerequisites

- Docker and Docker Compose
- Ollama models pulled once on the host:
  ```bash
  docker compose up -d ollama
  docker compose exec ollama ollama pull llama3.1:8b-instruct
  docker compose exec ollama ollama pull nomic-embed-text
  ```

Python 3.11 and Node 20 are only required if you want to run tests or the
frontend outside containers.

## Quickstart

```bash
cp backend/.env.example backend/.env
# Edit only if you need non-defaults. FORCE_LOCAL_ONLY=true is set by default.

docker compose up --build
```

Services:

| Service  | URL                        | Purpose                     |
|----------|----------------------------|-----------------------------|
| backend  | http://localhost:8000      | FastAPI API + OpenAPI docs  |
| frontend | http://localhost:3000      | Next.js UI                  |
| qdrant   | http://localhost:6333      | Vector store                |
| ollama   | http://localhost:11434     | Local LLM + embeddings      |
| postgres | localhost:5432             | Audit + feedback + drugs    |

Seed the knowledge base (runs inside a Python environment with access to
Ollama; from the backend container):

```bash
docker compose exec backend python /app/data/../../../ingestion/ingest_guidelines.py
docker compose exec backend python /app/data/../../../ingestion/ingest_vidal.py
docker compose exec backend python /app/data/../../../ingestion/ingest_drugbank.py
```

Or, simpler, from the host with Python available:

```bash
python ingestion/ingest_guidelines.py
python ingestion/ingest_vidal.py
python ingestion/ingest_drugbank.py
```

Smoke-test the local LLM:

```bash
docker compose exec backend python scripts/smoke_llm.py
```

## Environment variables

See `backend/.env.example`. Key groups:

- `OLLAMA_HOST`, `LLM_LOCAL_MODEL`, `LLM_EMBED_MODEL` — local stack
- `LLM_CLOUD_PROVIDER`, `LLM_CLOUD_MODEL`, `LLM_CLOUD_BASE_URL`, `LLM_CLOUD_API_KEY` — cloud
- `FORCE_LOCAL_ONLY=true` — disables cloud routing entirely (default)
- `QDRANT_URL`, `QDRANT_COLLECTION` — RAG
- `AUDIT_HMAC_KEY` — audit chain signing key
- `CONNECTIVITY_PROBE_URL`, `CONNECTIVITY_PROBE_INTERVAL` — offline detector

## Swapping the cloud provider

`CloudProvider` calls the `/chat/completions` shape (OpenAI-compatible). Any
OpenAI-compatible endpoint works with zero code changes:

- OpenAI: `LLM_CLOUD_BASE_URL=https://api.openai.com/v1`
- Azure OpenAI: `https://{resource}.openai.azure.com/openai/deployments/{deployment}` plus API-version route
- Mistral La Plateforme: `https://api.mistral.ai/v1`
- Anthropic via a compatibility gateway (e.g. LiteLLM proxy): the proxy URL
- Self-hosted vLLM / TGI with OpenAI-compatible server: its URL

Set `LLM_CLOUD_PROVIDER` to any label (used for logging/metrics only) and
flip `FORCE_LOCAL_ONLY=false`.

## Adding ingestion sources

The ingestion scripts live in `ingestion/`. The shared helper is
`ingestion/_common.py`, which:

1. Parses markdown into sections
2. Chunks each section (512 tokens, 64 overlap) with the section header preserved
3. Embeds via local Ollama (`nomic-embed-text`)
4. Upserts into the Qdrant `medai_knowledge` collection

To add a new corpus: drop markdown files into
`backend/data/knowledge_base/` and add a one-liner script that calls
`run(source_label="...", glob_pattern="...")`. For structured data
(DrugBank), follow `ingestion/ingest_drugbank.py` — it writes to Postgres
directly.

## Routing rules

Rules are evaluated first-match-wins. See
`backend/app/core/router.py` for the implementation and
`backend/tests/test_router.py` for one test per rule.

| Order | Rule | Target | Reason |
|------:|------|--------|--------|
| 0 | `FORCE_LOCAL_ONLY=true` | local | Operator flag (bring-up) |
| 1 | Offline | local | Network probe failed |
| 2 | High-sensitivity PHI match | local | Rare disease / genetic / psychiatric / HIV |
| 3 | `UC3_PRESCRIPTION` | local | Prescription safety is always local |
| 4 | Admin override in `routing_policies` | local/cloud | Per (use_case, department) |
| 5 | Text > 8000 chars or hospitalization/operative report | cloud | Complexity |
| 6 | Local queue depth > threshold | cloud | Load shedding |
| 7 | Default | cloud | Quality fallback |

## Use cases — API

- UC1: `POST /api/uc1/diagnose` → differential diagnosis list, citations, red flags
- UC1 feedback: `POST /api/uc1/feedback`
- UC2: `POST /api/uc2/generate` → structured markdown + HMAC signature
- UC2 Whisper: `POST /api/uc2/transcribe` (multipart audio file)
- UC3: `POST /api/uc3/check` → interaction alerts; returns HTTP 409 if a `major` alert blocks
- UC4: `GET /api/admin/metrics`, `GET /api/admin/audit`, `GET /api/admin/audit/verify`,
  `GET|POST|DELETE /api/admin/routing-policies`, `GET /api/admin/models`,
  `POST /api/admin/rl/train` → HTTP 501 (reserved for future sprint)

OpenAPI docs: http://localhost:8000/docs

## Running tests

```bash
docker compose exec backend pytest -q
```

Coverage target: ≥ 75% on `app/core/` and `app/services/`.

## HIPAA / GDPR compliance notes

- Raw patient identifiers NEVER leave the backend. All audit logs store
  `SHA-256(patient_id)` only (`app/core/audit.py::hash_patient_id`).
- Embeddings are always computed locally via Ollama. No text leaves the
  host for embedding, by design (`CloudProvider.embed` raises).
- When offline, the full UC1/UC2/UC3 workflow remains functional
  (`tests/test_offline_mode.py`).
- Routing rule 2 routes any payload containing high-sensitivity topics
  (HIV, genetic markers, psychiatric diagnoses, rare-disease ICD-10 codes)
  to the local provider regardless of other rules.
- Audit log is append-only with per-row HMAC chaining to the previous row's
  hash. `GET /api/admin/audit/verify` replays the chain and returns the
  first broken row id on tampering.
- Every LLM call passes through `LLMDispatcher.run`, which emits exactly
  one audit row. Direct provider calls from services are not permitted.
- Prescription safety (UC3) is always local (`R3_PRESCRIPTION`) and never
  sends medication lists to a cloud provider.

## What is NOT in this build

- **Reinforcement learning** — the routing policy is pure rules. The RL
  endpoint is scaffolded at `POST /api/admin/rl/train` but returns HTTP 501.
  Feedback rows and metrics tables are collected for a future RL sprint
  but no training loop exists.
- **Real EMR/DPI integration** — no HL7 FHIR client, no DMP API, no
  hospital directory integration. The `PatientProfile` schema is a local
  structure; wiring to a real EMR is a separate sprint.
- **Multi-tenant isolation** — single-tenant schema. No per-hospital
  database partitioning or RLS policies.
- **Real Vidal / DrugBank data** — a small synthetic sample is bundled
  (`backend/data/knowledge_base/drug_*.md`,
  `drug_interactions.csv`). Production use requires a commercial license.
- **Additional authentication providers** — only credentials + TOTP are
  planned. No SSO, SAML, or OIDC integration.
- **Country-specific PHI patterns beyond France** — the regex list
  (NIR, INSEE, FR phone) is French. Adding other locales is a
  `phi_detector.py` + YAML change but a scoped sprint.

## Project layout

```
medai-platform/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI entry
│   │   ├── config.py          Pydantic settings
│   │   ├── db.py              SQLAlchemy engine
│   │   ├── deps.py            FastAPI dependency wiring
│   │   ├── core/
│   │   │   ├── connectivity.py   Online/offline probe
│   │   │   ├── llm_provider.py   Ollama + OpenAI-compatible cloud
│   │   │   ├── phi_detector.py   Regex + spaCy + YAML keywords
│   │   │   ├── router.py         7-rule first-match-wins
│   │   │   ├── rag.py            Qdrant dense + BM25 + RRF
│   │   │   ├── audit.py          HMAC-chained append-only log
│   │   │   └── dispatcher.py     Router + RAG + audit glue
│   │   ├── models/            SQLAlchemy ORM (audit, drug, feedback, policy, user)
│   │   ├── schemas/           Pydantic request/response models
│   │   ├── services/          UC1–UC4 business logic
│   │   └── routes/            FastAPI routers
│   ├── data/
│   │   ├── knowledge_base/    Seed markdown + drug interactions CSV
│   │   └── vector_store/      Qdrant persistence volume
│   ├── scripts/
│   │   └── smoke_llm.py       Light end-to-end Ollama test
│   ├── tests/                 pytest suite
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                  Next.js 14 + Tailwind UI
│   ├── app/
│   │   ├── diagnostic/        UC1
│   │   ├── report/            UC2
│   │   ├── prescription/      UC3
│   │   ├── admin/             UC4
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   ├── lib/
│   └── Dockerfile
├── ingestion/                 Knowledge-base seeding scripts
│   ├── _common.py
│   ├── ingest_guidelines.py
│   ├── ingest_vidal.py
│   └── ingest_drugbank.py
└── docker-compose.yml
```
