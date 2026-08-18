# MyHeartCoach Component Taxonomy — Consumption Contract

Written 2026-08-12. Foundation pass for expanding Nutribot from a single
dietetics chatbot into a bot that can (eventually) cover all 10 content
Components the client's taxonomy defines. Only **Nutrition** has real
grounded content today. Source: `MyHeartCoach_Content_Registry.xlsx` (Taxonomy,
Content_Registry, Chatbot_Chunks tabs) and `Exercise Video Intensity.xlsx`,
both supplied by the client and kept at the repo root.

Same repo, same bot (explicit decision, not 10 separate services) — see
`taxonomy.py` for the machine-readable vocabulary everything below builds on.

## Why this exists

Mirrors `docs/state_machine_contract.md`'s framing: define what's decided
and what's deliberately still open, so a later session (or another
developer) doesn't have to re-derive it from the workbook or guess.

## What's built

- `taxonomy.py` — `COMPONENTS` (10 slugs), `COMPONENT_LABELS`,
  `COMPONENT_SCOPE`, `ONBOARDING_STAGE_LABELS`.
- `vector_store.py` — `doc_components` chunk metadata, `detect_query_component()`,
  a hard retrieval gate in `TopicBoostedRetriever` (chunks tagged for a
  different component are excluded; untagged/legacy chunks are always kept),
  and a `trust_tier == "clinical_approved"` ranking boost.
- `rag.py` / `agent.py` — component detection feeds both the retrieval gate
  and a prompt-injected `## Component Scope` block. **Updated 2026-08-14**:
  all 10 components now have a real `in_scope`/`out_of_scope` block, not a
  blanket refusal. `nutrition`/`exercise` stay grounded in retrieved content;
  the other 8 (`foundations`, `blood_pressure`, `lipid`, `diabetes`,
  `tobacco_nicotine_alcohol`, `physical_activity`, `psychosocial`,
  `medication`) are scoped to general, non-personalized lay education from
  the model's own knowledge only — explain concepts, never interpret the
  patient's own numbers/results, never give dosing/timing/programming
  advice, always defer anything personalized or clinical to the care team.
  `medication` stays the tightest of the 8 (no dosing/switching/interactions,
  no exceptions) since it's the highest-risk topic to get wrong ungrounded.
  The old blanket "no grounded content yet, defer" guard
  (`taxonomy._NO_CONTENT_GUARD`) is now only a fallback for a component slug
  added to `COMPONENTS` before its scope text is written — see
  `taxonomy.py`'s `__main__` self-check, which asserts none of the 10 real
  components fall through to it.
- `scripts/enrich_with_components.py` — backfilled all 24,819 existing
  `base_knowledge` chunks with `doc_components: ["nutrition"]` (they're
  100% nutrition-sourced today). `build_base_db.py` stamps new ingests the
  same way going forward (`DOC_COMPONENT_OVERRIDES` dict for anything else).
- `scripts/ingest_chatbot_chunks.py` — loads `Status == "Approved"` rows from
  the workbook's `Chatbot_Chunks` tab into `base_knowledge`, tagged
  `trust_tier: "clinical_approved"`. Idempotent by `Chunk ID` — safe to
  re-run every time the client resends the workbook. Ingested live
  2026-08-12: 1 row (`CB-001`, Exercise).
