# Nutribot — Claude Code Handover Document

## Project Overview

A distributed AI-powered nutrition chatbot for cardiac patients, built for a Malaysian hospital/university client. Uses a split architecture across two machines. The system provides personalized dietary advice using RAG (Retrieval-Augmented Generation) via CLaRa-7B + Qwen2.5:32b (Option B hybrid), with dynamic patient profile collection via an LLM extractor and a scheduled content drip pipeline.

**Public demo URL:** `https://nutribot.computationalrd.com`
**API Key:** `nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3`
**Docs:** `https://nutribot.computationalrd.com/docs`

---

## Architecture

```
Public Internet
    │
    ▼
nutribot.computationalrd.com (Cloudflare Tunnel)
    │
    ▼
RTX 3050 Server — Linux, user: han, IP: 100.101.247.5
/mnt/ext/bare_NutriChatbot/          ← main codebase (exFAT drive MEEEE, /dev/sdb1)
    - FastAPI bot (systemd: nutribot.service)
    - PGVector / Postgres (Docker: pgvector-nutribot)
    - Cloudflare tunnel (systemd: cloudflared.service)
    - Python: /home/han/miniconda3/bin/python (NOT .venv — exFAT breaks symlinks)
    │
    │ HTTPS via Cloudflare Tunnel
    ├─→ clara-internal-x9k2.computationalrd.com → Mac Studio :8001
    └─→ ollama-internal-x9k2.computationalrd.com → Mac Studio :11434

Mac Studio — macOS, user: bing, M3 Ultra 96GB
    - CLaRa-7B inference on MPS (LaunchDaemon: com.nutribot.clara)
    - Ollama qwen2.5:32b orchestration (LaunchDaemon: com.nutribot.ollama)
    - Cloudflare tunnel to expose both (LaunchDaemon: com.cloudflare.cloudflared)
    - CLaRa path: /Users/bing/Desktop/clara_lyh/clara-nutri/
    - Conda env: clara (Python 3.10)
```

**Note on the `-internal-` tunnel hostnames:** `clara-internal-x9k2.computationalrd.com` and `ollama-internal-x9k2.computationalrd.com` are served by the Mac Studio's *own* `cloudflared` LaunchDaemon, not proxied through the RTX 3050. The RTX 3050 in the diagram above is just a *client* calling those URLs like any other caller would. Because Cloudflare's edge routes to the Mac Studio directly, these two hostnames are reachable from anywhere on the internet — including when the RTX 3050 (and therefore the public `nutribot.computationalrd.com` URL) is down. See "Testing CLaRa/Ollama directly" under Service Management.

### Drive Layout (RTX 3050)

| Device | Mount | Label | FS | Size | Notes |
|--------|-------|-------|----|------|-------|
| /dev/sda1 | /mnt/ssd | T7 Shield | exFAT | 932GB | **100% FULL** — do not use for project files |
| /dev/sdb1 | /mnt/ext | MEEEE | exFAT | 932GB | **Active project drive** (~910GB free) |
| /dev/nvme0n1p3 | / | — | ext4 | 465GB | OS drive |

**IMPORTANT:** `/mnt/ssd` is full. The project codebase lives on `/mnt/ext`. `/dev/sdb1` is mounted on boot via `/etc/fstab` (added 12 June 2026, by UUID with `nofail`):
```
UUID=67B2-12E3 /mnt/ext exfat rw,uid=1000,gid=1000,fmask=0000,dmask=0000,allow_utime=0022,iocharset=utf8,errors=remount-ro,nofail 0 0
```

---

## Repository Structure

