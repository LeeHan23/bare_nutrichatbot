# NutriChatbot — Project Documentation

## What This Project Is

An AI-powered clinical nutrition chatbot for Malaysian cardiac patients. It is deployed as a REST API that B2B clients (hospitals, clinics) integrate with by passing an API key and a patient ID. The bot retrieves relevant clinical guidelines from a vector database, personalises the answer using the patient's medical profile, and streams a reply back to the patient.

The system runs across two machines:
- **RTX 3050 Server** — FastAPI application, Postgres + PGVector, Cloudflare tunnel
- **Mac Studio** — CLaRa-7B inference (primary RAG model), Ollama qwen2.5:32b (orchestration)

---

## What Was Built — Chronological Steps

### Step 1 — Initial Project Setup
- Created the FastAPI app skeleton (`app.py`)
- Set up Postgres + PGVector via Docker
- Defined the B2B multi-tenant model: each clinic is an `ApiClient` with a hashed API key; all patients and documents belong to a client

### Step 2 — Clinical Knowledge Base Ingestion (`build_base_db.py`)
- Collected 58 clinical PDFs (Malaysian CPGs, NICE guidelines, WHO nutrition guidance, MDGV)
- Wrote a parallel ingestion pipeline that chunks, filters junk, and embeds into PGVector
- Stored 24,268 clean chunks under the `base_knowledge` collection
- Embedded using BAAI/bge-m3 with a LoRA adapter for domain-specific retrieval

### Step 3 — Basic RAG Pipeline
- Connected retrieved chunks to CLaRa-7B for generation
- Initial LangChain LCEL chain with `InMemoryChatMessageHistory` per session
- Streaming response via `StreamingResponse` in `website_chat_router.py`

### Step 4 — CLaRa Integration as Primary Model
- Replaced the LangChain-only path with a direct CLaRa API call to the Mac Studio
- Patched CLaRa to run on Apple MPS (was CUDA-only) — patches live in huggingface module cache
- Added `llm.py` as the single abstraction layer for all LLM backends (CLaRa, Ollama, OpenAI fallback)

### Step 5 — Patient Profile System
- Designed `database.py` with `Patient` ORM including demographic, clinical, and supplementary fields
- Wrote `seed_patients.py` with 8 realistic synthetic Malaysian patients covering all condition types (T2DM, HTN, CKD, PCOS, dyslipidaemia, cardiac, general wellness)
- Created `PatientStore` ABC in `patient_store.py` to abstract the data layer for eventual hospital API swap

### Step 6 — Retrieval Quality Improvements
- Added `TopicBoostedRetriever` in `vector_store.py` — re-ranks chunks by topic overlap on top of vector similarity
- Built a `TOPIC_HINTS` taxonomy (150+ mappings, English + Bahasa Malaysia) linking query phrases to `doc_topics` metadata tags
- Prefixed retrieval queries with patient conditions so condition-specific guideline chunks score higher

### Step 7 — LLM Extractor (v1 → v2)
- Built `extractor.py`: sends each patient message to qwen2.5:32b, extracts new profile fields as JSON
- Extractor runs as a background async task after every chat message — zero added latency
- v1: 19 supplementary fields (fluid intake, tobacco, supplements, activity, etc.)
- v2 cardiac additions: fat intake level, fat type sources, medication compliance, activity types, self-reported food allergies
- Extractor never overwrites existing data; only fills empty fields
- Validates extracted values against allowed enums per field; strips LLM markdown noise before JSON parse

### Step 8 — v2 Cardiac Schema & DB Migration
- Defined cardiac-priority eNCPT fields in `data/encpt/encpt_curated.json`
- Wrote `scripts/migrate_v2.py` to add new columns to the live database idempotently
- Added `personalization_level` column (L0–L3) with dietitian-assigned tiers per patient

### Step 9 — Personalization Levels (L0–L3)
- Defined four clinical tiers based on cardiovascular risk:
  - L0: no risk, full-spectrum advice including vigorous activity
  - L1: emerging risk (early HTN, elevated BMI), structured safety-aware guidance
  - L2: established conditions (physical limitations, higher CV risk), low-intensity only
  - L3: post-cardiac event or high clinical risk, medically supervised advice only
- Injected tier-specific instruction blocks into both CLaRa prompt and Qwen generation prompt
- Second-person (patient self-mode) and third-person (clinician view) voice variants for each level

