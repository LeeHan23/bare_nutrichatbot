# State Machine → Nutribot Consumption Contract

Written 2026-07-30, updated 2026-08-03, updated 2026-08-18 with the real staging schema, **updated 2026-09-16 with a live re-check + the onboarding_stage fallback**. Sections below marked "placeholder" are still speculative; the "Real staging DB" section is not — it's from directly exploring the actual My Heart Coach staging database.

**Placeholder, not a finalized spec** — the care-path/rehab state machine and the clinical risk-scoring module are being built by separate teams. This doc defines the minimal fields Nutribot's dietetics LLM needs to consume from them for personalization, so those teams have something concrete to build against. Update this doc (and the adaptation points listed below) once the real interfaces are chosen — same pattern as `remote_patient_store.py`'s placeholder hospital-API contract.

## Real staging DB (found 2026-08-18) — supersedes the placeholder guesses below where they conflict

Received direct read credentials to the My Heart Coach companion app's staging MySQL DB (`.env`: `MYHEART_DB_*`). Explored live 2026-08-18: MySQL 8.4.11, 21 tables (Sequelize-managed — `sequelize_meta` present), all tables empty — a genuinely fresh pre-launch staging environment, not a broken/stale one.

**Re-checked live 2026-09-16: the schema has grown to 27 tables and is no longer empty** (`users`: 12 rows, `goals`: 7, `risk_score`: 4, `medicine`: 5, `medicine_history`: 7, `eka_sets`: 49, `exercises`: 147, `knowledge_articles`: 147). New `users` columns since the 2026-08-18 pass: `is_goals_completed`, `is_medicine_completed`, `is_medicine_history_completed`, `is_risk_score_completed`, `preferred_language`, `avatar`, `country_code`, `reward_points`, `last_active_at`, `active`.

This is a **separate identity space** from our own `Patient` table — the join key is `users.phone_no` (matches our `Patient.phone_number`) or `users.ic_no` (matches `Patient.ic_number`), not `patient_id`.

What matches our placeholder contract cleanly:
- **`users.risk_level`** — `enum('L0','L1','L2','L3')`. This is the **exact same vocabulary** as our own `Patient.personalization_level`, not `clinical_risk_tier` (which uses LOW/MODERATE/HIGH/VERY_HIGH). **Wired in 2026-08-18**: `myheart_db.py` (read-only, `pymysql`) queries this by phone number. **2026-09-16**: the fallback logic was deduplicated out of `database.patient_to_profile_dict()` / `local_patient_store._patient_to_full_profile()` (which had each reimplemented it) into one shared `database.get_effective_personalization_level(patient)`, and a real gap was found and fixed: `content_api_router.py`'s `GET /content/patient-feed/{patient_id}` (the EKA content endpoint) was reading `patient.personalization_level` directly, bypassing this fallback entirely — a patient with no dietitian-set level but a matching staging-DB phone number got generic/untiered EKA content instead of their real L0-L3 tier. Now routed through the same shared helper. Live-verified against the real staging DB: phone `+60170000001` → `L2`. Fails soft (unreachable DB, unset env, or no match all just return `None`) — never blocks a chat reply or EKA feed request, never writes.

- **`users.is_goals_completed` / `is_risk_score_completed` / `is_medicine_completed` / `is_medicine_history_completed`** — booleans, new since 2026-08-18. There is still no dedicated onboarding-stage field, but these four line up closely with `taxonomy.ONBOARDING_STAGE_LABELS`' own OB1 ("goals/preferences known"), OB2 ("known medical conditions on file"), OB3 ("medications and allergies on file") definitions. **Wired in 2026-09-16** as `myheart_db.get_myheart_onboarding_stage()` / `database.get_effective_onboarding_stage(patient)`, mapping `is_goals_completed` → OB1, `is_risk_score_completed` → OB2, `is_medicine_completed AND is_medicine_history_completed` → OB3 (highest completed step wins), used as a fallback wherever `Patient.onboarding_stage` is unset — same tier and call sites as the `risk_level` fallback above (chat prompt via `patient_to_profile_dict()`/`_patient_to_full_profile()`, and the EKA content feed). **This mapping is a provisional best guess, not confirmed by the My Heart Coach team** — wired in anyway per an explicit 2026-09-16 decision (weighed against this doc's standing caution below about not guessing at this schema, same caution that's kept the `goals`→`care_path` mapping unwired). Revisit if the My Heart Coach team clarifies intent differently. Live-verified against real rows: an all-flags-false user → `None`, goals-only → `OB1`, all-flags-true → `OB3`.

