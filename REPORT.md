# Session Report — 2026-07-20

Machine: `han233` (local dev box, RTX 5060 Ti, not the RTX 3050 production server referenced in `CLAUDE.md`)

This report covers two pieces of work done in one continuous session: (1) standing up a full working deployment of the bot on this machine and cutting the public domain over to it, and (2) setting up and running the clinical evaluation suite, investigating its failures, and applying fixes. It's meant to be readable on its own — where something is still open or needs a decision, that's called out explicitly rather than implied.

---

## Part 1 — Production deployment: `nutribot.computationalrd.com` cut over to this machine

### Why

`CLAUDE.md` documents the public bot as served by the RTX 3050 server (`100.101.247.5`), which was down (`nutribot.computationalrd.com` → Cloudflare `530`). This machine is a separate local clone of the repo, not the RTX 3050. The user asked to make this machine the new origin.

### What was found broken/missing, and how it was resolved

| Problem found | Resolution |
|---|---|
| No Docker permissions for the `han` user | User ran `sudo usermod -aG docker han`; picked up automatically in a fresh shell (no `sg`/`newgrp` binaries available on this system, so a stale shell session had to age out naturally) |
| `.venv` was corrupted — files were `XSym`/placeholder text, not real venv content (looked like sync-tool artifacts, similar to the `._*` AppleDouble files also present in the repo) | Deleted and rebuilt from scratch with `python3 -m venv .venv` + `pip install -r requirements.txt` |
| No Postgres/pgvector running locally | `docker compose up -d pgvector` (image `pgvector/pgvector:pg16`) |
| Empty schema | `database.Base.metadata.create_all()` — this already includes all prior migrations (v2 cardiac columns, content pipeline tables, chat_messages, whatsapp columns, eka columns, phone_number) since the ORM models reflect the current schema. The standalone migration scripts (`scripts/migrate_*.py`) were also run for completeness; all reported "already exists" as expected. |
| `seed_patients.py` failed — `client_id=4` (hardcoded, matches the documented production API key) didn't exist in `api_clients` | Manually inserted an `api_clients` row with explicit `id=4` and the documented API key (`nbk_live_96cfcc81...`), hashed via `werkzeug.security.generate_password_hash` — same mechanism `add_api_client()` uses |
| **Patient ID mismatch** (see below — this one matters for eval too) | Renumbered patients in the DB rather than patching code |
| Stale `data/file_tracker.json` falsely marked all 60 source PDFs as already ingested, even on this brand-new empty DB (carried over from wherever this folder was copied from) | Moved aside to `data/file_tracker.json.stale_bak`; ingestion re-ran clean |
| `ml_dtypes` had no `float4_e2m1fn` attribute — broke every single PDF during ingestion | `pip install ml_dtypes>=0.5`, which pulled in `numpy 2.5.1` |
| `numpy 2.5.1` broke `numba` ("Numba needs NumPy 2.4 or less") | Pinned `numpy` to `2.4.6` — the sweet spot where `ml_dtypes 0.5.4` and `numba 0.66.0` both work |
| No source PDFs at the `.env` default path (`BASE_DOCS_DIR=/mnt/ssd/documents_to_ingest`, an RTX-3050-only path) | User pointed to the actual location: `/home/han/Desktop/projects/documents_clean` (60 PDFs, passed explicitly via env var at ingestion time — `.env` itself was left as-is) |
| No LoRA embedding adapter on this machine (`EMBEDDING_ADAPTER_PATH=~/models/embedding_lora` doesn't exist here) | Not fixed — `embeddings.py` gracefully falls back to the base `BAAI/bge-m3` model on CPU. **Known gap**: retrieval quality may differ slightly from the RTX 3050's fine-tuned embeddings. |
| DNS for `nutribot.computationalrd.com` already pointed at the RTX 3050's separate tunnel | `cloudflared tunnel route dns --overwrite-dns ead75dae-7d79-415f-887f-2dbd398570f5 nutribot.computationalrd.com` (this machine's own tunnel, `local-machine`) |
| `/etc/cloudflared/config.yml` (root-owned, serves `computationalrd.com`/`www` portfolio on :8501) had no ingress rule for the bot | Added `nutribot.computationalrd.com → http://localhost:8000`; user ran the sudo-gated edit + `systemctl restart cloudflared` |