```
/mnt/ext/bare_NutriChatbot/
├── app.py                    # FastAPI app entry point, demo UI
├── rag.py                    # RAG pipeline (Option B: CLaRa compress → Qwen generate)
├── llm.py                    # LLM abstraction (CLARA_BASE_URL, OLLAMA_BASE_URL from .env)
├── chain_factory.py          # LangChain LCEL chain, InMemoryChatMessageHistory
├── database.py               # SQLAlchemy ORM — Patient, ContentMaterial, ContentDeliveryLog
├── dependencies.py           # FastAPI dependencies (X-API-Key auth, DB session)
├── vector_store.py           # PGVector TopicBoostedRetriever, LoRA embedding model
├── embeddings.py             # Embedding utilities (BAAI/bge-m3 + LoRA)
├── website_chat_router.py    # /chat/get_response (streaming) + /chat/get_response_sync
├── whatsapp_router.py        # /chat/whatsapp (Twilio) + /chat/whatsapp/meta (Meta Cloud API) inbound webhooks
├── whatsapp.py                # WhatsApp send_message + EKA/tips message formatters
├── admin_router.py           # Admin API routes
├── client_portal_router.py   # Client-facing portal routes
├── mcp_server.py             # MCP server for Claude Desktop integration
├── patient_store.py          # PatientStore ABC + SUPPLEMENTARY_FIELDS whitelist + get_patient_store() factory
├── local_patient_store.py    # LocalPatientStore (dev/staging, wraps SQLAlchemy)
├── remote_patient_store.py   # RemotePatientStore (prod, hospital REST API — placeholder contract)
├── mock_hospital_api.py       # Standalone mock of the hospital API, for testing RemotePatientStore
├── extractor.py              # LLM-based profile extractor (qwen2.5:32b, v2, BM support)
├── document_manager.py       # Document upload/management
├── process_client_docs.py    # Client document ingestion into vector store
├── image_handler.py          # Image upload and processing
├── patient_app.html          # Patient-facing HTML UI
├── build_base_db.py          # Ingestion script for clinical PDFs into PGVector
├── seed_patients.py          # Seeds 8 mock Malaysian patients into local DB
├── create_api_key.py         # API key creation utility
├── reset_key.py              # API key reset utility
├── conftest.py               # Pytest fixtures
├── test_api.py               # API endpoint tests
├── test_db.py                # Database tests
├── test_bot_accuracy.py      # Bot accuracy tests
├── test_bot_culture.py       # Cultural/bilingual response tests
├── .env                      # Environment variables (NOT committed)
├── agentgateway/
│   └── config.yaml           # Agent gateway configuration
├── data/
│   └── encpt/
│       ├── build_curated_schema.py   # Generates encpt_curated.json
│       ├── json_to_md.py             # Generates dietitian-friendly markdown
│       ├── encpt_curated.json        # v2.0 cardiac schema (34 fields, EN+MS)
│       ├── encpt_curated.md          # Human-readable review doc for dietitian (generated)
│       ├── extractor_v2.py           # v2 extractor draft (superseded by root extractor.py)
│       └── encpt_schema.json         # Full 447-field eNCPT 2020 parse
├── scripts/
│   ├── generate_content.py          # Content generation: 43 niche cases → RAG tips → Excel
│   ├── content_scheduler.py         # Daily cron: matches due patients to active materials
│   ├── migrate_content_pipeline.py  # Idempotent migration for content pipeline tables
│   ├── test_content_pipeline.py     # Smoke tests for content pipeline (4 tests)
│   ├── migrate_v2.py                # v2 supplementary fields DB migration
│   ├── migrate_chat_history.py      # Creates chat_messages table (conversation history persistence)
│   ├── migrate_whatsapp_columns.py  # Adds whatsapp_opted_out column to patients
│   ├── database_patch.py            # Ad-hoc DB patch script
│   ├── reembed_with_keywords.py     # Re-embed chunks with keyword metadata
│   ├── enrich_v1_with_keywords.py   # Add doc_keywords/topics to existing chunks
│   ├── test_extractor_v2.py         # Extractor v2 test cases
│   └── test_remote_patient_store.py # E2E test: RemotePatientStore against mock_hospital_api.py
├── finetune/
│   ├── generate_training_data.py         # Synthetic ADIME training data generator
│   ├── generate_embedding_training_data.py
│   ├── finetune_embeddings.py            # LoRA embedding fine-tuning
│   ├── export_pairs_csv.py
│   ├── colab_finetune.ipynb
│   └── Modelfile                         # Ollama Modelfile
└── eval/
    ├── eval_ragas.py          # RAGAs evaluation harness
    ├── eval_dataset.json      # Evaluation dataset
    └── results/               # Eval run outputs
```

---

## Environment Variables (.env on RTX 3050)

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nutribot
PGVECTOR_URL=postgresql://postgres:postgres@localhost:5432/nutribot
CLARA_BASE_URL=https://clara-internal-x9k2.computationalrd.com
OLLAMA_BASE_URL=https://ollama-internal-x9k2.computationalrd.com
OLLAMA_MODEL=qwen2.5:32b
USE_CLARA=false
USE_CLARA_COMPRESS=true
USE_OLLAMA=true
```

**Active RAG mode: Option B** — `USE_CLARA=false`, `USE_CLARA_COMPRESS=true`. CLaRa is used only for `/compress` (text digest), Qwen generates the final answer.

---

## Patient Database (Mock / Dev)

8 synthetic Malaysian patients in local Postgres:

| ID | Name | Username | Conditions | Level |
|----|------|----------|------------|-------|
| 1 | Ahmad Fadzillah bin Roslan | ahmad.fadzillah | Type 2 Diabetes, Hypertension | L2 |
| 2 | Lim Siew Ching | lim.siewching | CKD Stage 3, Hypertension | L2 |
| 3 | Kavitha a/p Subramaniam | kavitha.subra | PCOS, Insulin Resistance | L1 |
| 4 | Mohd Hafizuddin bin Salleh | hafizuddin.salleh | Dyslipidaemia, Obesity Class I | L1 |
| 5 | Tan Wei Loong | tan.weiloong | Hypertension, Hypercholesterolaemia, T2DM | L2 |
| 10 | Nurul Ain binti Zulkifli | nuraini.zulkifli | None (general wellness) | L0 |
| 11 | Rajendran a/l Muthu | rajendran.muthu | Post-CABG, Heart Failure (EF 35%), T2DM, HTN, CKD Stage 4 | L3 |
| 12 | Siti Hajar binti Mohd Nasir | sitihajar.mnasir | Overweight, Pre-hypertension | L1 |

**Production note:** All patient data in production must live on the hospital/university server. Local DB is dev/staging only. The `PatientStore` abstraction in `patient_store.py` is the designed swap point — implement `RemotePatientStore(PatientStore)` when the hospital API is available.

---

## Key Design Decisions

### RAG Pipeline — Option B (Active)

```
Question + Patient Profile
    ↓
TopicBoostedRetriever (k=15 → rerank → top 5)
    ↓
CLaRa /compress  →  clinical digest (1000-1500 chars)
    ↓
Qwen2.5:32b generate  →  streamed answer
    ↓ (fallback if CLaRa down)