### Step 10 — Option B Hybrid Pipeline
- Added CLaRa-compress → Qwen-generate pipeline for situations where pure CLaRa generation is suboptimal
- CLaRa's `/compress` endpoint synthesises a ~400-token clinical digest from retrieved chunks
- Qwen2.5:32b then converts the digest into a warm conversational reply
- Prompt engineering enforces: direct second-person voice, 3-part structure (answer + tip + follow-up question), under 100 words

### Step 11 — Food Context Enrichment
- Added `get_food_context()` in `rag.py` — calls Ollama to describe any Malaysian dish mentioned in the query
- Provides CLaRa with dish ingredients and approximate nutrition values when the knowledge base has no specific chunk for a local food (e.g. "nasi lemak", "char kway teow")

### Step 12 — CKD/KDOQI Knowledge Ingestion
- Ingested CPG CKD 2023 and KDOQI 2020 guideline PDFs into the knowledge base
- Added CKD/renal-specific keyword mappings to `TOPIC_HINTS` (potassium restriction, phosphorus restriction, eGFR, dialysis, renal nutrition)
- Enriched existing chunk metadata with curated keywords via `scripts/enrich_v1_with_keywords.py`

### Step 13 — Content Pipeline
- Designed a structured educational content delivery system
- `scripts/generate_content.py`: for each condition group × day offset × topic, retrieves RAG chunks and uses Ollama to generate 6 actionable clinical tips, stores in `content_materials` DB table
- `scripts/content_scheduler.py`: daily cron job that checks which patients are due content (based on `first_chat_at` + day offset), logs delivery entries in `content_delivery_log`
- Covers 6 condition groups (T2DM, HTN, CKD, Cardiac, PCOS, Dyslipidaemia, General) × 6 day offsets (3, 5, 7, 14, 21, 30) = 36 niche cases

### Step 14 — Evaluation Harness
- `eval/test_extractor.py`: 20 test cases covering English, Bahasa Malaysia, and mixed (Manglish) patient messages; tests that correct fields are extracted and that generic messages extract nothing
- `eval/test_rag.py`: 10 RAG regression tests checking clinical accuracy (required terms in answer), voice correctness (no patient name, uses "you"/"your"), and personalization (L3 answers require supervision language)

---

## Script-by-Script Reference

### Core Application

#### `app.py` — FastAPI Entry Point
- Creates the FastAPI app and registers all routers
- On startup: calls `db.create_db_and_tables()` to ensure schema exists; seeds from Docker volume if running containerised
- Mounts `/images` as a static file directory
- Defines the patient login endpoint (`POST /patient/login`) — name-based lookup with IC disambiguation for duplicate names
- Exposes patient CRUD endpoints (`GET /patients/`, `GET /patients/{id}`)
- Exposes document upload/list/delete endpoints for B2B clients
- Includes the developer test UI at `/dev` (raw HTML in a constant)
- Includes the patient-facing UI at `/` (served from `patient_app.html`)

#### `database.py` — ORM and DB Functions
- Defines all SQLAlchemy models: `User`, `ApiClient`, `DocumentMetadata`, `Patient`, `ContentMaterial`, `ContentDeliveryLog`
- `Patient` model columns:
  - **Clinical** (from hospital, never overwritten): name, IC number, age, gender, ethnicity, BMI fields, conditions, medications, dietary restrictions, allergies, notes
  - **Supplementary v1** (extractor-filled): 19 fields including fluid intake, tobacco status, activity data, food habits, sodium awareness
  - **Supplementary v2 cardiac**: fat intake level, fat sources, medication compliance, activity types, self-reported food allergies
  - **System**: personalization level, extractor metadata (provenance), first chat timestamp, demo login credentials
- `patient_to_profile_dict()` converts an ORM object to the dict that `rag.get_rag_response()` expects
- All API key operations use `werkzeug` password hash — no plaintext storage
- `ContentMaterial`: stores LLM-generated tips per condition group + day offset + topic
- `ContentDeliveryLog`: audit trail of what was queued/sent per patient

#### `rag.py` — RAG Pipeline
- Three parallel execution paths (controlled by `.env` feature flags):
  1. **CLaRa primary** (`USE_CLARA=true`): retrieves chunks → injects patient profile → calls CLaRa `/generate`
  2. **Option B hybrid** (`USE_CLARA_COMPRESS=true`): retrieves chunks → CLaRa `/compress` produces clinical digest → Qwen generates conversational reply
  3. **Legacy LangChain** (fallback when both above are false): uses `create_conversational_chain()`