### Patient ID renumbering (important — read this before touching patient data again)

`seed_patients.py` uses Postgres auto-increment, so on this fresh DB the 8 mock patients landed at IDs **2–9** in insertion order. But every reference to these patients elsewhere — `eval/test_rag.py`'s 36 test cases, `CLAUDE.md`'s patient table, the documented smoke-test curl commands — assumes the **original IDs: 1, 2, 3, 4, 5, 10, 11, 12**.

Rather than patch `eval/test_rag.py` (which would silently break on any *other* environment where IDs are already correct, e.g. a real re-seed of the RTX 3050), the DB was renumbered directly, inside a transaction, with the two `patient_id` foreign keys (`chat_messages`, `content_delivery_log`) temporarily dropped and restored:

```
Ahmad Fadzillah:  2 → 1
Lim Siew Ching:   3 → 2
Kavitha:          4 → 3
Hafizuddin:       5 → 4
Tan Wei Loong:    6 → 5
Siti Hajar:       7 → 12
Nurul Ain:        8 → 10
Rajendran:        9 → 11
```

Current state (verified): patient IDs on this machine now match the documented scheme exactly. `chat_messages` rows from earlier smoke tests were re-pointed from old id 3 to new id 2 (Lim Siew Ching) in the same transaction.

**One real content mismatch surfaced by this exercise, unrelated to the renumbering itself**: `seed_patients.py`'s current version gives patient 12 (Siti Hajar) the diagnosis "Ischaemic Heart Disease, Hypertension, Hypercholesterolaemia" — but `eval/test_rag.py` cases 28/29 (written against the old documented profile) assume "Overweight, Pre-hypertension." This is a drift between the seed script and the eval file that would reproduce on *any* fresh seed, not something this session caused. Someone needs to decide which one is stale and update the other.

### Final verified state

- `nutribot.computationalrd.com/docs` → `200`
- Full pipeline smoke test (patient 3/CKD+HTN, "What should I eat for breakfast?") → correct clinical answer referencing potassium/phosphorus/sodium restrictions
- Ingestion: **24,818 chunks** from 60 source PDFs (RTX 3050 baseline was 24,268 — close, expected given a slightly different doc set)
- App running as a bare `uvicorn` process (not the `docker-compose.yml` `nutribot` service — simpler given `.env` already points straight at the Mac Studio's CLaRa/Ollama tunnels, no need for the `agentgateway`/OpenAI-proxy container path)
- Portfolio site (`computationalrd.com`) unaffected by the cloudflared config change

### Open items from Part 1

1. **If the RTX 3050 ever comes back online, it will NOT automatically reclaim the domain.** DNS now points here until someone runs `cloudflared tunnel route dns --overwrite-dns <rtx-3050-tunnel-id> nutribot.computationalrd.com` to switch it back.
2. No LoRA embedding adapter locally — retrieval uses base `BAAI/bge-m3`. Copy `~/models/embedding_lora` here if retrieval-quality parity with the RTX 3050 matters.
3. Siti Hajar (patient 12) content mismatch between `seed_patients.py` and `eval/test_rag.py` cases 28/29 (see above) — needs a decision.
4. `.env`'s `BASE_DOCS_DIR` still points at the RTX-3050-only path (`/mnt/ssd/documents_to_ingest`); harmless unless someone re-runs `build_base_db.py` without passing `BASE_DOCS_DIR` explicitly.

---

## Part 2 — Evaluation infrastructure: a separate local judge model

### Why

The user asked which local/open-source model this machine (RTX 5060 Ti, 16GB VRAM, ~12GB free; 30GB RAM) could run for evaluation. Investigation found that `judge_stance()` (`eval/test_rag.py`) — the LLM-judge that classifies a contraindication answer's actual clinical stance (RESTRICT/PERMIT/MODERATE/UNCLEAR) — was calling `call_ollama_generate()`, i.e. **the exact same model and endpoint used to generate the candidate answer** (Mac Studio's `qwen2.5:32b`). That's a self-grading setup: the model that wrote the answer was also grading it.

### What was done

