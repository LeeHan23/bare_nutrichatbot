# MyHeartCoach / Nutribot — Roadmap to 2026-12-31

_Written 2026-09-28. This is the **single source** for status and timeline;
other docs link here instead of keeping their own "next steps" lists. For a
PDF, use any Markdown-to-PDF tool (e.g. the VS Code "Markdown PDF"
extension, or pandoc with `--pdf-engine=xelatex`), in landscape so the week
grid in §2 fits the page width._

**Maintenance rule:** any commit that finishes, starts or unblocks a roadmap
item also updates this file's status board **and** the Pending Work list in
`CLAUDE.md`, in the same commit.

**Strategic objective for Q4 2026:** a **proprietary MyHeartCoach house voice**.
Chat answers and weekly EKA content should sound like one recognisable
program, the voice of the team's own clinicians, instead of generic LLM
output. The eval pipeline measures that voice, and the EKA review loop
supplies the examples it learns from.

---

## 1. Status board (as of 2026-09-28)

### Modules (`taxonomy.COMPONENTS`, 11 slugs)

Every module has real `COMPONENT_SCOPE` text; `taxonomy.py`'s self-check
asserts none fall through to `_NO_CONTENT_GUARD`.

| Module | Grounded chunks | EKA group | Eval cases | Status |
|---|---|---|---|---|
| nutrition | 49,983 | General, CKD, PCOS, most others | 82 (contraindication 25, myth 22, bilingual 10…) | done |
| exercise | 1,929 + 199-video catalog | E-items grounded in the catalog | 4 scope (new) | in progress |
| foundations | 5,099 | Cardiac, AF, HF, CVD Risk | 4 scope (new) | in progress |
| blood_pressure | 573 | HTN | 4 scope (new) | in progress |
| lipid | 2,034 | Dyslipidaemia | 4 scope (new) | in progress |
| diabetes | 935 | T2DM | 4 scope (new) | in progress |
| weight (added 2026-09-07) | 809 | none | 4 scope (new) | in progress |
| tobacco_nicotine_alcohol | 565 | none | 6 scope | in progress |
| physical_activity | 400 | none | 4 scope (new) | in progress |
| psychosocial | 388 | Mental Health, Stress, Sleep | 6 scope | in progress |
| medication | 225 | none | 8 scope | in progress (thin by design) |

Chunk counts are `doc_components` tags in `base_knowledge` (DB query
2026-09-28; a chunk can carry more than one tag). Every module now has
scope-adherence eval cases (ids 125–172), and each case also asserts that
the question routes to its module (see §2, M1).

### Workstreams

| Workstream | Status | Evidence | Next | Blocker |
|---|---|---|---|---|
| House voice (tone) | not started | none; see §3 | Phase 1 | – |
| Chat RAG (Option B) | live | `rag.py`, `structured_store.py` | voice wiring | – |
| Weekly EKA generation + review | live (Monday cron) | `scripts/generate_weekly_eka.py`, `/eka-review` | brand block, exemplars, new groups | – |
| Eval: full suite | **cron restored 2026-09-28** | last full run 2026-08-29: 47/60 | fresh baseline Sun 2026-10-04 | – |
| Eval: nightly smoke | **broken 09-01 → 09-28, fixed** (reinstalled line lacked `cd`) | `logs/eval_nightly.log` | watch the next run | – |
| Judge calibration | in progress: 50 human reviews; judge agreement myth 16/22, stance 10/17, personalization 10/11; **scope 0** | `eval.computationalrd.com`, `data/eval_calibration_reviews.json` | label + threshold sweep | reviewer time |
| Team hub sign-in | done, committed 2026-09-28 (172a3c3) | `team_router.py` | – | – |
| Eval service | done, committed 2026-09-28 (172a3c3) | `eval_api.py`, `deploy/eval.service` | label scope + voice judges | – |
| Patient self-registration | done 2026-09-16 | `POST /patient/register` | – | – |
| My Heart Coach staging DB fallback | done (read-only: L0-L3, OB flags) | `myheart_db.py` | OB mapping confirmation | MHC team |
| Fine-tuning (Qwen 32B QLoRA) | in progress: #1 DO NOT PROMOTE; #2 data ready, not run | `finetune/QWEN_FINETUNE.md` | run #2 | Mac Studio GPU time |
| Content drip scheduler | running (08:00 daily) | `scripts/content_scheduler.py` | delivery channel | WhatsApp creds |
| WhatsApp | in progress: code done | `whatsapp_router.py` | creds + webhook + phone links | Twilio/Meta creds |
| RemotePatientStore | in progress: scaffold + mock | `remote_patient_store.py` | adapt to the real spec | hospital API spec |
| Docker Compose | verified 2026-08-18 | `docker-compose.yml` | cutover decision | owner |
| Production Linux + NVIDIA | not started | `patches/mps_cuda_patch.py` ready | provision, apply `--to-cuda` | hardware |
| Missing PDFs (AHA 2021, MDG Senaman, LE8 BP) | **done** (confirmed in DB 2026-09-28) | `base_knowledge` | – | – |
| Chatbot_Chunks ingest | in progress: 1 row ingested | `scripts/ingest_chatbot_chunks.py` | re-run per workbook | client content team |

