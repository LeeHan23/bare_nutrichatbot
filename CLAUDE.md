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
├── patient_store.py          # PatientStore ABC + SUPPLEMENTARY_FIELDS whitelist
├── local_patient_store.py    # LocalPatientStore (dev/staging, wraps SQLAlchemy)
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
│   └── test_extractor_v2.py         # Extractor v2 test cases
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

### 6. Test bilingual extractor end-to-end
- Send a Malay-language chat message through the public URL
- Verify extractor captures fields correctly in BM
- Check `extractor_metadata` is populated with correct provenance

### 7. ✅ DONE — Cloudflare keep-alive cron
Already in crontab, runs every 4 minutes:
```
*/4 * * * * curl -s -X POST -H "Content-Type: application/json" \
  -H "X-API-Key: nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3" \
  -d '{"question":"ping","patient_id":1,"session_id":"keepalive"}' \
  --max-time 90 https://nutribot.computationalrd.com/chat/get_response_sync > /dev/null 2>&1
```

### 8. Replace LocalPatientStore with RemotePatientStore
- Hospital/university server will host patient DB
- Implement `RemotePatientStore(PatientStore)` that calls their REST/FHIR API
- Swap in `website_chat_router.py` by changing one line:
  `patient_store = RemotePatientStore(base_url=os.getenv("HOSPITAL_API_URL"))`

### 9. Re-ingest 3 missing PDFs
- AHA 2021 Dietary Guidelines
- Buku MDG Senaman
- LE8 BP
Run `build_base_db.py` after adding to `/home/han/documents_clean/`

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

---

## Git

Repo: on GitHub (main branch).
The Mac Studio has a clone at `/Users/bing/Desktop/clara_lyh/clara-nutri/` (CLaRa inference only — not the bot codebase).
**The bot codebase at `/mnt/ext/bare_NutriChatbot/` is the source of truth** (moved from `/mnt/ssd` on 29 May 2026).