- Pulled **`qwen2.5:14b`** (9.0GB) via the already-installed local Ollama daemon (v0.32.1, already running as a systemd service on this machine). Chosen because: it fits comfortably in the ~12GB free VRAM (the full `qwen2.5:32b` needs ~20GB at Q4, doesn't fit); same model family as production, so judge behavior/prompt-following style stays consistent; `judge_stance()` only needs a short classification, not full 32B-scale reasoning.
- `llm.py`: added `JUDGE_OLLAMA_MODEL`/`JUDGE_OLLAMA_BASE_URL` config (defaults to the existing `OLLAMA_MODEL`/`OLLAMA_BASE_URL` if unset, so nothing breaks anywhere else that doesn't set them) and a new `call_judge_llm()` function, calling the judge model independently at `temperature=0.0`.
- `.env`: added `JUDGE_OLLAMA_MODEL=qwen2.5:14b`, `JUDGE_OLLAMA_BASE_URL=http://localhost:11434`.
- `eval/test_rag.py`: `judge_stance()` now imports and calls `call_judge_llm()` instead of `call_ollama_generate()`.
- Verified end-to-end: fed the judge a clear CKD/banana-restriction sentence, got back `RESTRICT` correctly.

**Decision explicitly made and confirmed with the user**: keep production generation on Mac Studio's `qwen2.5:32b` untouched; only the judge moved local. (The alternative — pointing `OLLAMA_MODEL`/`OLLAMA_BASE_URL` globally at the local 14B — was considered and rejected, because that constant is shared with the actual RAG generation call in `get_rag_response()`; doing so would have silently started testing a different, weaker model instead of the real production model.)

---

## Part 3 — Full evaluation run #1 (baseline, before any prompt changes)

Command: `PYTHONPATH=. .venv/bin/python eval/test_rag.py --out eval/results/rag_full.json`

**Result: 26/34 passed (76%)**, took ~6800s (~1h53m) end-to-end against the live Mac Studio backend, 8 failures. Full detail in `eval/results/rag_full.json`.

### Failure breakdown and interpretation

| # | Case | Failure type | Interpretation |
|---|---|---|---|
| 14 | L3 Post-CABG+HF+CKD4: salted fish | Personalization — missing L3 caution keywords | See Part 4 — root cause identified |
| 17 | L2 HTN+Hypercholesterol+T2DM: acar (pickled veg) | Personalization + Contraindication (judge: MODERATE, test wants RESTRICT) | Two different problems in one case — see below |
| 21 | L1 Dyslipidaemia+Obesity: coconut milk | Contraindication (judge: MODERATE, test wants RESTRICT) | Genuine clinical-judgment question, not a prompt bug |
| 24 | L3 Post-CABG+HF: soup/stock | Personalization — missing L3 caution keywords | See Part 4 |
| 25 | L3 Post-CABG+HF: fluid restriction | Personalization — missing L3 caution keywords | See Part 4 |
| 28 | L1 Overweight+Pre-HTN: roti canai | Personalization — missing L1 caution keywords | See Part 4 |
| 29 | L1 Overweight+Pre-HTN: instant food | Personalization + Contraindication (judge: MODERATE, test wants RESTRICT) | Same dual pattern as case 17 |
| 34 | L1 BM: gulai bersantan | Personalization (BM keyword gap) + Contraindication (judge: MODERATE) | BM half fixed in Part 5; contraindication half is the same clinical question as 17/21/29 |

Two structurally distinct failure classes emerged, requiring different fixes:

1. **Personalization keyword misses (14, 17, 24, 25, 28, 29, 34)** — the model's answer was often clinically fine but didn't literally contain one of the ~6 tracked words per level (e.g. `L3: supervised, supervision, doctor, medical, cardiac rehab`). Investigated in Part 4.
2. **Contraindication stance disagreements (17, 21, 29, 34)** — the LLM judge classified the answer's actual stance as MODERATE ("fine in small amounts/occasionally") where the test's `acceptable_stances` only allows RESTRICT. This is a dietitian-level clinical call: is portion-controlled pickled veg / coconut milk / occasional instant food a defensible MODERATE answer, or should these be hard-RESTRICTed for these specific conditions? **Not resolved this session — needs clinical sign-off, not a code fix.**

---

## Part 4 — Root-cause investigation: is the L1/L3 personalization prompt injection actually firing?

**Short answer: yes, 100% reliably. The bug isn't in the injection mechanism — it's in what the injected text actually says.**

### Verification method

Reconstructed the exact prompt sent for case 25 (patient 11/Rajendran, L3, "Can I drink as much water as I want?") by calling `rag._build_qwen_prompt()` directly with the patient's real profile. Confirmed the `## Personalization Level L3` block is added every time `profile.get("personalization_level")` is set (`rag.py:174`, unconditional on that one check) — no missed firings.

### The actual problem

The injected text itself (`_LEVEL_INSTRUCTIONS`/`_LEVEL_INSTRUCTIONS_SELF` in `rag.py`, pre-session) was written **entirely about physical activity/exercise safety** for every level — e.g. the original L3: *"Restrict all recommendations to medically supervised options only... Do not suggest unsupervised physical activity."* Zero mention of food, diet, or fluid caution framing.

Cross-checked all 10 `personalization_check` cases in the suite:

| Case | Level | Topic | Result |
|---|---|---|---|
| 4 | L3 | **Exercise** ("Can I start exercising?") | PASS |
| 14, 24, 25 | L3 | Food/fluid | FAIL |
| 16, 21, 26 | L1/L2 | Food | PASS (by chance of phrasing) |
| 17, 28, 29, 34 | L1/L2 | Food | FAIL |

The one exercise question passed reliably because the instruction is actually about that topic. The nine food questions passed or failed **essentially by coincidence** of whether the model happened to use a tracked word — not because anything in the prompt asked it to.

---

## Part 5 — Fixes applied and re-test results

### Fix 1: Diet-focused clauses added to `_LEVEL_INSTRUCTIONS` / `_LEVEL_INSTRUCTIONS_SELF` (`rag.py`)

Kept all existing activity-safety language untouched; appended a new clause to L1, L2, and L3 (both third-person and second-person versions) specifically addressing food/drink/fluid questions — asking the model to always frame higher-risk items with a concrete moderation boundary (L1), name the specific risk + a monitoring action (L2), or treat restrictions as firm medical limits with a brief care-team reference (L3). L0 was left alone (deliberately permissive tier — case 30's control check already expects non-restriction here).

### First re-test round — mixed results, revealed a second bug

Re-ran the 8 originally-failing cases. Only case 29 flipped to pass initially. Investigation of the raw answer text surfaced two more issues:

- **Real bug in the fix itself**: the L3 clause said "note that any *change* to it should be confirmed with their doctor" — scoped only to the hypothetical of changing the limit. None of the test questions ask to change anything, so the model correctly never triggered that clause. Example (case 24): *"Yes, you can have soup... as long as it fits within your sodium, potassium, phosphorus... limits"* — clinically correct, but no reason given to mention a doctor.
- **Sampling noise, not a fix**: generation runs at `temperature=0.5` (`llm.py:143`, pre-existing, not changed this session). The same case can flip PASS/FAIL on identical re-runs — case 28 passed 1 of 3 attempts, case 29 similarly inconsistent. This means single-run eval results (including this session's baseline run) carry real sampling variance; a case passing or failing once is not the same as a stable verdict.
- **Confirmed separate bug**: case 34's Malay answer was clinically excellent — *"hadkan kepada sekali seminggu"* ("limit to once a week") — but `LEVEL_CHECK_TERMS` only had English keywords, so a correct BM answer could never pass on language grounds alone.

### Fix 2 & 3 applied

- **`rag.py`**: L3 clause reworded to be unconditional — always briefly reference the care team in every food/fluid answer, not just when discussing changes.
- **`eval/test_rag.py`**: `LEVEL_CHECK_TERMS` gained Bahasa Malaysia equivalents for all three levels (`sederhana, hadkan, kurangkan, pantau, berhati-hati, doktor, perubatan, pasukan penjagaan`, etc.) plus the English phrase `"care team"`, which the L3 instruction's own suggested wording uses but had been left out of the check.

### Final verification

- Case 34 (BM): passes reliably (verified twice) — this was a real, deterministic fix.
- Cases 28/29 (L1): pass more often post-fix, but still probabilistic — the diet clause nudges the model's phrasing, doesn't guarantee a tracked keyword every time.
- Cases 14/25 (L3): re-ran 3x each after the unconditional-clause fix — **0/3 and 0/3**. The model consistently gives the clinically correct restriction but the "your care team set this limit" framing loses out against the prompt's own competing constraints elsewhere (`_build_qwen_prompt`'s "under 100 words," "3-part structure," "no preamble" voice rules). **This is a real, unresolved product tension — not something further wording tweaks are likely to fix reliably.**
- Case 24 (L3): passed in the final combined snapshot run.
- Final snapshot across all 8 original failures: **4/8 passing** (up from 0/8 baseline for this same subset) — but given the confirmed sampling noise, this specific 4/8 number should not be read as a stable rate without repeated runs.
- Cases 17/21 (contraindication stance): **unchanged**, as expected — the diet-instruction wording doesn't touch the judge's stance classification; this was never the mechanism that could fix these two.

### Deployment

Both `rag.py` and `eval/test_rag.py` changes are live. The running `uvicorn` app process was restarted (old PID 36542 → new PID 139315) so the diet-focused instructions are actually being served to real traffic on `nutribot.computationalrd.com`, not just present in eval runs. Post-restart smoke test confirmed correct, level-appropriate behavior.

---

## Summary of all file changes this session

| File | Change |
|---|---|
| `llm.py` | Added `JUDGE_OLLAMA_MODEL`/`JUDGE_OLLAMA_BASE_URL` config + `call_judge_llm()` function |
| `rag.py` | Added diet-focused clauses to `_LEVEL_INSTRUCTIONS`/`_LEVEL_INSTRUCTIONS_SELF` (L1/L2/L3, both self and third-person); L3 clause reworded to be unconditional after first test round |
| `eval/test_rag.py` | `judge_stance()` switched from `call_ollama_generate()` to `call_judge_llm()`; `LEVEL_CHECK_TERMS` gained BM equivalents + `"care team"` |
| `.env` | Added `JUDGE_OLLAMA_MODEL`, `JUDGE_OLLAMA_BASE_URL` |
| `data/file_tracker.json` | Moved to `data/file_tracker.json.stale_bak` (stale, carried over from wherever this repo was copied from) |
| DB (patients table) | Renumbered 8 mock patients to match documented IDs (1,2,3,4,5,10,11,12) |
| `/etc/cloudflared/config.yml` (system, not repo) | Added `nutribot.computationalrd.com → localhost:8000` ingress rule |
| Cloudflare DNS (external, not repo) | `nutribot.computationalrd.com` CNAME repointed from RTX 3050's tunnel to this machine's `local-machine` tunnel |

---

## Recommended next steps

1. **Decide on cases 17/21/29/34's contraindication stance disagreements** (acar, coconut milk, instant food) — needs the supervising dietitian's judgment on whether MODERATE is acceptable for these specific condition/food pairs, or whether the test's RESTRICT-only bar is correct and the model is being too lenient. This is the highest-value open question, since it's about real clinical safety, not test plumbing.
2. **Decide the L3 word-budget tension** (cases 14/25): either loosen the "under 100 words" constraint specifically for L3 patients so the care-team reference has room, restructure the prompt so it doesn't compete with the voice-rules section, or accept that this framing will only appear probabilistically and adjust the eval's expectation accordingly.
3. **Resolve the Siti Hajar (patient 12) content mismatch** between `seed_patients.py`'s current profile (IHD/HTN/Hypercholesterolaemia) and `eval/test_rag.py` cases 28/29's assumed profile (Overweight/Pre-hypertension).
4. **Re-run the full 34-case suite** (not just the 8 that failed) now that both `rag.py` and `eval/test_rag.py` have changed, to get a clean updated baseline — ideally 2-3x given the confirmed `temperature=0.5` sampling noise, rather than trusting a single run.
5. **Consider whether `personalization_check`'s literal-keyword approach is the right long-term design**, given how much of this session's investigation was about the model saying the right *thing* in different *words*. `judge_stance()` already moved from keyword-matching to an LLM judge for exactly this reason (documented in `CLAUDE.md`'s pending-work item 10, the "banana for CKD" example) — the same argument applies to `personalization_check`. Not done this session; flagged as a design decision for whoever owns eval methodology next.
6. **Decide whether to copy the LoRA embedding adapter to this machine** for retrieval-quality parity with the RTX 3050 (currently running on base `BAAI/bge-m3`).
7. **If the RTX 3050 comes back online**, remember DNS won't auto-revert — that's a manual `cloudflared tunnel route dns --overwrite-dns` back to its tunnel ID.
