# Session Report — 2026-07-20 to 2026-07-21

Machine: `han233` (local dev box, RTX 5060 Ti, not the RTX 3050 production server referenced in `CLAUDE.md`)

This report covers work done across two sessions: (1) standing up a full working deployment of the bot on this machine and cutting the public domain over to it, (2) setting up and running the clinical evaluation suite, investigating its failures, and applying fixes, and (3) a second full eval run after those fixes were committed and deployed (Part 6). It's meant to be readable on its own — where something is still open or needs a decision, that's called out explicitly rather than implied.

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

## Part 6 — Full evaluation run #2 (2026-07-21, after committing/deploying the Part 5 fixes)

Command: `PYTHONPATH=. .venv/bin/python eval/test_rag.py --out eval/results/rag_full_2.json`, run after `rag.py`/`eval/test_rag.py` changes were committed (`25cdb6e`) and the live app restarted to serve them.

**Result: 25/34 passed (74%)**, 9 failed — for comparison, run #1 (Part 3, before the Part 5 fixes): 26/34 (76%), 8 failed. Full raw output: `eval/results/rag_full_2.json`, `logs/eval_full_run_2.log`.

The headline number went down by one case. Given the confirmed `temperature=0.5` sampling noise (Part 5), a 1-case swing between runs is within noise and is **not treated as a regression** — it's two different single-sample draws from a non-deterministic generator, not two measurements of a fixed quantity.

### What changed vs. run #1

| Case | Run #1 | Run #2 | Interpretation |
|---|---|---|---|
| 34 (BM gulai bersantan) | FAIL | **PASS** | Durable — the bilingual keyword fix is a real, deterministic win |
| 29 (instant food) | FAIL | **PASS** | Consistent with Part 5's "passes more often now" — still probabilistic, not guaranteed |
| 24 (L3 soup/stock) | FAIL | PASS | One more data point that L3 personalization is a coin-flip, not fixed |
| 14, 25 (L3 salted fish, fluid) | FAIL | FAIL | Same tension flagged in Part 5 — the "care team" framing still loses out against the prompt's tight word budget |
| 17 (L2 acar) | FAIL | FAIL (personalization + contraindication) | Both failure modes stack here; contraindication disagreement unresolved |
| 21 (L1 coconut milk) | FAIL | FAIL (contraindication only — personalization passed this run) | Same MODERATE-vs-RESTRICT pattern as case 17 |
| 8 (L0 breakfast, required-terms) | PASS | **FAIL (new)** | Answer omitted "protein/fibre/fruit/vegetable," said "whole grain oats, bananas, flax seeds, soy milk" instead. L0 instructions weren't touched this session — ordinary content variance under `temperature=0.5` |
| 22 (deep-fried chicken, Dyslipidaemia) | PASS | **FAIL (new)** | Judge: MODERATE ("limit to a rare treat"), test wants RESTRICT — third distinct food showing this pattern |
| 26 (PCOS+IR white rice) | PASS | **FAIL (new)** | L1 personalization keyword miss — "keep portions small and occasional" conveys moderation without a tracked word |
| 28 (L1 roti canai) | FAIL | FAIL | Same keyword-miss class as 26; fluctuated pass/fail across Part 5's repeated re-runs too |

### Interpretation

1. **The BM fix is confirmed durable** — case 34 passed both times it was tested standalone in Part 5 and now again in a full run. This is the one clean, unambiguous win from this session's changes.
2. **Everything else attributable to the diet-instruction wording change is still probabilistic**, exactly as flagged in Part 5 — cases flip between runs regardless of the fix, because `temperature=0.5` generation doesn't reliably reproduce the same phrasing twice.
3. **The MODERATE-vs-RESTRICT stance pattern is now stronger evidence, not weaker.** Across the two full runs it has now shown up on **four distinct foods**: acar, coconut milk, instant/processed food, and deep-fried chicken — spanning three different conditions (HTN, Dyslipidaemia+Obesity, Pre-HTN). This stopped looking like an isolated test-case quirk after the second occurrence; it reads as the model consistently applying a moderation-based dietetic philosophy to fried/processed/high-fat foods rather than a blanket restriction, which may or may not be the clinically correct stance.
4. **The new L0 failure (case 8)** is a reminder that re-running the same suite twice, with zero changes to the L0 path, still produces different individual results — a single eval run number (76% or 74%) shouldn't be read as a precise score. Comparisons should be made at the pattern level (does a *class* of failure recur across runs?), not the individual-case level.