Raw chunks → Qwen2.5:32b generate
```

- **CLaRa-7B** used only for compression (fast summarization of retrieved chunks), not final generation
- **qwen2.5:32b via Ollama** generates the patient-facing response with conversational tone
- `keep_alive=-1` in `llm.py` keeps Qwen loaded in VRAM permanently
- Patient profile injected via `_build_qwen_prompt()` in `rag.py`
- Personalization level (L0–L3) injects level-specific safety instructions into all three pipeline paths

### TopicBoostedRetriever

- k=15 candidate pool from both `base_knowledge` and `client_{id}_knowledge` collections
- Boost-rerank by condition-matched topic tags → top 5 returned
- Condition-prefixed query rewriting: `"CKD, HTN: <question>"` ensures correct doc retrieval
- `[TopicBoost]` log lines in `/var/log/nutribot.log` for debugging

### Personalization Levels (L0–L3)

| Level | Profile | Content scope |
|-------|---------|---------------|
| L0 | No risk, no history | Full spectrum including vigorous activity |
| L1 | Emerging/moderate risk (early HTN, elevated BMI) | Structured, safety-aware, do/don't boundaries |
| L2 | Established conditions, physical limitations, higher CV risk | Low-intensity, symptom monitoring, strict stop conditions |
| L3 | High clinical risk, recent cardiac events | Medical oversight only, emergency education |

### Content Drip Pipeline

Scheduled educational content delivery for patients after their first chat:

```
first_chat_at  +  N days  →  content_scheduler.py  →  ContentDeliveryLog (queued)
                                                    ↗
generate_content.py  →  RAG tips  →  Excel (dev team polishes)  →  ContentMaterial (is_active=True)
                                                    ↓
                                         WhatsApp / in-app delivery (future)
```

- **Schedule days:** 3, 5, 7, 14, 21, 30 after `first_chat_at`
- **43 niche cases:** T2DM(6), HTN(6), CKD(6), Cardiac(6), PCOS(6), Dyslipidaemia(6), General(6) — one per condition_group × day_offset
- **Two-phase delivery:** (1) RAG→LLM→Excel for dev team review; (2) polished materials sent automatically when `is_active=True`
- **Excel output:** `materials/` directory, one sheet per condition group
- **DB tables:** `content_materials` (generated tips + approval state), `content_delivery_log` (per-patient audit trail)

### MPS Patches (Mac Studio only)

CLaRa was patched to run on Apple MPS instead of CUDA. Patches in:
- `/Users/bing/.cache/huggingface/modules/transformers_modules/compression-16/modeling_clara.py`

When deploying to production Linux + NVIDIA, **revert**:
- `.to('mps')` → `.to('cuda')`
- `torch.backends.mps.is_available()` → `torch.cuda.is_available()`
- `torch.mps.empty_cache()` → `torch.cuda.empty_cache()`
- `bfloat16` can replace `float16`
- Remove `PYTORCH_ENABLE_MPS_FALLBACK=1` env var

### Patient Store Abstraction

```python
class PatientStore(ABC):
    def get_profile(self, patient_id: int) -> dict | None: ...
    def update_supplementary_fields(self, patient_id, updates, source_session_id) -> dict: ...
