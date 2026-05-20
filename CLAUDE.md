# Nutribot — Claude Code Handover Document

## Project Overview

A distributed AI-powered nutrition chatbot for cardiac patients, built for a Malaysian hospital/university client. Uses a split architecture across two machines. The system provides personalized dietary advice using RAG (Retrieval-Augmented Generation) via CLaRa-7B, with dynamic patient profile collection via an LLM extractor.

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
/mnt/ssd/bare_NutriChatbot/          ← main codebase (exFAT, broken venv)
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

---

## Repository Structure

```
/mnt/ssd/bare_NutriChatbot/
├── app.py                    # FastAPI app entry point, demo UI
├── rag.py                    # RAG pipeline (CLaRa primary, Ollama orchestration)
├── llm.py                    # LLM abstraction (CLARA_BASE_URL, OLLAMA_BASE_URL from .env)
├── chain_factory.py          # LangChain LCEL chain, InMemoryChatMessageHistory
├── database.py               # SQLAlchemy ORM — Patient, ApiClient, User models
├── dependencies.py           # FastAPI dependencies (X-API-Key auth, DB session)
├── vector_store.py           # PGVector hybrid retriever, LoRA embedding model
├── embeddings.py             # Embedding utilities (BAAI/bge-m3 + LoRA)
├── website_chat_router.py    # /chat/get_response (streaming) + /chat/get_response_sync
├── admin_router.py           # Admin API routes
├── client_portal_router.py   # Client-facing portal routes
├── mcp_server.py             # MCP server for Claude Desktop integration
├── patient_store.py          # PatientStore ABC + SUPPLEMENTARY_FIELDS whitelist
├── local_patient_store.py    # LocalPatientStore (dev/staging, wraps SQLAlchemy)
├── extractor.py              # LLM-based profile extractor (qwen2.5:32b via Ollama)
├── document_manager.py       # Document upload/management
├── process_client_docs.py    # Client document ingestion into vector store
├── image_handler.py          # Image upload and processing
├── patient_app.html          # Patient-facing HTML UI
├── build_base_db.py          # Ingestion script for clinical PDFs into PGVector
├── seed_patients.py          # Seeds mock patients into local DB
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
│   ├── migrate_v2.py         # v2 supplementary fields DB migration
│   ├── database_patch.py     # Ad-hoc DB patch script
│   └── test_extractor_v2.py  # Extractor v2 test cases
├── finetune/
│   ├── generate_training_data.py         # Synthetic ADIME training data generator
│   ├── generate_embedding_training_data.py
│   ├── finetune_embeddings.py            # LoRA embedding fine-tuning
│   ├── export_pairs_csv.py
│   ├── colab_finetune.ipynb
│   └── Modelfile                         # Ollama Modelfile
└── eval/
    ├── eval_ragas.py          # RAGAs evaluation harness
    └── eval_dataset.json      # Evaluation dataset
```

---

## Environment Variables (.env on RTX 3050)

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nutribot
PGVECTOR_URL=postgresql://postgres:postgres@localhost:5432/nutribot
CLARA_BASE_URL=https://clara-internal-x9k2.computationalrd.com
OLLAMA_BASE_URL=https://ollama-internal-x9k2.computationalrd.com
OLLAMA_MODEL=qwen2.5:32b
USE_CLARA=true
USE_OLLAMA=true
```

---

## Patient Database (Mock / Dev)

5 synthetic Malaysian patients in local Postgres:

| ID | Name | Conditions | Level |
|----|------|------------|-------|
| 1 | Ahmad Fadzillah bin Roslan | Type 2 Diabetes, Hypertension | L2 |
| 2 | Lim Siew Ching | CKD Stage 3, Hypertension | L2 |
| 3 | Kavitha a/p Subramaniam | PCOS, Insulin Resistance | L1 |
| 4 | Mohd Hafizuddin bin Salleh | Dyslipidaemia, Obesity Class I | L1 |
| 5 | Tan Wei Loong | Hypertension, Hypercholesterolaemia, T2DM | L2 |
| 6 | Nurul Ain binti Zulkifli | None (general wellness) | L0 |
| 7 | Rajendran a/l Muthu | Post-CABG, Heart Failure (EF 35%), T2DM, HTN, CKD Stage 4 | L3 |

**Production note:** All patient data in production must live on the hospital/university server. Local DB is dev/staging only. The `PatientStore` abstraction in `patient_store.py` is the designed swap point — implement `RemotePatientStore(PatientStore)` when the hospital API is available.

---

## Key Design Decisions

### RAG Pipeline
- **CLaRa-7B** (compression-16, Stage 2 Instruct) is the primary RAG model. It uses compressed-context retrieval — faster and better on domain-specific content than raw LLMs.
- **qwen2.5:32b via Ollama** handles orchestration tasks: `identify_target_disease()`, the extractor, and fallback.
- When `patient_id` is provided in the request, the patient's clinical profile is loaded from DB and injected into the CLaRa prompt. The LLM never needs to guess the condition.
- **Embedding:** BAAI/bge-m3 + LoRA adapter at `/home/han/models/embedding_lora`
- **Vector store:** 24,268 clean chunks from 58 clinical PDFs (Malaysian CPGs + international guidelines). Deduped and junk-filtered.

### MPS Patches (Mac Studio only)
CLaRa was patched to run on Apple MPS instead of CUDA. These patches are in:
- `/Users/bing/.cache/huggingface/modules/transformers_modules/compression-16/modeling_clara.py`
- Source: `/Users/bing/Desktop/clara_lyh/clara-nutri/` (the actual api.py)

When deploying to production Linux + NVIDIA, **revert** these patches:
- `.to('mps')` → `.to('cuda')`
- `torch.backends.mps.is_available()` → `torch.cuda.is_available()`
- `torch.mps.empty_cache()` → `torch.cuda.empty_cache()`
- `bfloat16` can replace `float16` (CUDA supports bfloat16)
- Remove `PYTORCH_ENABLE_MPS_FALLBACK=1` env var

### Patient Store Abstraction
```python
class PatientStore(ABC):
    def get_profile(self, patient_id: int) -> dict | None: ...
    def update_supplementary_fields(self, patient_id, updates, source_session_id) -> dict: ...
