# Evaluation Methodology, Architecture Roadmap & Fine-Tuning Plan

Written 2026-07-16. This is a forward-looking plan, not a status report — items here are proposed work, not completed work. Cross-reference CLAUDE.md's "Known Issues" and "Pending Work" sections, which this doc extends.

## Why this doc exists

Nutribot has real eval infrastructure (`eval/eval_ragas.py`, `eval/test_rag.py`, `eval/test_extractor.py`) and real fine-tune infrastructure (`finetune/`), but they were built incrementally and have drifted from what's actually in production. The clearest example: `eval/test_rag.py` case id=2 ("CKD+HTN: can I eat bananas?") is marked `passed: true` in `eval/results/rag.json`, but the stored answer text reads *"a small banana is generally fine as an occasional treat"* for a CKD Stage 3 patient — this is precisely the failure mode CLAUDE.md's Known Issues table already warns about ("CLaRa sometimes recommends bananas to CKD patients"). The check passed only because it looks for the words "potassium" and "kidney" appearing somewhere in the answer, not for whether the answer's actual clinical *direction* (permit vs. restrict) is correct. Fixing that gap is the throughline for Part A below.

---

## Part A — Evaluation Methodology

### Current state

| Component | What it does | Gap |
|---|---|---|
| `eval/test_rag.py` | 10 cases, calls the real production path `rag.get_rag_response()`, checks via `required_terms`/`min_required` substring match + `forbidden_terms` + `voice_check` + `personalization_check` | Right call path, wrong assertion method — substring matching can't catch a direction-flipped clinical answer (see banana case above) |
| `eval/eval_ragas.py` | Computes RAGAs faithfulness / answer_relevancy / context_precision / context_recall | Evaluates via `chain_factory.create_conversational_chain()`, which is **dead code in production** (only reachable if both `USE_CLARA` and `USE_CLARA_COMPRESS` are false; prod has `USE_CLARA_COMPRESS=true`). RAGAs has been scoring a code path patients never talk to. |
| `eval/eval_dataset.json` | 25 generic knowledge-recall Q&A pairs | No patient profile, no personalization level, no bilingual (BM) coverage |
| `eval/results/*.json` | Single JSON snapshot per suite | Overwritten each run — no history, no way to tell if a model/prompt change helped or hurt |
| `test_bot_accuracy.py` / `test_bot_culture.py` | Manual scripts hitting the live streaming endpoint, human reads colored output | No assertions, not CI-able, purely eyeball QA |
| CI | — | None. No `.github/workflows` anywhere in the repo — every suite above is run by hand. |

### Framework survey: RAGAS vs. TruLens vs. DeepEval