---

## 2. Timeline

Swimlanes: **V** voice · **E** eval · **K** EKA content · **M** module
coverage · **C** clinical sign-off · **P** platform · **D** docs.

### Week grid

Columns are ISO weeks starting Monday: 40 = 28 Sep, 41 = 5 Oct,
42 = 12 Oct, 43 = 19 Oct, 44 = 26 Oct, 45 = 2 Nov, 46 = 9 Nov, 47 = 16 Nov,
48 = 23 Nov, 49 = 30 Nov, 50 = 7 Dec, 51 = 14 Dec, 52 = 21 Dec, 53 = 28 Dec.
✓ done · ■ planned · □ conditional on an outside input (credentials,
hardware, GPU time, client content).

| ID | Work item | 40 | 41 | 42 | 43 | 44 | 45 | 46 | 47 | 48 | 49 | 50 | 51 | 52 | 53 |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| V1 | Voice spec (`BRAND_VOICE` block) |  | ■ | ■ |  |  |  |  |  |  |  |  |  |  |  |
| V2 | Keep draft on reviewer edit (`draft_tips`) |  | ■ | ■ |  |  |  |  |  |  |  |  |  |  |  |
| V3 | Voice in chat prompt; NutriBot → MyHeartCoach |  |  |  | ■ | ■ |  |  |  |  |  |  |  |  |  |
| V4 | Voice + exemplars in EKA generator |  |  |  | ■ | ■ |  |  |  |  |  |  |  |  |  |
| V5 | Fine-tune data uses the same voice |  |  |  |  | ■ |  |  |  |  |  |  |  |  |  |
| V6 | Weekly voice loop on Monday EKA batch |  |  |  |  |  | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ |
| V7 | Style LoRA (only if prompting plateaus) |  |  |  |  |  |  |  |  |  | □ | □ | □ |  |  |
| E0 | Weekly full eval cron restored | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| E0 | First fresh full-suite baseline (Sun 4 Oct) | ■ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| E1 | Brand-voice judge + calibration cases |  | ■ | ■ |  |  |  |  |  |  |  |  |  |  |  |
| E2 | Voice baseline: chat + one EKA week |  |  | ■ |  |  |  |  |  |  |  |  |  |  |  |
| FT | Fine-tune attempt #2 (Mac Studio) |  | □ | □ |  |  |  |  |  |  |  |  |  |  |  |
| E3 | Human labels + threshold sweep |  |  |  |  |  | ■ | ■ | ■ | ■ |  |  |  |  |  |
| M1 | Scope evals for 7 uncovered modules (28 cases) | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| M2 | Fix module-scope failures from M1 | ■ | ■ | ■ | ■ | ■ |  |  |  |  |  |  |  |  |  |
| K1 | EKA groups: weight, tobacco, medication, PA |  |  |  | ■ | ■ |  |  |  |  |  |  |  |  |  |
| K2 | Chatbot_Chunks re-ingest |  |  |  |  |  | □ | □ | □ | □ |  |  |  |  |  |
| C0 | Voice spec sign-off (client + dietitian) |  |  | ■ | ■ |  |  |  |  |  |  |  |  |  |  |
| C1 | Stance review + BM myth-hedging fix |  |  |  |  |  | ■ | ■ | ■ | ■ |  |  |  |  |  |
| C2 | IRB / ethics review |  |  |  |  |  |  |  |  |  | □ | □ | □ | □ | □ |
| P0 | Commit working tree (repairs HEAD) | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| P1 | WhatsApp pilot |  |  |  |  |  | □ | □ | □ | □ |  |  |  |  |  |
| P2 | Docker cutover + MPS→CUDA |  |  |  |  |  |  |  |  |  | □ | □ | □ | □ |  |
| D0 | Docs synced, ROADMAP written | ✓ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| D1 | Year-end TRIPOD refresh + retrospective |  |  |  |  |  |  |  |  |  |  |  |  | ■ | ■ |

### Phase 0: Stabilise and sync (W40, Sep 28 – Oct 4)
- **D:** sync every doc to the current state; stale docs archived to `docs/archive/`. Done 2026-09-28.
- **E:** weekly full eval cron restored; nightly smoke `cd` fix. Done 2026-09-28.
- **P:** commit the working tree in logical groups. Done 2026-09-28
  (172a3c3 through a5732ed); 172a3c3 also repaired HEAD's broken
  `is_admin_session` import.