- `identify_target_disease()`: uses Ollama to extract the primary condition from a question when no patient profile is available
- `get_food_context()`: uses Ollama to describe any Malaysian food or dish mentioned; returns empty string if no food detected
- `_to_second_person_profile()`: rewrites "Name: X" → "Your name: X (do NOT repeat...)" etc. for patient self-mode
- `_build_qwen_prompt()`: constructs the full prompt for Option B including patient profile block, personalization level instruction, clinical digest, food context, and strict voice rules
- `_LEVEL_INSTRUCTIONS` / `_LEVEL_INSTRUCTIONS_SELF`: per-level clinical guidance injected into prompts for L0–L3

#### `llm.py` — LLM Abstraction Layer
- Feature flags: `USE_CLARA`, `USE_CLARA_COMPRESS`, `USE_OLLAMA`
- `get_llm()`: returns a LangChain chat model (Ollama preferred, OpenAI fallback) for orchestration tasks
- `get_direct_llm_response()`: one-shot string query to the orchestration LLM (used for disease identification and food context)
- `call_clara_api()`: HTTP POST to CLaRa `/generate` on Mac Studio; returns answer string
- `call_clara_compress()`: HTTP POST to CLaRa `/compress`; returns a structured clinical digest (~400 tokens)
- `call_ollama_generate()`: HTTP POST to Ollama `/api/generate` directly (not via LangChain); larger token budget (800) for full responses

#### `vector_store.py` — Retrieval
- `TOPIC_HINTS`: dictionary mapping 80+ query phrases (EN + BM) to sets of `doc_topics` metadata tags
- `detect_query_topics()`: scans a query string against TOPIC_HINTS with word-boundary padding
- `MergedRetriever`: combines results from two PGVector collections (base knowledge + client-specific knowledge) and deduplicates
- `TopicBoostedRetriever`: pulls a wider candidate pool (k=15 per collection), detects query topics, adds patient conditions as additional topic signals, scores each chunk as `(1/(rank+1)) + boost_factor × overlap_ratio`, returns top 5
- `get_retriever()`: public factory — builds the hybrid topic-boosted retriever for a given client and patient condition list

#### `embeddings.py` — Embedding Function
- Loads BAAI/bge-m3 base model with a LoRA adapter from `/home/han/models/embedding_lora`
- Falls back to base BAAI/bge-m3 if the LoRA adapter is not found
- Used by both the ingestion scripts and the retrieval pipeline

#### `extractor.py` — Profile Extractor
- `EXTRACTOR_FIELDS`: list of 15 field definitions with eNCPT codes, types, and extraction guidance covering cardiac-priority data (fat intake, medication compliance, activity, tobacco, supplements, etc.)
- `EXTRACTION_PROMPT`: zero-shot prompt instructing qwen2.5:32b to extract only what is explicitly stated; handles EN, BM, and Manglish
- `_validate_field()`: per-field type checking and enum validation; converts strings to lowercase, integers to int, strips whitespace
- `_filter_already_filled()`: drops any field that already has a non-null, non-empty value in the current profile — extractor is purely additive
- `extract_from_message()`: main entry point; builds prompt, calls Ollama at temperature 0, strips markdown fences, parses JSON, validates, filters, returns new fields dict

#### `website_chat_router.py` — Chat Router
- `POST /chat/get_response`: streaming endpoint
- `POST /chat/get_response_sync`: non-streaming endpoint, collects chunks into a full string
- Both endpoints:
  - Resolve patient profile (explicit dict → patient_id DB lookup → None)
  - Infer `is_patient_self` (default True when `patient_id` is given; set False explicitly for clinician tools)
  - Fire two background async tasks: `_record_first_chat()` (sets `first_chat_at` on first message) and `_run_extractor_background()` (extracts new fields, writes via PatientStore)
  - Call `rag.get_rag_response()` with the resolved profile

#### `patient_store.py` — PatientStore Abstraction
- Defines the `PatientStore` ABC with two methods: `get_profile()` and `update_supplementary_fields()`
- `SUPPLEMENTARY_FIELDS`: whitelist of extractor-fillable column names; prevents extractor from touching clinical data
- Swap point for production: implement `RemotePatientStore(PatientStore)` pointing to the hospital REST/FHIR API