```
- `LocalPatientStore` is the current implementation (dev only)
- `SUPPLEMENTARY_FIELDS` whitelist prevents extractor from overwriting clinical data
- All extractor writes include provenance metadata (`extractor_metadata` JSON column)

---

## Patient ORM — Current Columns

### Clinical (from hospital, never overwritten by extractor)
`id, client_id, name, ic_number, age, gender, ethnicity, weight_kg, height_cm, conditions, medications, dietary_restrictions, allergies, notes, username, hashed_password`

### Supplementary — v1 (extractor-filled, migrated)
`fluid_intake_ml, alcohol_per_week, supplements, religion, tobacco_status, meals_per_day, snacks_per_day, processed_food_freq, fast_food_freq, self_prepared_freq, caffeine_mg_per_day, sugar_drinks_ml, activity_freq, activity_minutes, activity_intensity, food_avoidance, nutrition_knowledge, readiness_to_change, sodium_awareness, extractor_metadata`

### Supplementary — v2 cardiac (DEPLOYED ✓)
`fat_intake_level, fat_type_sources (JSON), medication_compliance, activity_type (JSON), extractor_food_allergies (JSON), personalization_level`

### Content pipeline (DEPLOYED ✓)
`first_chat_at` — set once on first patient chat, drives the drip schedule.

Tables: `content_materials`, `content_delivery_log`

### WhatsApp (DEPLOYED ✓)
`phone_number` (e.g. `+60123456789`, set via `set_patient_phone` MCP tool), `whatsapp_opted_out` (Boolean, set by replying STOP/BERHENTI to a WhatsApp message).

Table: `chat_messages` (session_id, patient_id, role, content, created_at) — also used for WhatsApp sessions (`session_id=f"whatsapp-{patient_id}"`).

---

## Completed Work (chronological)

| Date | Work |
|------|------|
| May 2026 | Cloudflare tunnels, Option B hybrid pipeline, TopicBoostRetriever |
| May 2026 | v2 cardiac schema (15 extractor fields + 5 DB columns) fully deployed |
| May 2026 | Personalization levels L0–L3 wired end-to-end in all RAG paths |
| May 2026 | CKD + KDOQI 2020 docs ingested; 24,268 chunks enriched with topic metadata |
| May 2026 | Eval harness written: `eval/eval_ragas.py` + `eval/results/` |
| 29 May 2026 | Project moved: `/mnt/ssd` → `/mnt/ext` (T7 Shield 100% full → MEEEE 910GB free) |
| 29 May 2026 | Content drip pipeline: DB migration + `generate_content.py` + `content_scheduler.py` |
| 29 May 2026 | Smoke tests `test_content_pipeline.py` — 3/4 passing (generation dry-run ✓, live test pending) |

---

## Pending Work — in priority order

### 1. ✅ DONE — Run content generation live test
Superseded by the weekly EKA pipeline (§25 of ARCHITECTURE.md). Weeks 22-24 EKA materials generated and approved (63 items, 11 June 2026); one item (id=68) flagged for dietitian review — see `materials/eka_dietitian_review_flags.md`.

### 2. ✅ DONE — Content scheduler cron
Both schedulers are in crontab:
```
0 8 * * * /home/han/miniconda3/bin/python /mnt/ext/bare_NutriChatbot/scripts/content_scheduler.py >> /mnt/ext/bare_NutriChatbot/logs/content_scheduler.log 2>&1
0 6 * * 1 /home/han/miniconda3/bin/python /mnt/ext/bare_NutriChatbot/scripts/weekly_eka_scheduler.py >> /mnt/ext/bare_NutriChatbot/logs/weekly_eka.log 2>&1
```

### 3. ✅ DONE — Add /mnt/ext to /etc/fstab for auto-mount on boot
Added 12 June 2026:
```
UUID=67B2-12E3 /mnt/ext exfat rw,uid=1000,gid=1000,fmask=0000,dmask=0000,allow_utime=0022,iocharset=utf8,errors=remount-ro,nofail 0 0
```
Verified with `sudo mount -fav` → `/mnt/ext : already mounted`.

### 4. ✅ DONE — Persist conversation history to DB
Added 12 June 2026. New `chat_messages` table (`id, session_id, patient_id, role, content, created_at`), created via `scripts/migrate_chat_history.py` (auto-creates the table — no ALTER needed).
- `database.add_chat_message()` / `get_chat_history()` / `clear_chat_history()` — CRUD helpers
- `chain_factory.DBChatMessageHistory` replaces `InMemoryChatMessageHistory` for the legacy LangChain path (`RunnableWithMessageHistory` reads/writes via this class automatically)
- Active Option B path (`rag.get_rag_response`): `_load_history_text()` loads the last 12 messages and injects them as a "## Conversation So Far" block into the Qwen prompt; `_persist_turn()` saves the new user/assistant exchange after generation. Same wiring added to the CLaRa-primary and agent-tool paths.
- `get_rag_response()` now takes an optional `patient_id` param (passed through from `website_chat_router.py` and `mcp_server.py`) so rows can be filtered per patient
- `session_id == "keepalive"` (used by the Cloudflare keep-alive cron) is excluded from history load/persist to avoid polluting the table
- Verified end-to-end: a second turn referencing "what we just discussed" correctly pulled context from turn 1, surviving a full `systemctl restart nutribot`

### 5. ✅ DONE (inbound webhook) — WhatsApp integration
Added 12 June 2026. `whatsapp_router.py`, mounted under `/chat` (no X-API-Key — auth is via provider signature/verify-token):
- `POST /chat/whatsapp` — Twilio inbound webhook (form-encoded). Validates `X-Twilio-Signature` via `twilio.request_validator.RequestValidator` (skipped with a warning if `TWILIO_AUTH_TOKEN` is unset). Replies with empty TwiML; the real reply is sent async via the REST API.
- `GET /chat/whatsapp/meta` — Meta Cloud API verification handshake (`hub.verify_token` checked against `META_VERIFY_TOKEN`).
- `POST /chat/whatsapp/meta` — Meta Cloud API inbound webhook (JSON).
- Both providers resolve the sender via `database.get_patient_by_phone()` / `normalise_phone_number()` (strips `whatsapp:` prefix, spaces, dashes; ensures `+` prefix — `+60123456789`).
- STOP/BERHENTI and START/MULA set/clear `Patient.whatsapp_opted_out` (new column, migrated via `scripts/migrate_whatsapp_columns.py`). Opt-out only gates scheduled content (`_send_patient_content` in `mcp_server.py` now checks it before sending) — direct chat replies still work.
- Normal messages run in a `BackgroundTask` (`_process_and_reply`): calls `rag.get_rag_response()` with `session_id=f"whatsapp-{patient_id}"` (so conversation history from item 4 carries over), runs the extractor in the background too, truncates replies to 1500 chars, and sends via `whatsapp.send_message()`.
- Outbound delivery (`whatsapp.py` formatters, `_send_patient_content` dispatch, `phone_number`/`set_patient_phone`) was already built in a prior session.
- **Still pending**: set `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` (or `META_WHATSAPP_TOKEN` / `META_WHATSAPP_PHONE_ID` / `META_VERIFY_TOKEN`) in `.env`, configure the webhook URL with the provider (`https://nutribot.computationalrd.com/chat/whatsapp`), and link patient phone numbers via `set_patient_phone` (MCP tool).

### 6. ✅ DONE — Test bilingual extractor end-to-end
Tested 12 June 2026 against patient 3 (Kavitha, PCOS/Insulin Resistance, previously empty supplementary fields), `session_id=bm-extractor-test-1`. Sent:
> "Saya minum air kira-kira 6 gelas sehari. Saya tidak merokok. Saya bersenam berjalan kaki 3 kali seminggu, selama 30 minit setiap kali, agak senang je."

RAG replied in English referencing "6 glasses of water" and "walking" — correctly understood the BM input. Background extractor then wrote 6 fields, all validated correctly:
- `fluid_intake_ml: 1500` (6 gelas × 250mL)
- `tobacco_status: "Never smoked"` (tidak merokok)
- `activity_freq: "3 times a week"` (3 kali seminggu)
- `activity_minutes: 30` (30 minit)
- `activity_types: ["walking"]` (berjalan kaki)
- `activity_intensity: "light"` (agak senang je)