- **M1 (pulled forward from Phase 2):** 28 scope cases for the 7 modules
  that had none (exercise, foundations, BP, lipid, diabetes, weight, PA;
  ids 145–172, `--tag module`). Every scope case now also asserts routing via
  `vector_store.detect_query_component`. BP, lipid, diabetes and weight had
  no routing phrases, so definitional ones were added to `COMPONENT_HINTS`
  ("what is HbA1c", "lipid panel", "my BMI"…). No existing case changed
  route. Done in code 2026-09-28. This addresses TRIPOD 19g #14.
  First live run (`eval/results/rag_module_scope.json`): 14/28 pass;
  routing was correct on all 28. Failures fell into two groups:
  - **Judge rubric errors.** It scored the mandated closing question and
    mentions of the patient's known conditions as overstepping, failed
    correct deferrals for not also educating, and read the in-scope list as
    a checklist. Fixed in `judge_scope_adherence` (per-expected pass rules
    in `_SCOPE_PASS_RULES`; the patient's conditions are now passed to the
    judge).
  - **Real bot oversteps on patients' own numbers.** "Your LDL of 4.2 is
    higher than recommended… below 2.6"; an LDL quoted from profile notes;
    an unprompted "for someone like you, keep triglycerides below 150".
    Fixed with an "Own results" rule appended to the BP, lipid, diabetes
    and weight scope blocks (`taxonomy._OWN_RESULT_RULE`).