What does **not** match — the placeholder guessed wrong:
- **No `care_path`, `objective_ids`, or `difficulty_ceiling` fields exist anywhere in the real schema.** The closest analog is a `goals` table (`primary_goal`, `health_challenge`, `daily_active_level`, `exercise_type`, `physical_injury`, `average_sleep_hours`, `daily_exercise_minute`, `height`/`current_weight`/`target_weight` — all free-text-ish `varchar`, one row per `user_id`), which is a different shape entirely from the 4-way `keep_well/reduce_risk/live_better/recover` enum this repo already built `rag._build_care_path_block()` against. **Not wired in** — mapping `goals` onto `care_path`/`objective_ids` would be guessing at intent with zero sample data to check against. Needs the My Heart Coach team to confirm before building anything here.
- **`risk_score` table** has real intake fields (cholesterol, blood pressure, diabetes status/meds, ECG, prior heart attack/procedure) that overlap with our own `cardiovascular_screenings`/MHR intake (`risk_calculator.py`), but different field names, no computed category, and a different `user_id` FK space — not the same table our `POST /api/v1/mhr/screen` endpoint writes to. Not wired in.

Other tables of note, not yet consumed anywhere: `eka_sets`/`exercises`/`knowledge_articles` (a real risk-level-gated Exercise/Knowledge/Activity content schema — directly relevant to our weekly EKA pipeline, worth a closer look before more EKA content-generation work), `user_vital_signs` (pulse, BP, blood sugar, SpO2, HbA1c, cholesterol — an actual vitals channel; `docs/component_taxonomy_contract.md` had flagged this as not existing anywhere), `medicine`/`medicine_history` (JSON medicine list per user).

## How to connect

Credentials live in `.env` as `MYHEART_DB_HOST`/`_PORT`/`_NAME`/`_USER`/`_PASSWORD` — never hardcode them elsewhere.

**mysql CLI** (ad-hoc inspection):
```bash
mysql -u"$MYHEART_DB_USER" -p"$MYHEART_DB_PASSWORD" -h"$MYHEART_DB_HOST" -P"$MYHEART_DB_PORT" "$MYHEART_DB_NAME"
```

**From Python** — reuse `myheart_db._get_connection()` rather than opening a new `pymysql.connect(...)` elsewhere in the repo:
```python
from myheart_db import _get_connection
conn = _get_connection()  # None if MYHEART_DB_HOST unset — check before using
```

**Convention: read-only.** `myheart_db.py` is documented and built as never-write — every existing call site (`database.patient_to_profile_dict()`, `local_patient_store._patient_to_full_profile()`) only does `SELECT ... risk_level`. Keep new code on that side of the line; this is another team's database, and Nutribot is a guest in it. A one-off write (e.g. seeding a test row) is a deliberate, manual exception — done directly via `pymysql`, not by adding a write method to `myheart_db.py`.

**Linking a local `Patient` to a `users` row**: the join key is `phone_no` (or `ic_no`), not an ID. For the read-time `risk_level` fallback (see above) to actually resolve for a given patient, that patient's `Patient.phone_number` must equal the target row's `phone_no` exactly (E.164-ish, e.g. `+60170000001`) — set it via the `set_patient_phone` MCP tool. Without a matching phone number, `get_myheart_risk_level()` just returns `None` (fails soft, no error).

## Why this exists

Nutribot is the dietetics chatbot module only. The 6-8 week care-path/objective/programme state machine described in the "My Heart Coach" architecture doc, and the clinical risk scoring (Framingham/REDISCOVER-style), are owned elsewhere. Nutribot's job is to read whatever state those systems produce and use it to personalize dietary advice — same role `personalization_level` (L0-L3) already plays, just sourced externally instead of hand-set by a dietitian.

## Fields Nutribot consumes

Four `Patient` columns (`database.py`, `Patient` class) are owned by systems **outside this repo**. Nutribot only reads them; nothing in this codebase is the source of truth for their values.

| Field | Type | Values | Owner |
|---|---|---|---|
| `care_path` | `String` | `keep_well` \| `reduce_risk` \| `live_better` \| `recover` | Care-path/rehab state machine (external) |
| `objective_ids` | `JSON` (list) | 1 primary + up to 2 secondary; opaque IDs from the state machine's own objective catalogue — Nutribot does not need to know what each ID means, just that they exist | Care-path/rehab state machine (external) |
| `difficulty_ceiling` | `String` | `easy` \| `intermediate` \| `hard` — approved *activity* difficulty; governs exercise, not diet | Care-path/rehab state machine (external) |
| `clinical_risk_tier` | `String` | `LOW` \| `MODERATE` \| `HIGH` \| `VERY_HIGH` (matches `risk_calculator.py`'s `calculated_risk_category` casing — reuse, don't reinvent) | Risk-scoring module (external) — now has a real intake path, see below |
| `escalation_flag` | bool (not yet stored — add when the escalation-routing phase lands) | — | State machine / risk-scoring module |

These are **read-only from Nutribot's side** — never extractor-writable, same protection tier as hospital-owned clinical fields (`conditions`, `medications`, etc.), not the `SUPPLEMENTARY_FIELDS` whitelist in `patient_store.py`.

