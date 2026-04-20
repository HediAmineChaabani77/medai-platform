# Datasets used by MedAI Assistant (QA mode)

## Active dataset (only one)

### `medical_qa.json`

- **Source file**: `C:/Users/MSI/Documents/Med_LLM/medical_qa.json`
- **WSL path**: `/mnt/c/Users/MSI/Documents/Med_LLM/medical_qa.json`
- **Purpose**: the **only** corpus used by the QA RAG pipeline.
- **Loaded into**: Qdrant collection `medical_qa_only`
- **Ingestion script**: `ingestion/ingest_medical_qa.py`

## Current policy

- RAG retrieval for `/api/qa/ask` must use only chunks coming from `medical_qa.json`.
- The ingestion script clears the target collection before indexing, so old corpora are removed from retrieval scope.
- QA responses are grounded on retrieved snippets and include citations metadata.
- No other local corpus is kept under `backend/data` (DMP/DPI files are optional and configured outside this directory).

## How to run (WSL)

```bash
# 1) Start services (Postgres, Qdrant, backend, frontend)
docker compose up -d --build

# 2) Ingest only the QA dataset

docker compose exec -T backend python /app/ingestion/ingest_medical_qa.py

# 3) Ask a question
curl -sS -X POST http://localhost:8001/api/qa/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What are common symptoms of diabetes?"}'
```

## Chunking approach

- Chunk unit: one QA pair (`Category + Question + Answer`)
- Default chunk size: ~180 tokens
- Overlap: 30 tokens
- Rationale: keeps answers coherent while still handling long entries without over-engineering.