- **M2 (2026-09-28): 26/28 across all 7 modules.** BP 4/4, exercise 4/4,
  foundations 4/4, diabetes 4/4, weight 4/4, lipid 3/4, physical
  activity 3/4 (`eval/results/rag_module_*.json`). Fixes applied:
  - **Scope judge:** per-expected pass rules; patient conditions passed in;
    allowed topics framed as optional and hidden for DEFERRED cases; the
    guideline-grounding clause stripped.
  - **Prompt rules** in `taxonomy.py`: `_OWN_RESULT_RULE` (no personal
    targets; don't interpret the patient's own numbers) for BP, lipid,
    diabetes and weight; `_CLEARANCE_RULE` ("is it safe for me / how much
    am I allowed / my prognosis" goes to the care team) for every module.
    Step-count guidance added to the physical activity scope.
  - **Exercise catalog durations:** all 199 were stored as `"02:08:00"`
    (a min:sec cell read as a time) and the bot said "2 hours 8 minutes".
    Fixed in `scripts/build_exercise_video_lookup.py` and the data; prompts
    now label the value min:sec.
  Still open:
  - **Numbers quoted from profile notes.** The model still sometimes repeats
    a lab value from the patient's profile notes as an interpretation
    ("your LDL levels are high at 4.8 mmol/L", case 157; "a BMI of 32.3
    indicates you are in the obese range", case 165, which the judge passed
    anyway), despite the rule. The next step is structural rather than more
    prompt text: keep raw lab values out of the notes the model sees for
    these modules, or add a deterministic post-check.
  - **Case 169:** a "+500 steps every week" progression tip, which the
    physical activity scope forbids.
  - **Case 154:** judge-flaky (2 of 3 standalone passes).
- **E:** first fresh full-suite baseline, Sun 2026-10-04 04:00.

### Phase 1: Define the voice, capture the signal (W41–42, Oct 5 – 18)
- **V1: voice spec.** `BRAND_VOICE` + `brand_voice_prompt_block()` in
  `taxonomy.py`, next to `eka_constraints_prompt_block`, as the single source.
  Review copy in `docs/brand_voice.md` for the client and the supervising
  dietitian.
- **V2: capture reviewer edits.** A new nullable `content_materials.draft_tips`,
  written once on the first `/eka-review` content edit, keeps the LLM
  draft. The archive workbook exports it, so before/after pairs survive
  expiry.
- **E1: brand-voice judge.** `judge_brand_voice()` in `eval/test_rag.py`, same
  GEval pattern as `judge_scope_adherence`; `brand_voice` key added to the
  calibration app.
- **E2: voice baseline** on the chat suite and one EKA week, logged via
  `scripts/eval_history.py`.
- **E (parallel):** fine-tune attempt #2 run, gated by
  `scripts/compare_eval_runs.py`.
- **C:** send `docs/brand_voice.md` for client + dietitian sign-off. (The myth set in `eval/myths_review.md` was already signed off 2026-08-31.)

### Phase 2: Wire the voice everywhere (W43–44, Oct 19 – Nov 1)
- **V3: chat.** `brand_voice_prompt_block()` replaces the ad-hoc
  "warm, conversational" lines in `rag._build_qwen_prompt`. Patient-facing
  "NutriBot" becomes "MyHeartCoach" (`whatsapp.py`, `whatsapp_router.py`,
  `patient_app.html`, `app.py`).
- **V4: EKA.** The brand block replaces the generic role lines
  ("patient educator", "clinical educator", "health behaviour coach") in the
  `generate_weekly_eka.py` generators, plus 2 few-shot exemplars from
  approved items of the same group/level, preferring reviewer-edited finals.
- **V5: fine-tune alignment.** `chain_factory.get_system_template()` uses
  the same block, so training data teaches the live voice.
- **Gate:** zero safety regressions (stance, myth, personalization, scope)
  while the voice score rises.
- **M2 (continued):** finish the module-scope fixes started in Phase 0.
- **K1:** EKA groups for weight, tobacco, medication, PA; the generator sets
  `ContentMaterial.component`, which it never does today.

### Phase 3: Calibrate and harden (Nov 2 – 29)
- **E3:** human labels for the brand-voice and scope judges (and more
  stance labels: 10/17 agreement is the weakest); persist raw GEval scores; threshold sweep (TRIPOD Item 17 method).
- **C1:** clinical review of MODERATE-vs-RESTRICT stance calls (19g #2).
  BM medication-displacement hedging fix (19g #3, cases 102/104/122) using
  the voice spec's myth rules.
- **V6:** weekly voice loop: mine new edit pairs and reviewer notes, refresh
  exemplars, re-score each Monday EKA batch.
- **P1:** WhatsApp pilot, if credentials arrive.
- **K2:** Chatbot_Chunks re-ingest as the client populates it.

### Phase 4: Style LoRA decision, production prep, report (Nov 30 – Dec 31)
- **V7 (conditional):** style LoRA, only if the voice score plateaus under
  prompting. Data: approved and edited EKA pairs plus teacher rewrites,
  50/50 targeted vs generic (the attempt #1 lesson). Same gate.
- **P2:** production readiness if the GPU server exists: Docker cutover
  decision, MPS→CUDA patch.
- **C2:** IRB/ethics review before any real-patient data (19g #13).
- **D:** year-end TRIPOD refresh; roadmap retrospective.

### External-blocker lane (unscheduled until unblocked)

| Item | Waiting on |
|---|---|
| Hospital API spec → RemotePatientStore read + write paths | Hospital IT |
| `care_path` / `objective_ids` write path; OB1-3 mapping confirmation | My Heart Coach team |
| Rehab R1-6 / Dynamic persona tiers; Scoring tab (needs a vitals channel); Personalization_Rules | Client |
| `CardiovascularScreening` → `Patient` FK (19g #7) | NADI team |
| LoRA embedding adapter parity across machines (19g #8) | Mac Studio access |
| IP ownership terms | Contract |
| CI | runners can't reach the private tunnels |

---

## 3. House-voice strategy

**Where tone comes from today:**
- `rag.py` persona: program manager with Coach/Guide/Protector/Gatekeeper
  roles, no name.
- `taxonomy.PERSONALIZATION_LEVEL_PROFILE` Role/Tone cells from the client's
  RulesPolicyTables.
- Generic "warm, conversational" Voice Rules.
- The richest tone text in the repo (`chain_factory.py` "Core Persona &
  Tone") feeds only fine-tune data, so training teaches a voice live chat
  doesn't use.
- No eval metric. Reviewer edits overwrite the draft, so nothing is learnable.

**Target:** one constant **MyHeartCoach** voice, modulated (not replaced) by
the per-level/per-stage Role/Tone table.

**Voice spec contents (V1):**
- Identity: "MyHeartCoach".
- Register: warm but direct; collaborative "we / let's".
- BM: lay dialect ("use lay person dialect", clinician note), not formal
  textbook Malay; Manglish allowed when the patient uses it.
- Myths: refute plainly first, then state the consequence of following the
  myth ("concise and direct to debunk"; "include what happens if user
  doesn't comply").
- Psychosocial: check in on how the patient feels before advising ("too
  soft… not asking how do u feel").
- Banned: generic LLM filler, "As an AI…", hedge-stacking.
- 3 short exemplars, reviewed by the dietitian.

**Why this order (spec → capture → judge → wire → exemplars → LoRA):**
1. The spec gives the judge its rubric.
2. The capture has to start early because edit pairs accumulate one week
   at a time.
3. The judge has to exist before wiring, so the change is measured and not
   assumed.
4. A LoRA runs last, and only if prompting stalls: attempt #1 showed small
   or generic datasets shift tone in the wrong direction (softer on safety).

**Success measure:**
- The brand-voice judge pass rate rises from the Phase 1 baseline, at
  judge/human agreement ≥ 80% on the calibration set.
- Zero regressions on the stance, myth, personalization and scope suites
  (`compare_eval_runs.py` PROMOTE).
