---
title: Nutribot-API
emoji: 🤖
colorFrom: green
colorTo: blue
sdk: docker
---
# MyHeartCoach / Nutribot

A cardiac-rehab coaching chatbot built for a Malaysian hospital/university
client (UiTM). It started as a dietetics bot (Nutribot) and now covers the
11 MyHeartCoach modules (`taxonomy.COMPONENTS`): nutrition, exercise,
foundations, blood pressure, lipids, diabetes, weight,
tobacco/nicotine/alcohol, physical activity, psychosocial and medication.
Patient-facing answers are personalised by risk level (L0–L3) and onboarding
stage (OB1–OB3), in English and Bahasa Melayu.

## How it works
- **Chat (Option B RAG):**
  1. `TopicBoostedRetriever` pulls candidates from PGVector (`base_knowledge`,
     178 clinical documents), gated by module.
  2. `structured_store.py` adds row-level facts from reference spreadsheets.
  3. CLaRa-7B compresses the retrieved chunks.
  4. `qwen2.5:32b` (Ollama) writes the answer.
  5. The models run on a Mac Studio behind a Cloudflare tunnel.
- **Profile extraction:** an LLM extractor fills supplementary profile
  fields from chat, never clinical ones (`extractor.py`, `patient_store.py`).
- **Weekly EKA content:** `scripts/generate_weekly_eka.py` drafts
  Exercise/Knowledge/Action items per condition group, with L/OB variants.
  Nothing reaches a patient until a reviewer approves it at `/eka-review`.
- **Evaluation:** `eval/test_rag.py` runs contraindication, myth,
  personalization and scope suites with GEval judges. Humans calibrate those
  judges at `eval.computationalrd.com`.

## Services (Han Server)
| Service | Port | Public URL |
|---|---|---|
| Patient chat API + team hub (`app.py`) | 8000 | nutribot.computationalrd.com |
| Docs API + EKA review (`docs_api.py`) | 8100 | docs-api.computationalrd.com |
| Judge calibration (`eval_api.py`) | 8200 | eval.computationalrd.com |

The team signs in once at `nutribot.computationalrd.com/team/login` with
their API key. A cookie on `.computationalrd.com` covers all three hosts.

## Docs
- [ARCHITECTURE.md](ARCHITECTURE.md): the full architecture reference
- [docs/ROADMAP.md](docs/ROADMAP.md): status board and timeline to 2026-12-31
- [docs/api_usage.md](docs/api_usage.md): client API guide
- [docs/PROMPTS.md](docs/PROMPTS.md): every prompt, and where it lives
- [docs/component_taxonomy_contract.md](docs/component_taxonomy_contract.md): the module taxonomy
- [docs/TRIPOD_LLM_Report.md](docs/TRIPOD_LLM_Report.md): TRIPOD-LLM reporting
- `docs/archive/`: superseded docs, kept for history

## Run locally
```bash
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
.venv/bin/python eval/test_rag.py --smoke        # smoke eval (needs Postgres + the Mac Studio models)
```
Configuration lives in `.env`, which is not committed; see ARCHITECTURE.md
for the variables.