#### `local_patient_store.py` — Dev Implementation
- `LocalPatientStore(PatientStore)`: wraps SQLAlchemy ORM
- `update_supplementary_fields()`: validates keys against `SUPPLEMENTARY_FIELDS` whitelist, writes only changed values, appends provenance metadata `{field: {confidence, last_updated, source_session_id}}` to `extractor_metadata` JSON column

#### `chain_factory.py` — LangChain Chain (Legacy Fallback)
- Creates a conversational LCEL chain with `InMemoryChatMessageHistory` keyed by session ID
- Used only when `USE_CLARA=false` and `USE_CLARA_COMPRESS=false`
- History is in-memory and lost on restart — not suitable for production

#### `dependencies.py` — FastAPI Dependencies
- `get_db()`: yields a SQLAlchemy session
- `get_api_client()`: extracts `X-API-Key` header, calls `db.get_client_by_key()`, raises HTTP 401 if invalid

#### `build_base_db.py` — Knowledge Base Ingestion
- Reads PDFs from `BASE_DOCS_DIR` (default: `data/base_docs/`, override with env var)
- Uses `file_tracker.json` to skip already-processed files (mtime-based)
- Parallel processing via `ProcessPoolExecutor` (up to 4 workers), 10-minute timeout per file
- Per file: `unstructured.partition()` extracts text elements; headers, footers, images filtered out; `chunk_by_title()` creates chunks of max 1024 characters
- `is_junk_chunk()` filters out: too-short chunks, table-of-contents, reference lists, front matter, ISBN pages, citation-heavy academic sections
- Batches chunks into PGVector in groups of 500
- Stores to `base_knowledge` collection

#### `process_client_docs.py` — Client Document Ingestion
- Same chunk/filter pipeline as `build_base_db.py` but stores to `client_{id}_knowledge` collection
- SHA-256 hash used for deduplication (checked before ingestion)
- Called by `app.py` upload endpoint

#### `document_manager.py` — Vector Store Deletion
- Deletes all chunks for a given `file_hash` from the client's PGVector collection
- Called when a client deletes a document via `DELETE /documents/{id}`

#### `image_handler.py` — Image Response Parsing
- `parse_response_for_image()`: scans the LLM answer text for `[IMAGE: ...]` tags; resolves them to static `/images/` URLs
- Allows the RAG answer to reference educational infographic images stored on the server

#### `mcp_server.py` — MCP Server
- Exposes NutriBot functionality as MCP (Model Context Protocol) tools for Claude Desktop integration
- Tools: `get_patient_profile`, `list_patients`, `get_nutrition_advice`, `search_nutrition_knowledge`, `get_client_documents`, `list_api_clients`

#### `admin_router.py` — Admin Routes
- Password-protected admin endpoints for managing patients and viewing system state

#### `client_portal_router.py` — Client Portal
- Session-based authentication for B2B client web portal (document upload, patient management UI)

---

### Setup and Seed Scripts

#### `seed_patients.py` — Demo Patient Seeder
- Creates 8 synthetic Malaysian patients covering all clinical use cases:
  - Ahmad Fadzillah (T2DM + HTN, L2) — Malay, sedentary office worker, high HbA1c
  - Lim Siew Ching (CKD Stage 3 + HTN, L2) — Chinese female, shellfish allergy, fluid restricted
  - Kavitha (PCOS + Insulin Resistance, L1) — Indian female, peanut allergy, trying to conceive
  - Mohd Hafizuddin (Dyslipidaemia + Obesity, L1) — Malay, lorry driver, smoker
  - Tan Wei Loong (HTN + Hypercholesterolaemia + T2DM, L2) — Chinese, family-based counselling
  - Siti Hajar (Stable IHD + HTN + Hypercholesterolaemia, L1) — Malay female, post-diagnosis
  - Nurul Ain (general wellness, L0) — young teacher, active
  - Rajendran (Post-CABG + Heart Failure EF 35% + T2DM + HTN + CKD Stage 4, L3) — high-risk, supervised-only
- Idempotent: patches IC number and personalization level on existing records, skips otherwise unchanged rows
- All demo passwords: `demo1234`

#### `create_api_key.py` — API Key Creation
- Interactive or scripted creation of a new `ApiClient` with a generated `nbk_live_...` key

#### `reset_key.py` — API Key Reset
- Regenerates and re-hashes an API key for an existing client

---

### Migration Scripts