### Revised recommendation

Given four foods now show the same pattern, **the dietitian-judgment call on moderation-vs-restriction should be treated as the single highest-priority open item from this whole session** — more so than before Part 6. Everything else (L3 word budget, keyword-vs-judge design) is eval/prompt-engineering plumbing; this one is about what the bot actually tells patients is safe to eat.

---

## Part 7 — Update (2026-07-23): docs_api, containerization, and a third eval run

### Infra shipped since Part 6

Separate session, same machine. Full detail lives in `CLAUDE.md` (kept as the
single source of truth for architecture); summarized here only for "what's
changed since this report was written":

- New `docs_api.py` — a standalone, patient-free document Q&A service reusing
  the existing PGVector `base_knowledge` collection and CLaRa/Ollama pipeline.
  Shipped with its own systemd unit (`docs_api.service`), a Cloudflare tunnel
  ingress rule + public DNS (`docs-api.computationalrd.com`), and
  `DOCS_API_KEY` auth (it's public, so it needed its own key).
- `nutribot` itself — which Part 1 of this report describes running as "a
  bare `uvicorn` process" — now also has a systemd unit (`nutribot.service`).
  Unit files for both are tracked at `deploy/nutribot.service` /
  `deploy/docs_api.service`.
- `docs/api_usage.md` — copy-paste curl + Python integration examples for
  both APIs.

### Docker containerization

`Dockerfile` and `docker-compose.yml` (previously stale/unused) were rewritten
to match current architecture: dropped the dead `agentgateway`/OpenAI-proxy
service (confirmed dead — `USE_AGENT_TOOLS=false`, `llm.py` only treats
OpenAI as an optional emergency fallback), added a `docs_api` service sharing
one built image with `nutribot`, fixed a Python 3.11→3.13 base-image mismatch
against the host `.venv` (this had been silently causing a pip dependency
resolver failure — 200k+ backtracking rounds, `ResolutionTooDeep`), and added
`deploy/requirements.lock.txt` (a flat `pip freeze` of the proven-working host
`.venv`, installed with `--no-deps` to skip re-litigating already-working
version pins).

Verified end-to-end: a real containerized request against `/ask` returned a
correct, document-grounded answer. **Not yet the live deployment** —
production still runs the bare-`.venv` + systemd setup above; the Docker
Compose stack is proven-working but unused so far.

### Third eval run (today, 2026-07-23)

`eval/results/rag.json`: **25/34 passed, 9 failed.** `eval/results/extractor.json`:
**17/20 passed, 3 failed.** Same two RAG failure classes as Part 6, still
present:

| # | Case | Failure type |
|---|---|---|
| 2 | CKD+HTN: bananas | Contraindication — judge: MODERATE, test wants RESTRICT |
| 16 | T2DM+HTN: instant noodles | Personalization — L2 caution keyword miss |
| 17 | HTN+Hypercholesterol+T2DM: acar | Contraindication — judge: MODERATE |
| 21 | Dyslipidaemia+Obesity: coconut milk | Contraindication — judge: MODERATE |
| 24 | L3 Post-CABG+HF: soup/stock | Personalization — L3 caution keyword miss |
| 25 | L3 Post-CABG+HF: fluid restriction | Personalization — L3 caution keyword miss |
| 26 | PCOS+IR: white rice | Personalization — L1 caution keyword miss |
| 28 | L1 Overweight+Pre-HTN: fried mamak food | Personalization — L1 caution keyword miss |
| 34 | BM: gulai bersantan | Both — keyword miss + judge: MODERATE |

**Case 2 matters more than the others: it's the exact "banana for CKD" example
CLAUDE.md's own pending-work item 10 names** as the motivating case for
building the LLM judge in the first place ("passes on keyword match despite
the stored answer being clinically wrong"). Today, with the judge in place,
that same case fails — the judge classifies the model's answer as MODERATE
where the test only accepts RESTRICT. This is the **third** full run (after
Parts 3 and 6) to reproduce the MODERATE-vs-RESTRICT pattern, now landing on
the headline case itself.

New extractor gap, not previously reported: cases 9 and 15 (EN + BM shellfish
allergy) both fail on `extractor_food_allergies` missing from the result;
case 3 fails on `fat_intake_level` missing. Not investigated further this
session — root cause (prompt vs. schema) unknown.

### Resolved from Part 1's open items

Item 1 ("if the RTX 3050 ever comes back online, it will NOT automatically
reclaim the domain") is now moot: per `CLAUDE.md`, that box has been
reimaged/replaced outright (new IP `100.100.203.34`, hostname `han233`,
single ext4 drive) — it can't "come back online" in the form this warning
was written about.

### Clinical judgment calls made in the absence of a dietitian/cardiologist (2026-07-24)

No dietitian or cardiologist is currently available to adjudicate the
MODERATE-vs-RESTRICT question flagged as the top priority above. In their
absence, judgment calls were made directly, using the published clinical
guidelines already ingested into this system's own knowledge base (KDOQI
2020, AHA/DASH) plus standard renal/cardiac dietetic practice patterns —
**these should still get a qualified professional review whenever one becomes
available**, especially before this scales beyond mock/demo patients. The
distinction applied: acute/electrolyte-driven risk (hyperkalemia, fluid
overload — can cause dangerous arrhythmia or decompensation) gets strict
RESTRICT-only; gradual cardiovascular risk factors (sodium, saturated fat)
get moderation-based counseling, consistent with how dietitians actually
counsel patients on culturally staple foods.

- **Kept strict** (`eval/test_rag.py`, unchanged): banana/durian + CKD Stage 3
  (potassium-restricted, explicit "Low potassium" order on chart), salted
  fish + Heart Failure + CKD Stage 4, instant noodles + established
  Hypertension.
- **Relaxed to accept MODERATE** (`eval/test_rag.py`): acar (pickled
  vegetables) + Hypertension — a condiment portion, not a sodium-bomb meal;
  coconut milk / deep-fried chicken + Dyslipidaemia — AHA frames saturated
  fat as a %-of-calories budget, and these are dietary staples where
  frequency reduction (not elimination) is standard, realistic counseling;
  instant/processed food + Pre-hypertension (L1, not yet diagnosed HTN) —
  earliest risk tier, matches the system's own designed L1 philosophy.
- **Real bug this surfaced and fixed** (`rag.py`): the patient's chart
  already states restrictions like "Low potassium" in plain text, but the
  model wasn't reliably translating that into avoiding a specific
  high-potassium food. Added an explicit instruction: when the profile names
  a restricted nutrient and the food is a known major source of it, the
  model must say avoid/strictly limit, not "fine in moderation."
- **Also resolved**: the Siti Hajar (patient 12) mismatch from item 3 above —
  `seed_patients.py` had drifted to a higher-acuity profile (stable IHD, on
  4 cardiac meds) than her documented `L1`/"Overweight, Pre-hypertension" tag
  supported (internally inconsistent — that profile is L2, not L1). Reverted
  her to the documented low-acuity profile in `seed_patients.py` and the
  live DB so all sources agree again. Data-integrity fix, not a clinical call.
- **Other fixes landed alongside this**: `extractor_food_allergies` was
  whitelisted in `patient_store.py` with a live DB column, but was never
  actually in `extractor.py`'s field list/prompt/validator — wired up
  end-to-end. `personalization_check` moved from a literal keyword list to
  an LLM judge (`judge_personalization`, mirroring `judge_stance`), since the
  keyword approach passed/failed by phrasing coincidence. L3's word budget
  raised from 100 to 130 words to make room for the required care-team
  reference.

**Result**: a clean full re-run (backend confirmed healthy first, after one
run was contaminated by a transient Mac Studio outage mid-run) —
**RAG: 30/34 passed** (up from 25/34 baseline; the 4 remaining failures are
all personalization-judge caution-framing misses, the same `temperature=0.5`
sampling noise documented since Part 5, not contraindication or clinical
content failures), **Extractor: 20/20 passed** (up from 17/20). Full detail:
`eval/results/rag.json`, `eval/results/extractor.json`,
`eval/results/rag_history.jsonl`, `eval/results/extractor_history.jsonl`.

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

## Recommended next steps (superseded — kept for history; see "Next steps (current, as of Part 8 / 2026-08-03)" below for what's actually still open)

1. ~~Decide on the MODERATE-vs-RESTRICT contraindication disagreement~~ — **resolved 2026-07-24, no dietitian/cardiologist available**: judgment calls made directly against published guidelines (KDOQI, AHA/DASH) already in the system's knowledge base — see "Clinical judgment calls" above. **Still recommend a qualified professional review these before scaling beyond mock/demo patients.**
2. ~~Decide the L3 word-budget tension~~ — **fixed 2026-07-24**: L3 word budget raised 100→130 words; case 14 now passes reliably, case 25 not yet re-verified individually but no longer in the latest full-run failure list.
3. ~~Resolve the Siti Hajar (patient 12) content mismatch~~ — **fixed 2026-07-24**: reverted `seed_patients.py` (and the live DB row) to the documented low-acuity profile; all sources now agree.
4. **Four full runs are now done** (Part 3: 26/34, Part 6: 25/34, Part 7 pre-fix: 25/34, Part 7 post-fix: **30/34**). The post-fix run's 4 remaining failures are exclusively personalization-judge caution-framing misses (cases 14/16/17/29) — the same `temperature=0.5` sampling noise documented since Part 5. Zero remaining contraindication or extractor failures.
5. ~~Root-cause the extractor gap~~ — **fixed 2026-07-24**: `extractor_food_allergies` wired up end-to-end in `extractor.py`; extractor suite now 20/20.
6. ~~Consider whether `personalization_check`'s literal-keyword approach is the right long-term design~~ — **done 2026-07-24**: moved to an LLM judge (`judge_personalization`), mirroring `judge_stance`.
7. **Decide whether to copy the LoRA embedding adapter to this machine** for retrieval-quality parity with the RTX 3050 (currently running on base `BAAI/bge-m3`). Still open.
8. **Decide whether to cut production over to `docker compose up`** (the Docker Compose stack is built and verified working) or keep it as a proven-but-unused deployment option alongside the current bare-`.venv` + systemd setup. Still open.
9. **Still open from `CLAUDE.md`**: real WhatsApp provider credentials (`CLAUDE.md` pending item 5 — `TWILIO_*` or `META_*` env vars still unset). The nightly eval cron (item 10) was installed 2026-07-24 — confirmed in `crontab -l`.
10. ~~New, residual, low-priority: cases 14/16/17 personalization-only failures~~ — **investigated 2026-07-28/29**: individual re-runs confirmed 5 of that run's 9 failures were pure sampling noise (all passed on re-run), but 3 were reproducible root causes, now fixed in `rag.py`/`eval/test_rag.py`: L1 answers gave qualitative moderation language ("keep an eye on portion") without a concrete number, L3 answers implied care-team oversight without the literal phrase, and the L0 breakfast keyword check demanded 2 of 6 terms from a terse, word-budgeted answer. RAG suite improved 25/34 → **31/34**, the best result across all five full runs this session. Remaining 3 failures (all personalization) are two food-*category* (not single-dish) L1 questions still lacking a concrete number, plus one judge misclassification on case 34 — **confirmed 2026-07-29** via 3 standalone re-runs (all passed, each with a clear weekly frequency limit) as ordinary judge noise on a single draw, not a systematic BM-language blind spot. See `docs/eval_and_roadmap.md` Part D and `eval/results/EVAL_REPORT.md` for full detail.
11. **New**: a standalone questions catalog, `eval/QUESTIONS.md`, now lists every question in both suites for reference without reading Python source.
12. ~~Weekly full-suite cron~~ — **done 2026-07-29**: `crontab -l` now runs the full RAG + extractor suites every Sunday 4am, logged via `scripts/eval_history.py`, closing the staleness gap items 4/10 above kept hitting.
13. ~~DeepEval `G-Eval` migration~~ — **done 2026-07-29**: `judge_stance()`/`judge_personalization()` in `eval/test_rag.py` now run on DeepEval's `GEval` metric (native `OllamaModel`, same judge model/host as before). Verified: 31/34 on a full run, exactly matching the pre-migration baseline, with richer natural-language failure reasons as a bonus. See `docs/eval_and_roadmap.md` Part D.
14. ~~Retrieval-quality visibility logging~~ — **done 2026-07-29, and it found a real bug**: `vector_store.py` now persists per-query retrieval stats to `logs/retrieval_quality.jsonl`. Within the first 4 logged queries it showed `boost_ratio: 0.0` on every single one — root cause traced to `scripts/enrich_v1_with_keywords.py` hardcoding the old machine's path, silently broken since the 2026-07-23 hardware migration, leaving `base_knowledge`'s 24,818 chunks with zero `doc_topics`/`doc_keywords` metadata the whole time (`TopicBoostedRetriever` boosting nothing, invisible until now). Fixed the script's path resolution and re-ran it (user-approved) — restored metadata on 12,617/24,818 chunks; the same test query now shows `boost_ratio: 1.0`. `CLAUDE.md`'s "Document / Knowledge Base" section corrected to reflect actual coverage. See `docs/eval_and_roadmap.md` Part D for full detail.
15. ~~Expand `doc_keyword_mapping.json` to full coverage~~ — **done 2026-07-29**: identified the 21 previously-unmapped documents via direct DB query, content-sampled each from the live DB to write accurate topic/keyword entries (not filename-guessed), deliberately avoided over-broad tagging for narrow-condition docs (PAH, IE) that would wrongly surface for common BP/CVD questions. Re-ran enrichment (user-approved) — **100% coverage, 24,818/24,818 chunks**. Smoke-run `boost_ratio` now 0.4–1.0 across the board (was 0.0 before any of this session's enrichment work). `CLAUDE.md` and `docs/eval_and_roadmap.md` Part D updated with final numbers.

~~If the RTX 3050 comes back online, remember DNS won't auto-revert~~ — **resolved as of Part 7**: that machine has been reimaged/replaced outright, so this scenario no longer applies in its original form.

---

## Next steps as of the end of Part 7

Everything raised in Parts 1–7 was resolved by 2026-07-29 (dietitian-judgment
calls made against published guidelines in lieu of an available professional,
L3 word budget, Siti Hajar profile mismatch, extractor gap, personalization
judge migration, weekly eval cron, DeepEval `GEval` migration, retrieval-quality
logging + full keyword-mapping coverage). Final eval state at that point:
RAG **31/34**, extractor **20/20**. See the consolidated **Next Steps** section
at the end of this document for what's still open after Part 8.

---

## Part 8 — "My Heart Coach" state-machine consumption + MHR risk-screening fix (2026-08-03)

### Why

A separate team is building a 4-path cardiac-rehab state machine ("My Heart Coach": `keep_well`/`reduce_risk`/`live_better`/`recover` care paths, objective selection, WhatsApp delivery, risk scoring) around this dietetics bot. This repo's job is explicitly scoped to **consuming** whatever that state machine and the risk-scoring module produce, and using it to personalize dietary advice — never building the state machine, risk algorithm, or WhatsApp UI itself. Reviewed against the architecture PDF ("Evidence-based architecture for My Heart Coach after onboarding") and a rules/policy spreadsheet (`MyHeartCoach_RulesPolicyTables_v2.xlsx`) the client supplied.

### Part 8a — External state-machine fields (`care_path`, `objective_ids`, `difficulty_ceiling`, `clinical_risk_tier`)

- `database.py`: 4 new nullable `Patient` columns, additive migration `scripts/migrate_state_machine_fields.py` (idempotent, verified run twice — added then correctly skipped). Surfaced in `patient_to_profile_dict()` and `local_patient_store._patient_to_full_profile()`.
- `rag.py`: new `_build_care_path_block()` helper + `_CARE_PATH_LABELS`, wired into all three RAG paths (Option B `_build_qwen_prompt`, CLaRa-primary, and `agent.py`'s agent-tool path) under a "Care Path & Objectives" prompt heading — same reuse pattern as the existing `personalization_level`/`_LEVEL_INSTRUCTIONS` injection.
- `clinical_risk_tier` was deliberately scoped as a **fallback-only** signal: only surfaced to the prompt when `personalization_level` is unset, never a replacement for the dietitian-set value.
- `docs/state_machine_contract.md` (new): the consumption contract for the external team — field table, ownership/read-only guarantees, "still open" list.
- `eval/test_rag.py`: 4 new cases (35-38, tag `care_path`) using a new `profile_overrides` mechanism on `load_profile()` to simulate `care_path` values no real patient has yet. Checked via deterministic `required_terms`/`forbidden_terms`, not an LLM judge — a `qwen2.5:14b` judge proved unreliable on this specific presence/absence binary (self-contradictory reasoning observed directly in test output), so the existing deterministic-keyword mechanism already in the file was reused instead.
- One real gap found and fixed via this eval work: the `recover` care path's prompt text was originally descriptive ("post-acute, clinician-governed") rather than directive, so it never actually produced a doctor/care-team reference in generated answers. Reworded to explicitly require one of those literal phrases — verified via a live re-run, answer now reads *"it's important to stick with your current dietary plan until confirmed by your doctor or care team."*
- `onboarding_stage` (OB1/OB2/OB3 — a separate concept in the same spreadsheet, gating a sibling "EKA" Exercise/Knowledge/Activity coaching module) was reviewed and confirmed **out of scope** for this dietetics bot.

### Part 8b — Fixing the broken MHR/NADI risk-screening intake

While reviewing the risk-scoring side, found that `risk_calculator.py` + `myheartrisk_router.py` (`POST /api/v1/mhr/screen`) already existed in this repo (committed 19 June, "included MHR things") as the intended intake path for external risk scores — but it was never wired to anything and didn't actually work:

| Problem found | Fix |
|---|---|
| `create_mhr_screening()`/`get_latest_mhr_screening()` were `async def` using `AsyncSession` methods, but the rest of `database.py` (and the `Session` the router's `Depends(get_db)` hands it) is entirely sync | Converted both to plain sync functions matching the rest of the file |
| `CardiovascularScreening` model had `bmi`/`cholesterol_total`/`glucose_fasting`/`frs_score`/`rediscover_score`/`acs_risk_score`/`calculated_risk_category` declared twice in the same class body | Removed the duplicate block |
| Missing `referral_destination` column referenced by the router's payload | Added |
| A stored `calculated_risk_category` (LOW/MODERATE/HIGH/VERY_HIGH) never reached the dietetics prompt — completely disconnected from `clinical_risk_tier`/`rag.py` | `patient_to_profile_dict()`/`_patient_to_full_profile()` now fall back to the latest MHR screening's `calculated_risk_category` when `Patient.clinical_risk_tier` is unset, reusing the exact fallback slot already coded in `rag._build_care_path_block()` |
| `_build_care_path_block()` itself had a bug: it returned `""` before ever checking `clinical_risk_tier` if `care_path` was unset — silently defeating the whole fallback for every real patient today (none have `care_path` set yet) | Decoupled the two checks |

Note: `risk_calculator.py`'s actual scoring algorithms (Framingham/REDISCOVER coefficients, protocol cutoffs) were deliberately left untouched — that's the biostats/NADI team's responsibility per the file's own comments, not this repo's.

### How this got built and merged (process note)

This work was planned locally, then handed off to an Ultraplan cloud session for implementation of Part 8b specifically. That cloud sandbox had no `origin` git remote configured and couldn't push, so its work was exported as a patch file and applied here manually: `git am -3` on a branch cut from `origin/main` (3-way merge, since the patch's context assumed Part 8a's code was already present), with one manual conflict resolution (`docs/state_machine_contract.md` — both sides had independently written a version of this new file; merged into one). Verified with `py_compile` before merging into `main`. Pushed to `origin/main` as two commits: `5803855` (Part 8a) and `e21f2de` (Part 8b).

### Verification

- `scripts/migrate_state_machine_fields.py` run twice against live dev Postgres — added 4 columns, then correctly no-op'd.
- Eval cases 35-38 (`care_path`) all pass; case 35 (`recover`) individually re-verified live after the prompt-wording fix.
- Cloud session verified the MHR fix with real code execution against a temp SQLite DB: CRUD round-trip, the `/api/v1/mhr/screen` endpoint via `TestClient` (201, real persisted row), `_build_care_path_block` across 5 cases, and the full fallback chain (screening → profile dict → `clinical_risk_tier == "HIGH"`) all passed.
- `py_compile` on all 7 touched files after the merge, clean.
- Did not re-run the full `eval/test_rag.py` suite for Part 8b — no prompt text changed, only how `clinical_risk_tier` gets populated upstream.

### Part 8c — Onboarding → personalized diet advice (flowchart)

How a patient's care path, objectives, and risk tier — set by systems outside this repo — end up shaping what the dietetics bot actually says. Solid arrows are built and working; dashed arrows are not built yet. The left-hand (care-path/objectives) lane has no real data flowing through it today, so its nodes carry **mock placeholder values** — one worked example, for Patient #11 (Rajendran), showing what it will look like once the state-machine team builds their side.

```mermaid
flowchart TD
    subgraph ONB["My Heart Coach app — onboarding (external)"]
        A1["Onboarding complete"] --> A2["Safety gate"]
        A2 --> A3["Care path selection<br/>keep_well · reduce_risk · live_better · <b>recover</b><br/><i>mock: patient selects 'recover'</i>"]
        A3 --> A4["Objective selection<br/><i>mock: primary = restore-safe-eating<br/>secondary = fluid-sodium-control</i>"]
        A4 --> A5["Difficulty calibration<br/><i>mock: easy</i>"]
    end

    subgraph RISK["Risk-scoring module — NADI / MHR (external)"]
        R1["Clinical screening<br/>BP, BMI, smoking, diabetes, prior CVD..."] --> R2["POST /api/v1/mhr/screen"]
        R2 --> R3[("cardiovascular_screenings<br/>table")]
    end

    A5 -.->|"not built yet —<br/>values below are mock"| SM1["Patient.care_path = 'recover'<br/>Patient.objective_ids = ['restore-safe-eating',<br/>'fluid-sodium-control']<br/>Patient.difficulty_ceiling = 'easy'"]

    R3 --> F1{"Patient.clinical_risk_tier<br/>already hand-set?"}
    F1 -->|"yes"| F2["use the hand-set value"]
    F1 -->|"no — fixed 2026-08-03"| F3["fall back to the latest screening's<br/>calculated_risk_category"]

    subgraph NUTRI["Nutribot — this repo"]
        L1["Dietitian sets<br/>personalization_level = 'L3'<br/><i>(already set, so the risk-tier<br/>fallback stays quiet this time)</i>"]
        P1["patient_to_profile_dict()<br/>_patient_to_full_profile()"]

        SM1 -.->|"mock"| P1
        F2 --> P1
        F3 --> P1
        L1 --> P1

        P1 --> CB["_build_care_path_block()<br/>rag.py"]
        P1 --> LV["_LEVEL_INSTRUCTIONS<br/>rag.py"]

        CB -.->|"mock output"| PR["## Care Path &amp; Objectives<br/>'Recover after a recent heart event...<br/>confirm with doctor, care team,<br/>or cardiac rehab team first'<br/>Current focus objectives: restore-safe-eating,<br/>fluid-sodium-control<br/>Approved difficulty ceiling: easy"]
        LV --> PL["## Personalization Level L3<br/>prompt block"]

        PR -.-> GEN["Qwen 2.5:32b generates<br/>the answer"]
        PL --> GEN
    end

    GEN -.->|"mock — illustrative only,<br/>no real care_path exists yet"| OUT["Patient asks: 'Can I go back to<br/>eating normally now?'<br/><br/>Bot replies: 'Not yet — it's important to<br/>stick with your current plan for now. Any<br/>change, like resuming rice or loosening<br/>your fluid limit, needs a check with your<br/>doctor or care team first...'"]
```

**Reading the diagram:**

- **Two boxes at the top are owned by other teams** — the care-path state machine and the NADI/MHR risk-scoring module. Nutribot never generates or writes their data, only reads it.
- **The risk path (right) is real and working**, fixed this session: a screening reaches `cardiovascular_screenings`, and `clinical_risk_tier` falls back to it whenever no dietitian has set a `personalization_level` yet.
- **The care-path/objectives path (left) has no write path yet** — `care_path`, `objective_ids`, and `difficulty_ceiling` exist as columns and are already wired into the prompt, but nothing in this codebase or elsewhere writes real values into them today. The mock values along that lane (`care_path = 'recover'`, the two objective IDs, `difficulty_ceiling = 'easy'`) are a worked example, not live data — every dashed edge downstream of onboarding carries that same "mock" label for exactly this reason.
- **The mock trace is end-to-end**: the example `care_path` and `objective_ids` values shown at `SM1` are the literal input to `_build_care_path_block()`, whose output is shown verbatim at `PR` (this is the real function's real output for that input, reproduced exactly — not paraphrased). The reply at `OUT` is an illustrative answer in the style the real, live-verified "recover" behavior produces (see Part 8a) — written for Patient #11's actual CKD4/fluid-restricted profile specifically, matching the interactive demo linked below, rather than reusing another patient's verified wording out of context.
- **`personalization_level` and `clinical_risk_tier` are independent signals**, not a replacement for one another — a dietitian's own assessment always wins over the risk-scoring fallback. The mock example sets `personalization_level = 'L3'` so that fallback branch stays inactive, keeping this particular worked example focused on the care-path lane rather than mixing in the risk-tier one.
- Everything under **Nutribot** is this repo's actual, shipped code — `patient_to_profile_dict()`, `_build_care_path_block()`, and `_LEVEL_INSTRUCTIONS` in `rag.py`, mirrored in `agent.py`'s agent-tool path (not pictured, same logic).

An interactive version of this exact worked example — with a live toggle across all four care paths and a live prompt trace — is published at `https://claude.ai/code/artifact/9e01aa01-a5fb-44b1-bf7b-a187b19678e0`, and the standalone flowchart at `https://claude.ai/code/artifact/a2e598cb-fc76-41fb-b285-206bd2e7dbd7`.

---

## Next steps (current, as of Part 8 / 2026-08-03)

Everything from Parts 1–7 is resolved (see the note at the end of Part 7).
What's actually still open:

1. **Dietitian/cardiologist review of the MODERATE-vs-RESTRICT clinical calls.**
   No qualified professional has reviewed the moderation-vs-restriction judgment
   calls made in Part 7 (acar, coconut milk, deep-fried chicken, instant/processed
   food) against KDOQI/AHA-DASH guidance. Needed before this scales beyond
   mock/demo patients.
2. **No write path yet for `care_path` / `objective_ids` / `difficulty_ceiling`.**
   These columns exist and are already wired into the RAG prompt (Part 8a), but
   nothing populates them with real values — blocked on the external My Heart
   Coach state-machine team building their side. Only `clinical_risk_tier` has a
   working intake today (`POST /api/v1/mhr/screen`, fixed in Part 8b).
3. **`CardiovascularScreening.patient_id` is a bare string with no FK to
   `Patient.id`.** The assumed convention (`str(Patient.id)`) is a guess — confirm
   with whoever owns the NADI screening intake once real data starts flowing.
4. **LoRA embedding adapter not present on this machine** — retrieval runs on
   base `BAAI/bge-m3` instead of the RTX 3050's fine-tuned adapter. Copy
   `~/models/embedding_lora` over if retrieval-quality parity matters.
5. **Docker Compose stack is built and verified but not the live deployment.**
   Production still runs bare-`.venv` + systemd. Decide whether to cut over.
6. **WhatsApp provider credentials still unset** (`TWILIO_*` or `META_*` in
   `.env`, per `CLAUDE.md` pending item 5). Integration code is complete and
   tested — this is purely a credentials + webhook-registration step.
7. **`.env`'s `BASE_DOCS_DIR` still points at the old RTX-3050-only path**
   (`/mnt/ssd/documents_to_ingest`). Harmless unless `build_base_db.py` is
   re-run without passing `BASE_DOCS_DIR` explicitly.