`extractor_metadata` populated correctly for all 6 fields with `source_session_id: "bm-extractor-test-1"` and matching timestamps.

**Note**: request was sent to `localhost:8000` directly — the public Cloudflare URL timed out client-side (>100s) on the same request, consistent with the existing cold-start/long-request behaviour noted elsewhere. The `[Extractor] Ollama call failed: Connection aborted/Read timed out` errors seen frequently in `/var/log/nutribot.log` (from the 4-minute keepalive cron's background extractor calls contending with Ollama) are a pre-existing issue, unrelated to this fix — extractor failures there are silently swallowed (`return {}`) and don't affect the user-facing reply.

### 7. ✅ DONE — Cloudflare keep-alive cron
Already in crontab, runs every 4 minutes:
```
*/4 * * * * curl -s -X POST -H "Content-Type: application/json" \
  -H "X-API-Key: nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3" \
  -d '{"question":"ping","patient_id":1,"session_id":"keepalive"}' \
  --max-time 90 https://nutribot.computationalrd.com/chat/get_response_sync > /dev/null 2>&1
```

### 8. ✅ DONE (scaffold) — Replace LocalPatientStore with RemotePatientStore
Added 12 June 2026. Hospital API spec doesn't exist yet, so built a generic
REST scaffold + mock server that's testable today and adjustable once the
real spec arrives:
- `patient_store.get_patient_store()` — factory used by both `website_chat_router.py`
  and `whatsapp_router.py`. Returns `RemotePatientStore` if `HOSPITAL_API_URL` is set,
  else `LocalPatientStore` (current default — no env var set, so dev/staging unaffected).
- `remote_patient_store.py` — `RemotePatientStore(PatientStore)`. Assumed placeholder
  contract (flat JSON, not FHIR — adjust when the real spec is known):
  - `GET {base_url}/patients/{patient_id}` → 200 flat profile dict (same shape as
    `LocalPatientStore.get_profile()`) or 404
  - `PATCH {base_url}/patients/{patient_id}/supplementary` with
    `{"updates": {...}, "source_session_id": "..."}` → 200 `{"applied": {...}}` or 404
  - Env vars: `HOSPITAL_API_URL`, `HOSPITAL_API_KEY` (Bearer token), `HOSPITAL_API_TIMEOUT_S` (default 10)
  - `_to_profile_dict()`, `_PATIENT_PATH`, `_SUPPLEMENTARY_PATH` are the marked
    adaptation points for the real hospital schema (possibly FHIR Patient/Observation)
- `mock_hospital_api.py` — standalone FastAPI app implementing the contract above
  with an in-memory patient (seeded with patient 1's shape), for local testing.
- `scripts/test_remote_patient_store.py` — spins up the mock API on port 8500 and
  exercises `RemotePatientStore` end-to-end (get_profile found/404, update with
  allowed/rejected fields, persistence check). All assertions pass.
- **Known gap**: `_resolve_patient_profile` (website) and `_process_and_reply`
  (WhatsApp) still build the RAG profile via `db.patient_to_profile_dict(patient)`
  directly from the local DB, not via `patient_store.get_profile()`. Only the
  *write* path (`update_supplementary_fields`) is fully routed through
  `patient_store` so far — full read-path swap-over is future work once real
  hospital endpoints exist.
- **Still pending (real deployment)**: hospital provides actual API spec → update
  `_PATIENT_PATH` / `_SUPPLEMENTARY_PATH` / `_to_profile_dict()` in
  `remote_patient_store.py`, then set `HOSPITAL_API_URL` (and `HOSPITAL_API_KEY`
  if needed) in `.env` on the production server.

### 9. Re-ingest 3 missing PDFs
- AHA 2021 Dietary Guidelines
- Buku MDG Senaman
- LE8 BP
Run `build_base_db.py` after adding to `/home/han/documents_clean/`

### 10. Evaluation methodology + architecture + fine-tuning roadmap
See `docs/eval_and_roadmap.md` (written 2026-07-16). Covers: fixing `eval_ragas.py`'s dead-code eval target, replacing keyword-match checks with a directional/clinical-correctness judge (the "banana for CKD" test case currently passes on keyword match despite the stored answer being clinically wrong), a systematic per-condition contraindication test matrix, architecture resilience fixes (no LLM-generation fallback, untracked MPS patch, dead `chain_factory.py` path), and a plan to LoRA/QLoRA fine-tune `qwen2.5:32b` directly, targeted at whatever the expanded eval shows as the most common failure categories.

**Part A implemented 2026-07-16** (evaluation methodology — code changes live in `eval/eval_ragas.py`, `eval/test_rag.py`, `eval/test_extractor.py`, `scripts/eval_history.py`, `pytest.ini`):
- `eval_ragas.py` now calls `rag.get_rag_response()` (the real Option B pipeline) instead of the dead `chain_factory` legacy chain.
- `eval/test_rag.py` grew from 10 to 34 cases: a systematic per-condition contraindication matrix (25 cases use the new `judge_stance()` LLM-judge check — classifies the answer's actual RESTRICT/PERMIT/MODERATE stance instead of trusting keyword presence), 4 bilingual (BM) cases, and L1/L2 personalization coverage (previously only L3 was checked).
- `scripts/eval_history.py` appends `{date, git_commit, passed/failed, category_breakdown}` to a JSONL log per run — `python scripts/eval_history.py --results eval/results/rag.json --suite rag` — instead of the old overwrite-only `results/*.json` snapshots.
- Both suites are now pytest-collectible (`pytest eval/test_rag.py -m smoke`) in addition to their existing CLI runners.
- **Still pending**: add this cron entry on the RTX 3050 once it's back up (couldn't be installed remotely — the box was down during this session, see Known Issues):
  ```
  0 3 * * * cd /mnt/ext/bare_NutriChatbot && /home/han/miniconda3/bin/python eval/test_rag.py --smoke --out eval/results/rag_smoke.json >> logs/eval_nightly.log 2>&1 && /home/han/miniconda3/bin/python scripts/eval_history.py --results eval/results/rag_smoke.json --suite rag_smoke >> logs/eval_nightly.log 2>&1
  ```
  (Uses the CLI runner, not `pytest` — the repo's root `conftest.py` forces `DATABASE_URL` to a sqlite in-memory DB for other test suites, which would break this suite's real Postgres/pgvector dependency if run via `pytest` in cron; the CLI runner calls its own `load_dotenv()` directly and isn't affected.)
- The error-leakage bug is also fixed: `stream_rag_response()` in `website_chat_router.py` no longer yields raw exception text to the patient-facing chat — it logs the real exception server-side and yields a generic apology instead.

**Part B implemented 2026-07-16** (architecture resilience — code changes live in `llm.py`, `rag.py`; scope trimmed per explicit decision not to add an OpenAI generation fallback):
- Timeout budget cut from a ~300s worst-case stack to ~90s: `CLARA_COMPRESS_TIMEOUT_S=40` + `OLLAMA_GENERATE_TIMEOUT_S=50` (both env-overridable in `llm.py`), comfortably under the ~100s client-observed Cloudflare timeout (item 6 above) — a dead backend now fails fast instead of the server grinding for minutes on a request the client already gave up on. `CLARA_GENERATE_TIMEOUT_S=90` for the single-call CLaRa-primary path.
- Removed the dead legacy LangChain path from `rag.py` (confirmed `create_conversational_chain` had exactly one remaining caller — that branch — after Part A repointed `eval_ragas.py`). `get_rag_response()` now raises a clear `EnvironmentError` if none of `USE_AGENT_TOOLS`/`USE_CLARA`/`USE_CLARA_COMPRESS` are set, instead of silently falling through to dead code. Also removed `identify_target_disease()`, which became dead code itself once its only call site (inside the removed branch's profile-less path) was gone — it was a wasted extra LLM round-trip on every profile-less request that fed a value nothing downstream used.
- `chain_factory.py` itself is untouched — `get_system_template()` is still used by `finetune/generate_training_data.py`.
- **Explicitly not done, per user decision**: no OpenAI fallback was wired into `call_ollama_generate`'s call site — a full Mac Studio/tunnel outage still means 100% generation failure. This was Part B item 1 in the roadmap doc; deliberately skipped, not forgotten.
- The MPS patch is now tracked: `patches/mps_cuda_patch.py` + `patches/README.md`. Since the real `modeling_clara.py` lives only on the Mac Studio's HuggingFace cache (never accessible from this session), this is a verified apply/revert script (mechanical text substitutions matching the exact changes documented above) rather than a literal `.patch` diff against content nobody here has read — a hand-authored diff against unseen content would have been worse than nothing. Verified via `--demo` mode against a built-in sample snippet (no real file needed to prove the substitution logic is correct). Still manual: bfloat16 dtype choice (optional) and removing `PYTORCH_ENABLE_MPS_FALLBACK=1` from the Mac Studio's LaunchDaemon (an env var, not a source-file line) — both documented in `patches/README.md`. The IP ownership flag remains documentation-only (no action needed from Claude).

**Part C implemented 2026-07-16** (fine-tuning scaffolding — code changes live in `eval/test_rag.py`, `finetune/generate_training_data.py`, `scripts/compare_eval_runs.py`, `finetune/QWEN_FINETUNE.md`):
- `eval/test_rag.py`'s `run_case()` now also returns the `contraindication_check` dict for each case (food/condition/acceptable_stances), so a failing case's targeting metadata survives into results JSON without needing to re-cross-reference `CASES`.
- `finetune/generate_training_data.py` gained `--focus-results <path>` + `--focus-weight <n>`: reads a `test_rag.py --out` results JSON, extracts every distinct FAILING contraindication combo, and generates `--focus-weight` extra synthetic ADIME conversations per combo that explicitly demonstrate the correct RESTRICT/MODERATE/PERMIT stance (via a new `FOCUS_ADDENDUM` prompt block) — oversampling the model's known weak spots instead of pure uniform random sampling. The stance-picking logic (`_target_stance`) and combo extraction (`load_focus_combos`) were verified against a synthetic results JSON matching the real output shape (correctly excludes passing cases and no-check cases, dedupes, and picks the clinically conservative stance when multiple are acceptable) — this Mac Mini has no `openai`/`dotenv` packages installed, so the full module couldn't be executed end-to-end here, only its pure logic.
- `scripts/compare_eval_runs.py` (new): compares a baseline vs. candidate `test_rag.py --out` results JSON, reports per-case regressions/improvements and per-tag pass rates, and prints a PROMOTE / DO NOT PROMOTE verdict (exit code 0/1) — a candidate is only promotion-worthy with zero regressions and at least one fix. Verified against synthetic baseline/candidate pairs covering both a clean-improvement case (correctly PROMOTEs) and a mixed-improvement-with-regression case (correctly blocks promotion).
- `finetune/QWEN_FINETUNE.md` (new): documents the recommended QLoRA config for fine-tuning `qwen2.5:32b` directly (not the existing Gemma-3 `Modelfile` track) — base model, Unsloth framework, starting hyperparameters, the merge/quantize/deploy pipeline, and how the pieces above wire together end-to-end. Documentation only — actually running a 32B training job needs real GPU time this session didn't have.
- **Not built**: the actual LoRA/QLoRA training run itself (needs the Mac Studio or a cloud GPU); the embeddings closed-loop (Part C item 4) is noted as blocked on Part A's retrieval-quality visibility gap, which was never closed (`vector_store.py`'s `[TopicBoost]` scores are still print-only, no persisted signal).

---

## Service Management

### RTX 3050 Server

```bash
# Bot
sudo systemctl status nutribot
sudo systemctl restart nutribot
tail -f /var/log/nutribot.log

# Cloudflare tunnel (public URL + portfolio)
sudo systemctl status cloudflared
sudo cat /etc/cloudflared/config.yml

# Postgres
sudo docker ps | grep pgvector
sudo docker inspect pgvector-nutribot --format='{{.HostConfig.RestartPolicy.Name}}'

# Check all services
sudo systemctl status nutribot cloudflared docker

# Mount MEEEE drive if not auto-mounted
sudo mount -t exfat -o rw,uid=1000,gid=1000,fmask=0000,dmask=0000,allow_utime=0022,iocharset=utf8,errors=remount-ro /dev/sdb1 /mnt/ext
```

### Mac Studio (SSH as bing, or AnyDesk as care-uitm)

```bash
# Check all LaunchDaemons
sudo launchctl list | grep -E "nutribot|cloudflare"

# CLaRa
sudo launchctl kickstart -k system/com.nutribot.clara
tail -f /Users/bing/clara.log

# Ollama
sudo launchctl kickstart -k system/com.nutribot.ollama
tail -f /Users/bing/ollama.log

# Cloudflare (private tunnels for CLaRa + Ollama)
sudo launchctl kickstart -k system/com.cloudflare.cloudflared
tail -f /Users/bing/cloudflared.log

# Test local services
curl -s -o /dev/null -w "CLaRa: %{http_code}\n" http://localhost:8001/docs
curl -s -o /dev/null -w "Ollama: %{http_code}\n" http://localhost:11434/api/tags
```

### End-to-end smoke test

```bash
curl -X POST https://nutribot.computationalrd.com/chat/get_response_sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3" \
  -d '{"question":"What should I eat for breakfast?","patient_id":2,"session_id":"smoke-test"}'
```

Healthy response: clinical answer mentioning CKD + hypertension restrictions (low K, low P, fluid limit, low Na). Takes 30–60s first call, 10–30s warm.

### Testing CLaRa/Ollama directly (RTX 3050 down)

If the RTX 3050 is down, the public bot URL and the smoke test above will fail — but CLaRa and Ollama on the Mac Studio can still be checked directly from **any machine with internet access** (no LAN/Tailscale/SSH to the Mac Studio needed), since their tunnel hostnames are served by the Mac Studio's own `cloudflared`, independent of the RTX 3050:

```bash
# CLaRa (Mac Studio :8001, via its own tunnel)
curl -s -o /dev/null -w "CLaRa: %{http_code}\n" https://clara-internal-x9k2.computationalrd.com/docs

# Ollama (Mac Studio :11434, via its own tunnel) — lists loaded models
curl -s https://ollama-internal-x9k2.computationalrd.com/api/tags

# Public bot URL, for contrast — will show the RTX 3050 outage
curl -s -o /dev/null -w "Public bot: %{http_code}\n" https://nutribot.computationalrd.com/docs
```

Last verified **2026-07-16**: CLaRa → `200`, Ollama → `200` (models loaded: `qwen2.5:32b`, `llama3.1:8b`), public bot → `530` (Cloudflare origin/DNS error — confirms the outage is isolated to the RTX 3050's tunnel, Mac Studio unaffected).

**Real inference test (proves the models actually generate, not just that the HTTP server is up)** — payload shapes match `llm.py`'s `call_ollama_generate` / `call_clara_api` / `call_clara_compress`:

```bash
# Ollama — real generation via qwen2.5:32b
curl -s -X POST https://ollama-internal-x9k2.computationalrd.com/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:32b","prompt":"Reply with exactly one short sentence confirming you are online.","stream":false,"options":{"temperature":0.3,"num_predict":50}}'

# CLaRa — /generate
curl -s -X POST https://clara-internal-x9k2.computationalrd.com/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Reply with exactly one short sentence confirming you are online.","max_tokens":50,"temperature":0.3,"documents":[]}'

# CLaRa — /compress (the actual Option B pipeline call)
curl -s -X POST https://clara-internal-x9k2.computationalrd.com/compress \
  -H "Content-Type: application/json" \
  -d '{"documents":["Patients with chronic kidney disease should limit potassium intake to 2000-3000mg per day and avoid high-potassium foods such as bananas, oranges, and potatoes."],"question":"What should I eat for breakfast?","patient_context":"CKD Stage 3, Hypertension","max_tokens":300,"temperature":0.1}'
```

Results, verified **2026-07-16** from a Mac Mini (not RTX 3050, not the Mac Studio itself — i.e. from any machine on the internet):
- Ollama → `"I am online and ready to assist."` (~16s, mostly cold model-load time)
- CLaRa `/generate` → `"I'm online and ready to help."` (~16s)
- CLaRa `/compress` → full structured digest (RECOMMENDATIONS / CAUTIONS / KEY NUMBERS) correctly reflecting the CKD + hypertension test input — confirms the compression step of the active RAG pipeline is working, not just reachable.

Note: this only exercises CLaRa/Ollama in isolation. The full `rag.py` retrieval pipeline additionally needs PGVector/Postgres, which lives on the RTX 3050 — so this local test proves the *models* are healthy but doesn't stand in for a full end-to-end RAG smoke test while the RTX 3050 is down.

---

## Content Pipeline Quick Reference

```bash
cd /mnt/ext/bare_NutriChatbot

# Generate all content for client 4 (calls Ollama, takes ~20 min)
python scripts/generate_content.py --client-id 4

# Generate one group only (faster test)
python scripts/generate_content.py --client-id 4 --group General --day 3

# Dry run (no LLM call, no DB write — just shows niche lookup)
python scripts/generate_content.py --client-id 4 --dry-run

# Daily scheduler (normally run by cron)
python scripts/content_scheduler.py
python scripts/content_scheduler.py --dry-run
python scripts/content_scheduler.py --dry-run --as-of 2026-06-01

# Tests
python scripts/test_content_pipeline.py                    # all tests (dry-run mode)
python scripts/test_content_pipeline.py --test migration   # DB tables check only
python scripts/test_content_pipeline.py --seed-dates       # set first_chat_at on demo patients
python scripts/test_content_pipeline.py --reset-dates      # clear first_chat_at
NUTRIBOT_TEST_LIVE=1 python scripts/test_content_pipeline.py --test generation  # calls Ollama
```

---

## Known Issues

| Issue | Impact | Mitigation |
|-------|--------|------------|
| CLaRa sometimes recommends bananas to CKD patients | Clinical risk | Prompt engineering, more training data |
| Mac Studio SSH via `studio-ssh.mrbing.dev` broken | Can't SSH as bing directly | Use AnyDesk as care-uitm, or local LAN |
| exFAT on /mnt/ext breaks Python venvs | Must use miniconda, not .venv | Use /home/han/miniconda3/bin/python |
| UiTM network blocks Tailscale | Can't use Tailscale on Mac Studio | Replaced with Cloudflare tunnels |
| T7 Shield (/mnt/ssd) 100% full | Cannot write new files there | Project moved to MEEEE (/mnt/ext) |
| RTX 3050 down as of 2026-07-16 (public `nutribot.computationalrd.com` → Cloudflare 530) | Full bot pipeline untestable via public URL | Mac Studio's CLaRa/Ollama confirmed independently reachable via their own tunnel — see "Testing CLaRa/Ollama directly" under Service Management |

---

## Document / Knowledge Base

Clinical PDFs ingested: 58 docs + CKD CPG + KDOQI 2020 = 24,268 chunks in PGVector `base_knowledge`.
Sources: Malaysian CPGs, NICE guidelines, WHO nutrition guidance, MDGV, KDOQI.
Location on server: `/home/han/documents_clean/`
Ingestion script: `build_base_db.py` (run with `BASE_DOCS_DIR=/home/han/documents_clean python build_base_db.py`)

Chunk enrichment: all chunks have `doc_keywords`, `doc_topics`, `doc_topic_summary`, `doc_language` metadata.
Enrichment script: `scripts/enrich_v1_with_keywords.py --mapping data/encpt/doc_keyword_mapping.json`

---

## eNCPT Schema

Based on eNCPT 2020 (Academy of Nutrition and Dietetics).
Current version: **v2.0-cardiac** (34 fields, EN + BM, cardiac-focused tiers).
Source: `data/encpt/build_curated_schema.py` — edit this, then run it to regenerate the JSON.

Pending dietitian review: `data/encpt/encpt_curated.md` (send to supervising dietitian).

---

## Contacts & Context

- Developer: Lee Yean Han (han on RTX 3050 server, the main codebase owner)
- Mac Studio owner: bing / CAREs-Mac-Studio (client-provided hardware)
- Supervising dietitian: provided cardiac priority schema, reviewing eNCPT field list
- Client: UITM / hospital (sungaibuloh.uitm.edu.my network)
- Deployment target: Single Linux + NVIDIA GPU server (production, not yet provisioned)
- IP ownership: Confirm contract terms before SaaS expansion — work-for-hire vs license-back TBD

---

## Quick Reference — Python Paths

| Use case | Command |
|----------|---------|
| Run the bot locally | `/home/han/miniconda3/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000` |
| Run extractor test | `/home/han/miniconda3/bin/python -c "from extractor import extract_from_message; ..."` |
| Run v2 migration | `/home/han/miniconda3/bin/python scripts/migrate_v2.py` |
| Run content pipeline migration | `/home/han/miniconda3/bin/python scripts/migrate_content_pipeline.py` |
| Run chat history migration | `/home/han/miniconda3/bin/python scripts/migrate_chat_history.py` |
| Run WhatsApp columns migration | `/home/han/miniconda3/bin/python scripts/migrate_whatsapp_columns.py` |
| Run build schema | `/home/han/miniconda3/bin/python data/encpt/build_curated_schema.py` |
| Check DB | `/home/han/miniconda3/bin/python -c "import database as db; ..."` |
| Generate content | `/home/han/miniconda3/bin/python scripts/generate_content.py --client-id 4` |
| Test RemotePatientStore (mock hospital API) | `/home/han/miniconda3/bin/python scripts/test_remote_patient_store.py` |

---

## Git

Repo: on GitHub (main branch).
The Mac Studio has a clone at `/Users/bing/Desktop/clara_lyh/clara-nutri/` (CLaRa inference only — not the bot codebase).
**The bot codebase at `/mnt/ext/bare_NutriChatbot/` is the source of truth** (moved from `/mnt/ssd` on 29 May 2026).