#### `scripts/migrate_v2.py` — v2 Cardiac Column Migration
- Idempotent `ALTER TABLE` migration adding 5 new columns to `patients`:
  - `fat_intake_level` (VARCHAR)
  - `fat_sources` (JSON, default `[]`)
  - `medication_compliance` (VARCHAR)
  - `activity_types` (JSON, default `[]`)
  - `personalization_level` (VARCHAR)
- Reads existing columns first; skips any that already exist
- Prints a summary of added vs skipped columns

#### `scripts/database_patch.py` — Ad-hoc DB Patch
- One-off patch script for fixing specific data issues in production without a full migration

#### `scripts/migrate_content_pipeline.py` — Content Pipeline Tables Migration
- Adds `content_materials` and `content_delivery_log` tables to the database

---

### Retrieval Quality Scripts

#### `scripts/enrich_v1_with_keywords.py` — Keyword Metadata Backfill
- Takes a `doc_keyword_mapping.json` file mapping document filenames to curated keyword/topic/summary/language metadata
- For each mapped document, finds its existing chunks in `langchain_pg_embedding` by source filename
- Merges keyword metadata into the chunk's `cmetadata` JSON column in-place (no re-embedding needed)
- `--dry-run` flag prints the changes without writing

#### `scripts/reembed_with_keywords.py` — Re-embedding with Metadata
- Alternative to `enrich_v1_with_keywords.py` — re-creates chunks with the new metadata embedded
- Used when keyword metadata should affect the embedding (not just re-ranking)

---

### Content Pipeline Scripts

#### `scripts/generate_content.py` — Educational Content Library Generator
- Defines 36 niche cases: 6 condition groups × 6 day offsets × condition-specific topics
  - Groups: T2DM, HTN, CKD, Cardiac, PCOS, Dyslipidaemia, General
  - Day offsets: 3, 5, 7, 14, 21, 30
- For each niche case:
  1. Runs a targeted RAG query against the knowledge base (base + client collections)
  2. Calls `call_ollama_generate()` to produce 6 structured tips grounded in the retrieved evidence
  3. Stores raw tips in `content_materials` table (is_active=False until dev team polishes)
- Exports everything to an Excel workbook organised by condition group tab
- CLI flags: `--client-id`, `--group`, `--day`, `--dry-run`, `--no-db`, `--output-dir`

#### `scripts/content_scheduler.py` — Daily Content Delivery Scheduler
- Intended to run as a daily cron job at 8:00 AM
- For each patient with `first_chat_at` set, calculates days elapsed since first chat
- If `days_elapsed` matches a scheduled offset (3, 5, 7, 14, 21, 30): maps patient conditions to condition groups, checks for existing delivery log entry (idempotent), finds active materials, writes a `queued` or `no_material` entry in `content_delivery_log`
- `--dry-run` flag prints the plan without DB writes
- `--as-of YYYY-MM-DD` simulates a different date for testing

#### `scripts/test_content_pipeline.py` — Content Pipeline Integration Test
- End-to-end test that exercises both the generator and scheduler

---

### Evaluation Scripts

#### `eval/test_extractor.py` — Extractor Regression Tests
- 20 test cases covering:
  - English: fat intake + sources, medication compliance (good/variable/poor), activity (type + frequency + minutes), food allergies, tobacco status, supplements
  - Bahasa Malaysia: same fields in BM including "santan" → coconut milk normalisation, "saya alah" allergy detection
  - Mixed Manglish: "aiyah, sometimes I forget lah"
  - Negative cases: generic questions and greetings that should extract nothing
- Each case specifies `expected` (field → value) with subset matching for lists and substring matching for strings
- `--smoke`: runs 5 critical cases only (~2 min); `--case N`: single case; `--tag bm/en/negative`: filter by tag
- Writes JSON results to `--out results/extractor.json`

#### `eval/test_rag.py` — RAG Pipeline Regression Tests
- 10 test cases against real patients in the DB; calls `get_rag_response()` end-to-end
- Checks:
  - **Required terms**: answer must contain at least N of the specified clinical terms
  - **Forbidden terms**: answer must not contain patient names, "the patient", or third-person pronouns
  - **Voice check**: answer uses "you" and "your"
  - **Personalization check**: L3 patient answers include "supervised", "doctor", or "cardiac rehab"
- Representative cases: CKD patient avoiding bananas (potassium), T2DM white rice (carbs + portion), L3 Post-CABG exercise (supervision-only), L0 general wellness (no over-restriction)
- `--smoke`: 4 critical cases; `--show-answers`: print answer text; `--out results/rag.json`