## Where they land today

- `database.py` — `Patient.care_path`, `.objective_ids`, `.difficulty_ceiling`, `.clinical_risk_tier` columns (all nullable, additive migration: `scripts/migrate_state_machine_fields.py`).
- `database.patient_to_profile_dict()` and `local_patient_store.py`'s `_patient_to_full_profile()` both surface them into the profile dict `rag.py` consumes.
- All four are consumed by `rag._build_care_path_block()` and injected into the Qwen prompt under a "Care Path & Objectives" heading (also used by `agent.py`'s agent-tools path).

## `clinical_risk_tier` — intake path (fixed 2026-08-03)

`POST /api/v1/mhr/screen` (`myheartrisk_router.py`) is the real intake path for this field. It receives a pre-calculated risk screening from the NADI Centre protocol (scoring logic lives in `risk_calculator.py`, out of scope for this repo to modify) and stores it in the `cardiovascular_screenings` table (`CardiovascularScreening` model, `database.py`).

This did not work before the 2026-08-03 fix: the CRUD functions (`create_mhr_screening`/`get_latest_mhr_screening`) were `async def` using `AsyncSession`, while the rest of this codebase — including the `Session` the router's `Depends(get_db)` actually hands it — is sync. The endpoint crashed on every real call. It's now sync, matching the rest of `database.py`.

The flow, as of the fix:

1. `POST /api/v1/mhr/screen` writes a row to `cardiovascular_screenings`, keyed by `patient_id` (stored as a string — there is no FK to `Patient.id`, and no mapping table exists; the assumed convention is `str(Patient.id)`).
2. `database.patient_to_profile_dict()` and `local_patient_store._patient_to_full_profile()` read `patient.clinical_risk_tier` first. **Only if that's unset** do they call `get_latest_mhr_screening()` and fall back to the screening's `calculated_risk_category`.
3. A hand-set `clinical_risk_tier` (written directly to `Patient` by the state machine, if that integration ever exists) always wins over the screening fallback.

This is a read-time fallback, not a write to `Patient.clinical_risk_tier` — the screening table and the `Patient` column stay independent; nothing copies data between them at write time.

## Still open

1. **No write path for `care_path` / `objective_ids` / `difficulty_ceiling` — and, per the 2026-08-18 schema exploration above, it's now unclear these will ever map 1:1 onto anything in the real My Heart Coach DB.** The interim patient-self-service picker (`app.py`, added 2026-08-12) remains the only way these fields get set today. Whether `goals` (the real schema's closest analog) should eventually drive these, and how, needs the My Heart Coach team's input, not a guess from this side.
2. **`personalization_level` relationship**: `clinical_risk_tier` (hand-set or MHR-screening-derived) remains a fallback signal only where `personalization_level` is null. **As of 2026-08-18**, `personalization_level` itself now has its own further fallback — the My Heart Coach staging DB's `users.risk_level` (same L0-L3 enum) — checked only when `personalization_level` is unset (see "Real staging DB" above). Priority order, most to least authoritative: dietitian-set `personalization_level` → My Heart Coach `users.risk_level` → (separately) `clinical_risk_tier`, hand-set or MHR-screening-derived.
3. **`onboarding_stage` (OB1–OB3)** — updated 2026-08-12, see `docs/component_taxonomy_contract.md`. Still owned by an external solution (never written by this repo): `Patient.onboarding_stage` + `rag._build_onboarding_block()`. **2026-09-16**: now has the same kind of staging-DB read-time fallback as `personalization_level` (see "Real staging DB" above) when unset — `database.get_effective_onboarding_stage()`. This repo still does not gate or progress the stage on its own, only renders what it means once told (hand-set or staging-DB-derived).

**2026-08-28**: `MyHeartCoach_RulesPolicyTables_v2.xlsx`'s `Prompt` tab supplied the client's canonical Role/Tone/Exercise/Knowledge/Activity policy for each OB1-3 stage and L0-L3 level (covering all 10 MyHeartCoach components, not just nutrition). Folded in additively — nothing existing was removed: `taxonomy.ONBOARDING_STAGE_LABELS`'s OB1-3 entries and `taxonomy.PERSONALIZATION_LEVEL_PROFILE` (new, L0-L3) carry this detail; `rag._build_qwen_prompt()`, the CLaRa-primary path, `agent.py`'s agent-tools path, and `eval/live_pipeline_smoke_test.py`'s standalone copy all render it alongside the pre-existing dietary-specific L0-L3 instructions. `scripts/generate_weekly_eka.py`'s `_PERSONALIZATION_GUIDANCE` got the same L0-L3 detail — while fixing it, found that constant had never actually been wired into any of its three generation prompts (dead code); it's now injected alongside `_SAFETY_GUARDRAILS`.
