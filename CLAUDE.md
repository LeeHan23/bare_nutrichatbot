# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Development server
uvicorn app:app --reload --port 8000

# Production
gunicorn -w 1 -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:8000

# Docker
docker build -t nutribot .
docker run -e PORT=8000 -e OPENAI_API_KEY=sk-... -v /data:/app/data nutribot
```

## Setup

```bash
pip install -r requirements.txt

# Start local pgvector Docker container (required for dev)
docker start pgvector-nutribot
# First time only: docker run -d --name pgvector-nutribot -e POSTGRES_PASSWORD=postgres \
#   -e POSTGRES_DB=nutribot -p 5432:5432 pgvector/pgvector:pg16

# Build foundational knowledge base (reads from BASE_DOCS_DIR env var)
BASE_DOCS_DIR=/mnt/ssd/documents_to_ingest python build_base_db.py

# Create a B2B client API key (stored in DB as hashed nbk_live_{hex})
python create_api_key.py
```

## Tests

```bash
# Unit tests (no API key needed)
pytest test_db.py test_api.py

# Run a single test file
pytest test_db.py -v

# Integration tests (require running server and API key)
python test_bot_accuracy.py
python test_bot_culture.py
```

## Environment Variables

Copy `.env.example` to `.env`:
- `OPENAI_API_KEY` — required (for LLM only; embeddings are local)
- `OPENAI_MODEL` — default: `gpt-4-turbo`
- `EMBEDDING_MODEL` — default: `BAAI/bge-small-en-v1.5` (local, free, ~130MB)
- `DATABASE_URL` — PostgreSQL URL for the app DB (users, api_clients, documents, patients)
- `PGVECTOR_URL` — PostgreSQL URL for the vector store; defaults to `DATABASE_URL`
- `BASE_DOCS_DIR` — path to source PDFs for `build_base_db.py`; defaults to `data/base_docs/`
- `PERSISTENT_DISK_PATH` — default: `./data`
- `ADMIN_PASSWORD` — for admin panel
- `REDIS_URL` — optional, for session management
- `OLLAMA_BASE_URL` — default: `http://localhost:11434` (Ollama endpoint for the extractor)
- `OLLAMA_MODEL` — default: `qwen2.5:32b` (model used by `extractor.py` for field extraction)

For production, set both `DATABASE_URL` and `PGVECTOR_URL` to the remote PostgreSQL instance with pgvector enabled (`CREATE EXTENSION IF NOT EXISTS vector;`).

## Architecture

### Hybrid RAG Pipeline

Each chat request flows through:
1. `dependencies.py` — validates `X-API-Key` header against hashed keys in PostgreSQL
2. `website_chat_router.py` — resolves patient profile (explicit dict → `patient_id` DB lookup → None), then fires background extractor task
3. `rag.py` → `identify_target_disease()` (LLM call) → `get_rag_response()`
4. `vector_store.py` → `get_retriever(client_id)` builds a `MergedRetriever` combining:
   - **`base_knowledge`** collection (shared foundational knowledge)
   - **`client_{id}_knowledge`** collection (per-client isolated knowledge)
5. `chain_factory.py` → `create_conversational_chain()` wires an LCEL chain (LangChain 1.x): retriever → prompt → LLM → StrOutputParser, wrapped in `RunnableWithMessageHistory` for per-session memory
6. Streaming response via SSE with image tag parsing; non-streaming available at `/chat/get_response_sync`

### Embedding Model

`embeddings.py` provides a singleton `get_embedding_function()` returning `HuggingFaceEmbeddings` with `BAAI/bge-small-en-v1.5`. The model is downloaded from HuggingFace on first use (~130MB) and cached locally. **All four files that touch vectors must import from `embeddings.py`** — `vector_store.py`, `build_base_db.py`, `process_client_docs.py`, `document_manager.py` — so the model is only instantiated once per process.

### Multi-Tenancy

Client knowledge bases are isolated as separate pgvector **collections** (`client_{id}_knowledge`). The `X-API-Key` header determines the `client_id` for all requests. Document uploads (`POST /upload_documents/`) and deletions are scoped to the authenticated client. Deletions use direct SQL on `langchain_pg_embedding` filtered by `cmetadata->>'file_hash'`.

### Document Ingestion

`process_client_docs.py` pipeline:
1. SHA256 hash for deduplication (hash stored in pgvector chunk metadata as `file_hash`)
2. Unstructured.io partitioning (falls back to OCR `hi_res` strategy if no text found)
3. `chunk_by_title()` with 1500-char max
4. Batched insertion via `PGVector.from_documents()` (batch size: 100)
5. Metadata recorded in PostgreSQL (`DocumentMetadata` model)