```
- `LocalPatientStore` is the current implementation (dev only)
- `SUPPLEMENTARY_FIELDS` whitelist in `patient_store.py` prevents extractor from overwriting clinical data
- All extractor writes include provenance metadata (`extractor_metadata` JSON column)

---

## Patient ORM — Current Columns

### Clinical (from hospital, never overwritten by extractor)
`id, client_id, name, ic_number, age, gender, ethnicity, weight_kg, height_cm, conditions, medications, dietary_restrictions, allergies, notes, username, hashed_password`

### Supplementary — v1 (extractor-filled, already migrated)
`fluid_intake_ml, alcohol_per_week, supplements, religion, tobacco_status, meals_per_day, snacks_per_day, processed_food_freq, fast_food_freq, self_prepared_freq, caffeine_mg_per_day, sugar_drinks_ml, activity_freq, activity_minutes, activity_intensity, food_avoidance, nutrition_knowledge, readiness_to_change, sodium_awareness, extractor_metadata`

### Supplementary — v2 cardiac (PENDING MIGRATION)
```sql
ALTER TABLE patients ADD COLUMN fat_intake_level VARCHAR;
ALTER TABLE patients ADD COLUMN fat_type_sources JSON DEFAULT '[]'::json;
ALTER TABLE patients ADD COLUMN medication_compliance VARCHAR;
ALTER TABLE patients ADD COLUMN activity_type JSON DEFAULT '[]'::json;
ALTER TABLE patients ADD COLUMN extractor_food_allergies JSON DEFAULT '[]'::json;
```
**Run:** `python /mnt/ssd/bare_NutriChatbot/scripts/migrate_v2.py`

### Pending (not yet added)
`personalization_level` (VARCHAR: L0/L1/L2/L3 — see below)

---

## Pending Work — in priority order

### 1. Deploy v2 cardiac schema (IMMEDIATE)
Files generated, deployment not yet confirmed. Steps:

```bash
cd /mnt/ssd/bare_NutriChatbot

# Step 1: Replace build_curated_schema.py with v2 content, then:
python data/encpt/build_curated_schema.py
python data/encpt/json_to_md.py data/encpt/encpt_curated.json data/encpt/encpt_curated.md

# Step 2: Replace extractor.py with v2 (15 fields, BM support, allowed_values)

# Step 3: Add to database.py Patient class (after sodium_awareness line):
#   fat_intake_level = Column(String, nullable=True)
#   fat_type_sources = Column(JSON, default=list)
#   medication_compliance = Column(String, nullable=True)
#   activity_type = Column(JSON, default=list)
#   extractor_food_allergies = Column(JSON, default=list)

# Step 4: Add new fields to SUPPLEMENTARY_FIELDS in patient_store.py

# Step 5: Run migration
python scripts/migrate_v2.py

# Step 6: Test extractor
python -c "
from extractor import extract_from_message
print(extract_from_message('Saya makan nasi lemak setiap hari', {}))
print(extract_from_message('I forgot my evening blood pressure pill sometimes', {}))
"