Before extending the homegrown eval further, it's worth checking whether an existing eval framework already solves part of this rather than hand-rolling more of it. Researched 2026-07-17. All three support a **fully self-hosted judge LLM** (Ollama, LiteLLM, or a hand-wrapped base class) — important here specifically because Nutribot's eval cases carry real patient conditions/profiles, and routing judge calls through an external API (e.g. `gpt-4o-mini`) means patient clinical data leaves the hospital-controlled environment with no BAA/compliance review in place (the IP-ownership question in Part B #7 is still open, and this is the same category of unresolved contractual question). That rules out the "or `gpt-4o-mini`" option floated in item 2 below as a default — `qwen2.5:32b` itself (already self-hosted on the Mac Studio) should be the default judge model for all three frameworks unless/until data handling is explicitly cleared.

| Framework | What it's actually good at | Fit for Nutribot |
|---|---|---|
| **RAGAS** | Retrieval-grounding metrics: faithfulness (does the answer stick to retrieved context), answer relevancy, context precision/recall. Judge LLM is pluggable via `LangchainLLMWrapper` around any LangChain chat model, including `ChatOllama` — no OpenAI dependency required. | Already partially wired (`eval/eval_ragas.py`, fixed in Part A #1 to hit the real pipeline). Keep it scoped to what it measures well — **is the retrieved context being used faithfully** — which is a different axis from clinical correctness. It has no built-in notion of "expected stance"; forcing contraindication checking into a custom RAGAS metric would just re-implement `judge_stance()` inside a heavier framework for no benefit. |
| **DeepEval** | `G-Eval` — a research-backed LLM-as-judge metric that scores against a natural-language custom criterion via chain-of-thought, essentially a formalized, calibrated version of the `judge_stance()` function already hand-built for this project. Native pytest integration (`assert_test`, `@pytest.mark`) — directly usable given `test_rag.py`/`test_extractor.py` were already made pytest-collectible in Part A #7. Supports a fully local judge via `DeepEvalBaseLLM` (wrap Ollama directly, no LangChain dependency needed). Also ships hallucination, bias, and toxicity metrics, plus a red-teaming/vulnerability scan module. | **Best fit for the actual gap this doc opened with.** Recommend adopting `G-Eval` as the judge implementation behind the `contraindication_check` mechanism (item 2 below) instead of maintaining a bespoke prompt/parsing function — same data shape (`food`, `condition`, `expected_stance`), same test cases, but a maintained, published implementation instead of one this project owns and has to keep correct. The bias metric is also worth a look given Nutribot's patient base spans multiple Malaysian ethnicities (`ethnicity` is a first-class Patient column) — a systematic bias check across ethnicity-varying personas is currently not covered by anything in `test_rag.py`. |
| **TruLens** | A different category entirely — not a pre-deploy fixed-case test suite but a *production tracing/observability* tool. The "RAG triad" (context relevance, groundedness, answer relevance) scores **live conversations** after the fact via `@instrument`-decorated spans, surfaced in a running dashboard. | Nutribot already persists every real conversation (`chat_messages` table, added for conversation-history persistence). TruLens would be the natural way to continuously score *actual patient traffic* rather than only the fixed 34-case matrix — catching failure modes the hand-authored cases don't anticipate. But it adds a standing dashboard service and dependency footprint on top of an already resource-constrained split-machine setup (RTX 3050's small GPU, the exFAT-drive fragility already noted in Part B). **Recommend as an opt-in Phase 2 item, not part of closing Part A** — valuable for ongoing production monitoring once the core eval-quality gaps here are closed, not required to close them. |

**Net recommendation**: keep RAGAS scoped to retrieval-grounding metrics (already the plan per item 1), adopt DeepEval's `G-Eval` as the engine behind the directional/clinical-correctness judge (item 2, superseding the bespoke `judge_stance()` prototype once ported over — the case data and matrix in items 2–5 don't change, only the judge implementation does), and defer TruLens to a later phase focused on live-traffic monitoring rather than pre-deploy testing.

### Recommended fixes, in priority order

1. **Point `eval_ragas.py` at the real pipeline.** Swap `create_conversational_chain()` for `rag.get_rag_response()` — the same call `test_rag.py` already uses. One-function change, outsized correctness value: until this lands, RAGAs scores tell you nothing about the deployed Option B pipeline (CLaRa compress → Qwen generate).

2. **Add a directional/clinical-correctness check.** Introduce a `contraindication_check` case type, e.g.:
   ```json
   {"contraindication_check": {"food": "banana", "condition": "CKD", "expected_stance": "restrict"}}
   ```
   Verify it via DeepEval's `G-Eval` metric (see framework survey above), judged by a self-hosted model (`qwen2.5:32b` via Ollama — **not** an external API, given patient clinical data is in the prompt) that classifies the answer's stance toward that food as `permit` / `moderate` / `restrict`, compared against `expected_stance`. Keep existing keyword checks as a cheap first-pass filter, but for any case tagged `contraindication`, gate "passed" on the directional judge, not the keyword match alone. (The hand-rolled `judge_stance()` already prototyped and verified this exact mechanism against the live pipeline — see the 2026-07-16 live baseline run below — porting it to `G-Eval` is a maintainability upgrade, not a redesign.)