- `exercise_lookup.py` + `scripts/build_exercise_video_lookup.py` —
  deterministic, code-only exercise-video citation (199 videos flattened
  from the Exercise Video Intensity workbook into
  `data/exercise_video_lookup.json`). The YouTube URL is attached to the
  response dict (`rag.get_rag_response()`'s `exercise_video` key) entirely
  outside the LLM's generation — the model never sees or reproduces it.
  Because of this, `exercise` got a real (non-guard) `COMPONENT_SCOPE`
  entry in `taxonomy.py`, not the generic "no content yet" block — see
  "exercise is a partial exception" below.
- `Patient.onboarding_stage` + `ContentMaterial.component` columns
  (`scripts/migrate_component_columns.py`, both nullable, no backfill).
  `onboarding_stage` is read-only, same treatment as `care_path` — an
  external solution owns progressing a patient through OB1-3; Nutribot only
  renders what the stage means via `ONBOARDING_STAGE_LABELS` once told.
- `scripts/generate_weekly_eka.py` / `scripts/weekly_eka_scheduler.py`
  (the pre-taxonomy weekly Exercise/Knowledge/Activity generator) were
  **retired 2026-08-12**: deleted, their crontab entry removed, and the
  `POST /content/generate-weekly` admin endpoint in `content_api_router.py`
  removed. `ContentMaterial.content_type`/`week_number` columns and the
  DB-layer helpers (`upsert_eka_material`/`cleanup_expired_eka_materials`/
  `get_materials_by_filters`/`get_weekly_feed_for_conditions`) were **kept**
  — they map directly onto the taxonomy's E/K/A Content Classification axis
  and were expected to be reused, not reinvented.

  **Restored 2026-08-14**, rebuilt on the taxonomy's safety boundaries
  rather than free-form generation. What changed, driven by the material
  id=68 dietitian flag (a Knowledge item recommended lentils/beans — high
  potassium — as a low-protein swap to CKD patients, see
  `materials/eka_dietitian_review_flags.md`):
  - `_SAFETY_GUARDRAILS` (new, in `generate_weekly_eka.py`): injected into
    every Knowledge and Activity prompt — no direct food/medication swap
    instructions, no invented clinical thresholds, always defer specific
    changes to the patient's own dietitian/doctor. Same spirit as
    `taxonomy.COMPONENT_SCOPE`'s out-of-scope boundaries, applied to this
    separate (non-chat) generation pipeline.
  - `_generate_exercise()` no longer invents a session plan (warmup/main
    activity/cooldown/duration/sets) from scratch. It's now grounded in the
    real approved exercise-video catalog (`exercise_lookup.list_exercise_samples_for_level()`
    — the same source of truth the live chat `exercise` Component uses,
    see "Exercise (and nutrition) are grounded" below) via a
    `_GROUP_LEVEL` mapping (condition group → personalization level, e.g.
    CKD/Cardiac → L2). The LLM only writes short framing/why-it-helps copy
    about real catalog entries it must reference verbatim — never new
    exercises, durations, or intensities.
  - Everything else is unchanged: `is_active=False` on every generated row
    (nothing reaches a patient without `POST /content/materials/{id}/approve`),
    the 4-week topic rotation per condition group, the Excel export to
    `materials/`, and the Monday 06:00 cron
    (`0 6 * * 1 .../weekly_eka_scheduler.py`).
  - New: a live, filterable review UI at
    `https://docs-api.computationalrd.com/eka-review` (X-API-Key gated,
    `docs_api.py`) reads `content_materials` directly — replaces manually
    opening the weekly Excel exports to review a batch. Read-only; approval
    still goes through the existing admin endpoint.

## Exercise (and nutrition) are grounded; the other 8 are general-education

`nutrition` and `exercise` are the only two components backed by real
retrieved content — `nutrition` from `base_knowledge` chunks, `exercise` from
the video library (199 real, client-approved YouTube videos filtered by
personalization level). `taxonomy.COMPONENT_SCOPE["exercise"]` reflects that
narrowly — the model may confirm a video is being shown, never describe/
invent one itself, and still may not prescribe a programme or judge medical
safety beyond what the library covers.

The other 8 components have zero ingested clinical documents, so their
`COMPONENT_SCOPE` entries (added 2026-08-14) intentionally stay at the
"general lay education, always defer specifics to the care team" altitude
rather than letting the model answer as if it had grounded clinical content.

## Component detection is deliberately conservative

`vector_store.COMPONENT_HINTS` only maps phrases with essentially no
plausible dietary framing (medication dosing, smoking cessation, mental
health, structured-workout requests, "what is a heart attack"-style
definition questions). Condition words already in `TOPIC_HINTS`
(hypertension, diabetes, cholesterol, CKD, heart failure) are **not** mapped
to a component — today's live traffic asks about those conditions almost
entirely in a dietary context, and gating them would hard-filter working
Nutrition retrieval to zero chunks. Verified live 2026-08-12: a CKD +
hypertension breakfast question still returns `component=None` and behaves
identically to before this change; a medication-stopping question correctly
routes to `component=medication`, retrieves 0 chunks, and (even after the
2026-08-14 general-education update, since "stop my medication" is
explicitly `out_of_scope`) the model defers to the doctor instead of
answering.

This is a `# ponytail:`-marked heuristic ceiling in `vector_store.py` —
upgrade path is an LLM intent-classification pass if misses on a populated
component prove costly in eval.

## Still open — do not guess at these

1. **Rehab R1-6 / Dynamic persona tiers.** Not consumed anywhere. The
   Taxonomy tab defines them (structured recovery stages; real-time
   tone-adaptation layer) but the user only asked for OB1-3 understanding
   in this pass. No `Patient` columns added. Revisit only if asked.
2. **The `Scoring` tab** (Borg RPE / HR response / BP response → a real-time
   "System Logic Action" exercise-safety rubric, in `Exercise Video
   Intensity.xlsx`). This needs live vitals telemetry mid-conversation —
   Nutribot has no such input channel today. Explicitly out of scope; would
   need a wearables/device integration owned elsewhere.
3. **`Personalization_Rules` tab** (App/WhatsApp/Bot content-delivery rules
   mapping profile triggers → Content IDs → channel). Conceptually
   overlaps with `content_scheduler.py`'s existing due-date/condition
   matching, but no `Content_Registry` rows exist yet with real
   (non-template) Content IDs for it to resolve against. Not designed.
4. **Content_Registry label drift.** Sample rows use labels not in the
   Taxonomy tab's canonical 10 (`"Sleep & Recovery"`, `"Foundations"` vs
   `"Foundations - Heart Diseases"`, `"Monitoring & Check-ins"`,
   `"Physical Activity & Exercise"`). `scripts/ingest_chatbot_chunks.py`
   logs a warning and leaves the resulting chunk untagged (safe default:
   always eligible, never wrongly excluded) rather than fuzzy-guessing the
   mapping. Confirmed template noise as of this workbook version; revisit
   if it persists once the client's content team populates real rows.
5. **Chatbot_Chunks ingestion cadence.** Stays a manual, developer-run
   script (`python scripts/ingest_chatbot_chunks.py <workbook path>`) each
   time the client resends the workbook — no automation, no webhook. The
   workbook only had 1 Approved row as of 2026-08-12; revisit once real
   delivery cadence (email vs. shared drive vs. an eventual API) is clear.
6. **`image_url` / `exercise_video` frontend rendering.** Neither is
   actually consumed by any frontend today (`app.py`, `website_chat_router.py`,
   `whatsapp_router.py`, `patient_app.html` — confirmed via grep). The API
   response carries the field correctly; wiring a UI to render it is
   separate, unstarted work.