# Step 7: Restart bot
sudo systemctl restart nutribot
```

### 2. Add personalization_level to Patient model (NEXT)
Personalization levels (from dietitian, May 2026):

| Level | Patient profile | Content scope |
|-------|----------------|---------------|
| L0 | No risk, no history, no limitations | Full spectrum including vigorous activity, performance goals |
| L1 | Emerging/moderate risk (early HTN, elevated BMI), no functional limits | Structured, safety-aware, moderation, do/don't boundaries |
| L2 | Established conditions, physical limitations, higher CV risk | Low-intensity, symptom monitoring, strict stop conditions |
| L3 | High clinical risk, recent cardiac events, disability | Medical oversight only, emergency education, minimal activity |

**Implementation needed:**
- Add `personalization_level = Column(String, nullable=True)` to Patient model
- Add migration: `ALTER TABLE patients ADD COLUMN personalization_level VARCHAR`
- Update `patient_to_profile_dict()` in `database.py` to include `personalization_level`
- Update CLaRa prompt in `rag.py` to inject level-specific instructions
- Assign levels to 7 mock patients: P1=L2, P2=L2, P3=L1, P4=L1, P5=L2, P6=L0, P7=L3 ✓ Done

### 3. Test the bilingual extractor end-to-end
- Send a Malay-language chat message through the public URL
- Verify extractor captures fields correctly
- Check `extractor_metadata` is populated with correct provenance

### 4. Build evaluation harness (before more extractor changes)
```
eval/
├── test_extractor.py    # 20 test messages with expected extractions
└── test_rag.py          # 10 nutrition questions with expected answer themes
```
Critical: without evals, future changes may regress silently.

### 5. Persist conversation history to DB
Currently `InMemoryChatMessageHistory` in `chain_factory.py` — history lost on bot restart. Required for WhatsApp delivery. Needs a `chat_messages` table.

### 6. Cloudflare keep-alive cron (IMMEDIATE)
First request after long idle can exceed Cloudflare's 100s timeout (model cold-start). Add to crontab on RTX 3050:
```
*/4 * * * * curl -s -X POST -H "Content-Type: application/json" \
  -H "X-API-Key: nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3" \
  -d '{"question":"ping","patient_id":1,"session_id":"keepalive"}' \
  --max-time 90 https://nutribot.computationalrd.com/chat/get_response_sync > /dev/null 2>&1
```

### 7. WhatsApp integration
- Twilio or Meta API webhook → `/chat/whatsapp` endpoint
- Phone number → patient_id mapping table
- Requires conversation history persistence (item 5 above)

### 8. Replace LocalPatientStore with RemotePatientStore
- Hospital/university server will host patient DB
- Implement `RemotePatientStore(PatientStore)` that calls their REST/FHIR API
- Swap in `website_chat_router.py` by changing one line:
  `patient_store = RemotePatientStore(base_url=os.getenv("HOSPITAL_API_URL"))`

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
sudo cat /etc/cloudflared/config.yml   # routes portfolio + nutribot

# Postgres
sudo docker ps | grep pgvector
sudo docker inspect pgvector-nutribot --format='{{.HostConfig.RestartPolicy.Name}}'

# Check all services
sudo systemctl status nutribot cloudflared docker
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

Healthy response: clinical answer mentioning CKD + hypertension restrictions (low K, low P, fluid limit, low Na). Takes 30-60s first call, 10-30s warm.

---

## Known Issues

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Cloudflare 100s timeout on cold start | 524 error for first request after idle | Keep-alive cron (item 6 above) |
| CLaRa sometimes recommends bananas to CKD patients | Clinical risk | Prompt engineering, more training data |
| Conversation history in-memory only | Lost on restart | Needs DB persistence (item 5) |
| Mac Studio SSH via `studio-ssh.mrbing.dev` broken | Can't SSH as bing directly | Use AnyDesk as care-uitm, or local LAN |
| exFAT on /mnt/ssd breaks Python venvs | Must use miniconda, not .venv | Documented, use /home/han/miniconda3/bin/python |
| UiTM network blocks Tailscale | Can't use Tailscale on Mac Studio | Replaced with Cloudflare tunnels |

---

## Document / Knowledge Base

Clinical PDFs ingested: 58 docs, 24,268 chunks in PGVector `base_knowledge` collection.
Sources: Malaysian CPGs, NICE guidelines, WHO nutrition guidance, MDGV.
Location on server: `/home/han/documents_clean/`
Ingestion script: `build_base_db.py` (run with `BASE_DOCS_DIR=/home/han/documents_clean python build_base_db.py`)

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
| Run migration | `/home/han/miniconda3/bin/python scripts/migrate_v2.py` |
| Run build schema | `/home/han/miniconda3/bin/python data/encpt/build_curated_schema.py` |
| Check DB | `/home/han/miniconda3/bin/python -c "import database as db; ..."` |

---

## Git

Repo: on GitHub (main branch, up to date as of session start).
The Mac Studio has a clone at `/Users/bing/Desktop/clara_lyh/clara-nutri/` (CLaRa inference only — not the bot codebase).
The bot codebase at `/mnt/ssd/bare_NutriChatbot/` is the source of truth.