#### `eval/eval_ragas.py` — RAGAs Automated Evaluation
- Uses the RAGAS framework to evaluate retrieval faithfulness, answer relevance, and context precision
- Produces quantitative metrics for the RAG pipeline

---

### Fine-tuning Scripts (in `finetune/`)

#### `generate_training_data.py` — Synthetic ADIME Data Generator
- Generates synthetic ADIME (Assessment, Diagnosis, Intervention, Monitoring and Evaluation) training examples for nutrition scenarios

#### `generate_embedding_training_data.py` — Embedding Training Data
- Generates positive and negative retrieval pairs for fine-tuning the embedding model

#### `finetune_embeddings.py` — LoRA Embedding Fine-tuning
- Fine-tunes BAAI/bge-m3 with LoRA on nutrition-specific retrieval pairs
- Saves the adapter to `/home/han/models/embedding_lora`

#### `export_pairs_csv.py` — Training Pairs Export
- Exports embedding training pairs to CSV for inspection or external use

---

### eNCPT Schema Scripts (in `data/encpt/`)

#### `build_curated_schema.py` — Schema Generator
- Reads the curated schema definition and generates `encpt_curated.json` (34 fields, EN + BM, cardiac focus)
- Source of truth for the extractor field list

#### `json_to_md.py` — Schema to Markdown Converter
- Converts `encpt_curated.json` to a human-readable `encpt_curated.md` for dietitian review

---

## Key Data Flows

### Chat Request (patient self-mode)
```
Patient → POST /chat/get_response
  → get_api_client() validates X-API-Key
  → _resolve_patient_profile() loads Patient from DB
  → asyncio.create_task(_record_first_chat)
  → asyncio.create_task(_run_extractor_background)
  → rag.get_rag_response()
      → get_retriever() → TopicBoostedRetriever (base + client knowledge)
      → get_food_context() → Ollama (if food detected in question)
      → call_clara_api() or call_clara_compress() + call_ollama_generate()
      → parse_response_for_image()
  → StreamingResponse → patient
```

### Extractor Background Flow (zero latency to patient)
```
patient message (already sent back) →
  extract_from_message(message, current_profile)
    → build prompt with EXTRACTOR_FIELDS
    → Ollama qwen2.5:32b @ temperature=0
    → parse JSON → validate → filter already-filled
  → patient_store.update_supplementary_fields()
    → check against SUPPLEMENTARY_FIELDS whitelist
    → write new fields + extractor_metadata provenance to DB
```

### Knowledge Base Ingestion (one-time setup)
```
Clinical PDFs → build_base_db.py
  → unstructured.partition() (fast strategy, hi_res fallback)
  → filter_elements() (remove headers, footers, images)
  → chunk_by_title() (max 1024 chars)
  → is_junk_chunk() (remove TOC, references, short fragments)
  → BAAI/bge-m3 + LoRA embed()
  → PGVector "base_knowledge" collection
```

---

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Postgres connection | `postgresql://postgres:postgres@localhost:5432/nutribot` |
| `PGVECTOR_URL` | PGVector connection (same DB) | Same as DATABASE_URL |
| `CLARA_BASE_URL` | CLaRa inference server | `https://clara-internal-x9k2.computationalrd.com` |
| `OLLAMA_BASE_URL` | Ollama server | `https://ollama-internal-x9k2.computationalrd.com` |
| `OLLAMA_MODEL` | Ollama model name | `qwen2.5:32b` |
| `USE_CLARA` | Enable CLaRa primary path | `true` |
| `USE_CLARA_COMPRESS` | Enable Option B hybrid | `false` |
| `USE_OLLAMA` | Enable Ollama orchestration | `true` |

---

## Pending Work (priority order)

1. **Cloudflare keep-alive cron** — add `*/4 * * * *` cron to prevent 524 cold-start errors
2. **Test bilingual extractor end-to-end** — send BM message via public URL, verify `extractor_metadata` populated
3. **Persist conversation history to DB** — replace `InMemoryChatMessageHistory` with a `chat_messages` table
4. **WhatsApp integration** — Twilio/Meta webhook, phone number → patient_id mapping table
5. **RemotePatientStore** — implement hospital REST/FHIR API client as the production swap for `LocalPatientStore`
6. **Deploy content pipeline** — activate `content_materials` by setting `is_active=True` after dev team polishes tips; wire the delivery channel