`build_base_db.py` reads from `BASE_DOCS_DIR` (env var), uses incremental processing tracked by `data/file_tracker.json`, and parallelises PDF parsing with `ProcessPoolExecutor` (4 workers).

### Key Modules

| File | Purpose |
|---|---|
| `app.py` | FastAPI app, route registration, startup event |
| `chain_factory.py` | Persona/behavior prompt template (ADIME process), chain creation |
| `llm.py` | `ChatOpenAI` config (gpt-4-turbo, temp=0.5, max_tokens=1500) |
| `vector_store.py` | Hybrid `MergerRetriever` (k=3 per source) |
| `database.py` | SQLAlchemy models: `ApiClient`, `DocumentMetadata`, `User`, `Patient` + patient CRUD functions |
| `embeddings.py` | Singleton `get_embedding_function()` — `BAAI/bge-small-en-v1.5` |
| `admin_router.py` | HTML admin panel for API key management |
| `client_portal_router.py` | HTML client portal for document management |
| `website_chat_router.py` | `/chat/get_response` (streaming) and `/chat/get_response_sync` endpoints; profile resolution + background extractor |
| `image_handler.py` | Parses `[IMAGE: query]` markers, matches CSV annotations |
| `extractor.py` | Background LLM extraction of eNCPT supplementary fields from patient messages via Ollama |
| `patient_store.py` | `PatientStore` ABC + `SUPPLEMENTARY_FIELDS` whitelist |
| `local_patient_store.py` | Dev/staging `PatientStore` implementation backed by local Postgres |

### Patient Data Model

The `Patient` table in `database.py` is multi-tenant (scoped to `client_id`) and holds two categories of fields:

**Clinical fields** (hospital-supplied, never written by the extractor):
- Demographics: `name`, `ic_number` (Malaysian YYMMDD-SS-XXXX format), `age`, `gender`, `ethnicity`, `weight_kg`, `height_cm`
- Medical: `conditions`, `medications`, `dietary_restrictions`, `allergies`, `notes` (all JSON lists or text)
- Demo auth: `username`, `hashed_password`

**Supplementary fields** (eNCPT 2020 aligned, filled progressively by `extractor.py`):
- Tier 1 — Critical: `fluid_intake_ml`, `alcohol_per_week`, `supplements`, `religion`, `tobacco_status`
- Tier 2 — Important: `meals_per_day`, `snacks_per_day`, `processed_food_freq`, `fast_food_freq`, `self_prepared_freq`, `caffeine_mg_per_day`, `sugar_drinks_ml`, `activity_freq`, `activity_minutes`, `activity_intensity`, `food_avoidance`, `nutrition_knowledge`, `readiness_to_change`, `sodium_awareness`
- `extractor_metadata` (JSON) — provenance dict: `{field: {last_updated, source_session_id}}`

Patient lookup supports: by ID, username, name (case-insensitive, contains fallback), or IC number (normalised — strips dashes/spaces).

### Background Extractor Pipeline

After every chat message where a `patient_id` is provided, the router fires `_run_extractor_background()` as an `asyncio` task that runs concurrently with the streaming response (zero user-facing latency).

Pipeline inside `extractor.py`:
1. Build prompt with field descriptions and already-known values (so LLM doesn't re-extract)
2. Call `qwen2.5:32b` via Ollama (`/api/generate`, temperature=0, non-streaming, 30s timeout)
3. Strip markdown fences, parse JSON
4. `_validate_extraction()` — type-check + range-check each field, drop anything invalid
5. `_filter_already_filled()` — drop fields that already have a value (extractor is additive only)
6. `PatientStore.update_supplementary_fields()` — whitelist-gated write to DB with provenance

The `PatientStore` abstraction (`patient_store.py`) decouples the bot from the storage backend. `LocalPatientStore` is the current dev/staging implementation. Swapping to a hospital API requires only writing a `RemotePatientStore` that implements the same interface and updating the instantiation in `website_chat_router.py`.

### Persona & Prompting

The core system prompt lives in `chain_factory.py:get_system_template()`. It encodes:
- **ADIME nutrition care process**: Assessment → Diagnosis → Intervention → Monitoring/Evaluation
- Malaysian multicultural food context (Malay, Chinese, Indian cuisines)
- Open-ended questioning strategy to avoid looping

Modifying the bot's behavior means editing this template.

### Authentication Layers

- **B2B API clients**: `X-API-Key` header (format `nbk_live_{hex}`), hashed with werkzeug
- **Admin panel**: `ADMIN_PASSWORD` env var, plain text form submission
- **Client portal**: In-memory session store (not persistent across restarts)