3. **Build a systematic contraindication matrix.** For each condition already in the patient DB (CKD, HTN, T2DM, Dyslipidaemia, HF, PCOS) × 3–5 commonly-confused foods (banana, durian, coconut milk/santan, white rice, processed/salted food), add a case with an explicit `expected_stance`. This turns "CLaRa recommends bananas to CKD patients" from one lucky-catch case into a systematic net — roughly 20–30 new cases in `eval/test_rag.py`.

4. **Add bilingual (BM) coverage.** Mirror a subset of the new contraindication cases in Bahasa Malaysia. `extractor.py`/`test_extractor.py` already prove BM input works well elsewhere in the app; the RAG-answer eval currently has zero BM cases.

5. **Fill personalization-level gaps.** Only 1 of 10 current cases checks L3. Add ≥2 cases each for L1/L2 so all four tiers (L0–L3) have real coverage, and extend the existing "L0 shouldn't be over-restricted" case with a couple more.

6. **Add result history instead of overwriting.** Append `{date, git_commit, passed, failed, category_breakdown}` to a JSONL log (a small `scripts/eval_history.py` wrapper around the existing `--out` flag) rather than clobbering `results/rag.json`/`results/extractor.json` every run. This is what makes it possible to tell whether a CLaRa/Qwen update or prompt tweak made things better or worse over time.

7. **Make the suites pytest-collectible and run them nightly.** Wrap each `CASES` entry as a `@pytest.mark.parametrize` test; add a cron entry mirroring the existing `content_scheduler.py`/`weekly_eka_scheduler.py` pattern, running `--smoke` against the live Mac Studio models nightly, logging to `logs/eval_nightly.log`. This doesn't need the RTX 3050's Postgres for the CLaRa/Ollama-only smoke cases, so it can run even during an RTX 3050 outage.

8. **Fix the error-leakage bug found alongside this investigation** (`website_chat_router.py`, roughly the exception handler around the streaming response): raw exception text is currently yielded straight into the patient-facing chat on any `get_rag_response` failure. Not an eval item per se, but a safety-adjacent bug worth fixing in the same pass — replace with a generic user-facing message plus server-side logging of the real exception.

### Live baseline run — 2026-07-16

Items 1–7 above were implemented and verified against synthetic/offline data (no live Mac Studio access from the machine that wrote them, at the time). Separately, `eval/live_pipeline_smoke_test.py` was built as a dependency-free (stdlib-only) harness that exercises the *actual* live CLaRa+Ollama models over their Cloudflare tunnels directly — bypassing `rag.py`/`database.py`/PGVector entirely (hardcoded patient profiles, AST-extracted `CASES`/`CONTEXT_SAMPLES` from the real source files so there's no drift between the harness and the real eval matrix, verbatim-ported `judge_stance()` and prompt-building logic) — for exactly the situation where the RTX 3050's Postgres is unavailable but the Mac Studio isn't.

Run against all 25 `contraindication_check`-tagged cases from `eval/test_rag.py`, results saved to `eval/results/rag_live_baseline_2026-07-16.json`:

**21/25 passed.** The 4 failures share one consistent pattern — the model says `moderate` ("fine in small amounts / occasionally") where the correct clinical stance is `restrict` (avoid it outright). It never fails in the other direction (no case where a safe food gets over-restricted):

| Food | Condition | Judged stance | Expected |
|---|---|---|---|
| banana | CKD Stage 3 (potassium-restricted) | moderate — the answer actively praised its potassium content | restrict |
| acar (pickled vegetables) | Hypertension | moderate | restrict |
| deep-fried chicken | Dyslipidaemia | moderate | restrict |
| instant/processed food | Pre-hypertension | moderate | restrict |

This confirms the original motivating "banana for CKD" Known Issue is still live in production as of this date, and narrows it from "the model sometimes gets contraindications wrong" to a specific, actionable pattern: **the model hedges genuine restrictions into moderation language**, specifically for foods with some redeeming nutritional property (potassium, home-style preparation, familiarity) that it weighs against the contraindication instead of overriding it. This is exactly the kind of narrow, well-characterized weak spot Part C's `--focus-results` mechanism was built to oversample in synthetic training data.

---

## Part B — Architecture Forward Plan

### Concrete risks (found by reading the code, not just restating known issues)

- **No generation fallback.** `call_clara_compress()` in `rag.py` falls back to raw chunks if CLaRa is down, but `call_ollama_generate()` has no fallback at all. `llm.py` already has a working `OPENAI_API_KEY` / `get_llm()` path — it's just never wired as a backstop. A full Mac-Studio/tunnel outage today means **100% generation failure**, not graceful degradation.
- **Shared failure domain.** Compress and generate both go over the *same* Cloudflare tunnel to the *same* Mac Studio. A tunnel misconfig or Cloudflare-side incident kills both simultaneously — a bigger blast radius than "the public URL is down" suggests.
- **Timeout stacking exceeds the observed client timeout.** `call_clara_compress` (120s) + `call_ollama_generate` (180s) can serially take up to 5 minutes, but the public Cloudflare path is already known to time out client-side at ~100s (CLAUDE.md item 6). A degraded-but-alive backend is today functionally indistinguishable from a dead one.
- **MPS patch is untracked tribal knowledge.** The CLaRa CUDA→MPS patch lives only inside `/Users/bing/.cache/huggingface/modules/...` on the Mac Studio — not in git. A fresh HuggingFace cache pull would silently lose it, and nothing would catch a bad revert except manual smoke testing at the eventual production cutover.
- **Dead code drift risk.** `chain_factory.py`'s legacy chain (the one `eval_ragas.py` currently — incorrectly — evaluates) is unconditionally imported by `rag.py` and maintains its own divergent system prompt alongside Option B's `_build_qwen_prompt()`. Two personas that can silently drift apart if one is edited and not the other.
- **exFAT fragility is demonstrated, not theoretical.** `/mnt/ext` (the active codebase drive) is exFAT, `nofail`-mounted, forces conda over venv. Its sibling exFAT drive `/mnt/ssd` is already 100% full — this exact failure mode has already happened once on this setup.

### Recommended forward plan, in priority order

1. ~~Wire the OpenAI fallback into `call_ollama_generate`'s call site~~ — **deliberately skipped per explicit decision**: a full Mac Studio/tunnel outage still means 100% generation failure, no cross-provider fallback. Not a gap that was missed; a scope call.
2. **Fix the error-leakage bug** (same item as Part A #8). — **Done 2026-07-16**: `website_chat_router.py`'s `stream_rag_response()` no longer yields raw exception text to the patient chat.
3. **Bring the compress+generate timeout budget under the ~100s client ceiling.** — **Done 2026-07-16**: `llm.py` now uses `CLARA_COMPRESS_TIMEOUT_S=40` + `OLLAMA_GENERATE_TIMEOUT_S=50` (90s combined, env-overridable), down from a ~300s worst-case stack (120s + 180s). `CLARA_GENERATE_TIMEOUT_S=90` for the single-call CLaRa-primary path.
4. **Commit the MPS patch as a tracked diff** — e.g. `patches/modeling_clara_mps.patch` plus a small apply script or Makefile target — so the eventual CUDA revert for production is a mechanical patch-apply, not manual re-editing from memory. — **Done 2026-07-16**: as `patches/mps_cuda_patch.py` + `patches/README.md`, not a literal `.patch` file — the real `modeling_clara.py` lives only on the Mac Studio's HuggingFace cache and was never accessible from this session, so a hand-authored diff against unseen content would have been guessing. The script instead applies the same mechanical substitutions in either direction (`--to-cuda` / `--to-mps`) and was verified via a `--demo` mode against a built-in sample snippet. Still manual, documented in the README: bfloat16 dtype choice (optional) and removing `PYTORCH_ENABLE_MPS_FALLBACK=1` (a LaunchDaemon env var, not a source-file line).
5. **Quarantine or remove the dead `chain_factory.py` legacy path** once `eval_ragas.py` is repointed at `rag.get_rag_response()` (Part A #1) — nothing will still need it. — **Done 2026-07-16**: removed the legacy branch and its import from `rag.py` entirely (confirmed `create_conversational_chain` had exactly one remaining caller). `get_rag_response()` now raises a clear `EnvironmentError` if no generation path is enabled, instead of silently falling through. Also removed `identify_target_disease()`, which became dead code itself once its only call site (the profile-less branch of the removed legacy path) was gone — it was a wasted LLM round-trip on every profile-less request. `chain_factory.py` itself is untouched — `get_system_template()` is still used by `finetune/generate_training_data.py`.
6. **Medium-term**: once the production Linux+NVIDIA box is actually provisioned, the cutover rehearsal is materially lower-risk because of steps 2–5 (tracked patch once #4 lands, no dead-code drift, faster failure detection under the current split-machine setup — note: still no cross-provider fallback, per the #1 decision).
7. **Flag, don't solve, the IP ownership question.** Work-for-hire vs. license-back is still open per CLAUDE.md's Contacts & Context section. Call this out explicitly as a blocker to any SaaS-reuse discussion — it's a contractual decision, not a technical one.

---

## Part C — Fine-Tuning Plan, Targeted at Eval Failures

**Goal**: close the loop. Use whatever Part A's expanded eval turns up as the most common failure categories to drive *targeted* synthetic training data, instead of the current uniform random sampling.

### Current fine-tune scaffolding (already built — reuse, don't rebuild)

- `finetune/generate_training_data.py` — GPT-4o-generated synthetic ADIME conversations across a persona × condition × context matrix, output as ShareGPT-format JSONL for LoRA/Unsloth/TRL.
- `finetune/generate_embedding_training_data.py` + `finetune/finetune_embeddings.py` — LoRA fine-tune of `bge-m3` embeddings using (question, passage) pairs mined from the live PGVector knowledge base.
- **Gap found**: `finetune/Modelfile` and `finetune/colab_finetune.ipynb` target a **Gemma-3** base model — a separate experiment track, not the production `qwen2.5:32b`.

**Decision**: target `qwen2.5:32b` directly going forward (not the Gemma-3 track) — it directly improves the model patients actually talk to, and the Mac Studio's M3 Ultra 96GB unified memory has the headroom for a 32B LoRA/QLoRA job.

### Recommended approach

1. **Target `qwen2.5:32b` directly via LoRA/QLoRA**, trained on the Mac Studio. This supersedes the Gemma-3 experiment track as the primary fine-tuning effort — the Gemma-3 work can continue separately if there's ever a reason to ship a smaller/cheaper model, but it's not the path to improving what's in production today. — **Documented 2026-07-16** in `finetune/QWEN_FINETUNE.md`: base model, QLoRA rationale (32B at bf16 ≈ 64GB, tight against the Mac Studio's 96GB unified memory alongside activations/gradients — 4-bit QLoRA brings that down to ~16-18GB), starting hyperparameters, and the merge/quantize/deploy pipeline. Documentation only — actually running the training job needs real GPU time this session didn't have, so treat the hyperparameters as a starting point to verify empirically, not as already-tuned values.

2. **Feed eval failure categories back into `generate_training_data.py`.** Once Part A #6/7 give us eval history, tag failing cases by `{condition, contraindicated_food, expected_stance, language}`. Extend `generate_training_data.py`'s `META_PROMPT`/`CONTEXT_SAMPLES` mechanism to accept a "focus" parameter that oversamples exactly those weak combinations — e.g. if CKD+banana-style direction errors turn out to be the most common failure, generate many more ADIME conversations that explicitly model the assistant correctly *restricting* (not just mentioning) contraindicated foods for that condition, in both English and Bahasa Malaysia. — **Done 2026-07-16**: `eval/test_rag.py`'s `run_case()` now returns the `contraindication_check` dict alongside each result (so failing combos survive into results JSON), and `generate_training_data.py` gained `--focus-results <path>` + `--focus-weight <n>` — it reads a results JSON, extracts distinct failing combos via `load_focus_combos()`, picks the clinically conservative stance to target via `_target_stance()` (restrict > moderate > permit when multiple are acceptable), and generates that many extra conversations per combo using a new `FOCUS_ADDENDUM` prompt block. The extraction/stance logic was verified against a synthetic results JSON matching the real output shape; the full generation path (which calls OpenAI) couldn't be executed in this session (no `openai`/`dotenv` packages installed here).

3. **Gate the fine-tune with eval, both ways.** Before merging any new LoRA adapter into the production Ollama model, re-run the full expanded `test_rag.py` (contraindication matrix + bilingual + personalization cases) against the fine-tuned model and compare to the pre-tune baseline using the same eval-history log from Part A #6. Only promote the adapter if the targeted failure categories measurably improve *and* nothing else regresses. — **Done 2026-07-16**: `scripts/compare_eval_runs.py` — takes a baseline and candidate results JSON, reports per-case regressions/improvements and per-tag pass rates, and prints a PROMOTE / DO NOT PROMOTE verdict (exit 0/1, so it can gate a deploy step). Verified against synthetic baseline/candidate pairs: a clean-improvement pair correctly PROMOTEs, a mixed pair (one fix, one new regression) correctly blocks promotion.

4. **Apply the same closed loop to embeddings** if Part A's retrieval-quality visibility improves enough to surface systematic retrieval misses (currently retrieval scoring only exists as `[TopicBoost]` print statements in `vector_store.py`, with no persisted signal). If it does, use `generate_embedding_training_data.py` to mine additional pairs specifically for the underperforming topics, rather than uniformly re-mining the whole knowledge base. — **Not done**: blocked on the retrieval-quality visibility gap itself, which nothing in Parts A/B closed — `vector_store.py`'s `[TopicBoost]` scores are still print-only with no persisted signal to build this on.

---

## Suggested execution order

This is a lot of surface area. If picking work up incrementally, the natural dependency order is:

1. Part A #1 (repoint RAGAs) and #8 / Part B #2 (error leakage) — both are small, immediate correctness/safety fixes.
2. Part A #2–#5 (contraindication matrix + bilingual + personalization coverage) — the actual eval-quality upgrade.
3. Part A #6–#7 (history + nightly cron) — makes everything after this point trend-trackable.
4. Part B #1, #3–#5 (fallback wiring, timeout budget, tracked MPS patch, dead-code removal) — architecture resilience, can happen in parallel with the eval work.
5. Part C — depends on Part A's history mechanism existing first, since it's driven by "most common failure categories," which requires having run the expanded eval enough times to know what those are.
6. Part B #6 (production cutover) — depends on Part B #4 (tracked patch) at minimum.

---

## Part D — Status update and next steps (2026-07-29)

Parts A #1–#7 and Part B #2–#5 above are now all done (see `REPORT.md` Parts
3–7 for the narrative). Status of everything else this doc left open, plus
what a fifth full eval run today turned up:

### Where the RAG suite stands

The 34-case matrix (Part A #2–#5's contraindication/bilingual/personalization
coverage) has now been run five times. Today's run went 25/34 → **31/34**
(the best result yet) after root-causing 3 of the 9 failures as real prompt
gaps rather than sampling noise — see `eval/results/EVAL_REPORT.md` for the
full breakdown. Remaining 3 failures, all `personalization_check`:

1. **Coconut milk (santan) in general** and **instant/processed food in
   general** — both ask about a *food category*, not a single dish, and the
   model still says "limit your intake" without a concrete number. Every
   single-dish L1 case (roti canai, gulai bersantan specifically) now gets a
   number reliably; category-level questions don't yet. Recommend leaving
   this as a documented known limitation rather than forcing the prompt
   further — an open-ended category doesn't always have one natural number,
   and over-fitting the prompt to these two specific eval questions risks
   making real answers worse to make two test cases pass.
2. ~~Case 34 (BM gulai bersantan) looks like a judge misclassification~~ —
   **confirmed 2026-07-29**: 3 standalone re-runs all passed, each answer
   containing a clear weekly frequency limit ("sekali seminggu" / "1-2 kali
   seminggu") and correctly recognized by the judge each time. This was
   ordinary run-to-run judge noise on a single draw, not a systematic BM-
   language blind spot — no `judge_personalization` prompt change needed.

### Full-suite staleness — a real gap, not just today's oversight

~~The nightly cron only runs `eval/test_rag.py --smoke`~~ — **fixed
2026-07-29**: added `0 4 * * 0` (Sunday 4am, after the 3am nightly smoke has
cleared) running the full 34-case RAG suite + 20-case extractor suite, both
logged via `scripts/eval_history.py` into `rag_history.jsonl` /
`extractor_history.jsonl`, output to `logs/eval_weekly.log`. Uses `;` (not
`&&`) between the two suite runs so a test-runner's exit-1-on-failures
doesn't skip the extractor run — see `crontab -l`. Nightly stays smoke-only;
weekly now catches full-suite drift automatically instead of by accident.

### Still open from the original framework survey

- **DeepEval `G-Eval` migration was never done.** `judge_stance()` and
  `judge_personalization()` in `eval/test_rag.py` are still the hand-rolled
  prototype this doc originally described as a stopgap. Migrating to
  DeepEval's `G-Eval` is still the right long-term call (a maintained,
  published judge implementation vs. one this project has to keep correct
  itself) but adds a new dependency and needs verification that a local
  Ollama judge model plugs into `DeepEvalBaseLLM` cleanly — scope as its own
  follow-up session, don't fold it into routine eval maintenance.
- **Part C #4 (embedding closed-loop) is still blocked.** `vector_store.py`'s
  `[TopicBoost]` scores remain print-only (confirmed again today) — no
  persisted signal exists to tell whether retrieval or generation is the
  bottleneck on any given failure. Smallest viable next step: persist
  boost/rerank scores per query to a log (same JSONL pattern as
  `eval_history.py`) rather than building a full retrieval-eval harness
  up front.
- **Part C #1 (the actual LoRA/QLoRA training run) still hasn't happened** —
  `finetune/QWEN_FINETUNE.md` documents the plan, but running it needs real
  Mac Studio GPU time. `finetune/generate_training_data.py --focus-results`
  is built and ready to consume exactly this kind of eval-failure JSON
  whenever that GPU time is available — once 2-3 more full runs accumulate
  in `rag_history.jsonl`, the "category-level food lacks a concrete number"
  pattern above is a reasonable first target for a focused synthetic batch.
- **No CI gate exists**, and this is a real constraint rather than an
  oversight: both suites are pytest-collectible, but they need live network
  access to the Mac Studio's private Cloudflare tunnels, which a hosted CI
  runner doesn't have. Not proposing a GitHub Actions workflow until/unless
  that constraint changes.

### Priority order for picking this up

1. ~~Confirm/refute the case-34 judge misclassification~~ — **done
   2026-07-29**, see above. RAG suite is effectively 32/34-clean once this
   noise draw is excluded (only the 2 category-level food gaps remain as a
   genuine, documented limitation).
2. ~~Add the weekly full-suite cron~~ — **done 2026-07-29**, see above.
3. Everything else (DeepEval migration, retrieval-visibility logging, actual
   fine-tune run) — larger, each deserves its own session rather than being
   squeezed in alongside routine eval maintenance.
