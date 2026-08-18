# State Machine → Nutribot Consumption Contract

Written 2026-07-30, updated 2026-08-03. **Placeholder, not a finalized spec** — the care-path/rehab state machine and the clinical risk-scoring module are being built by separate teams. This doc defines the minimal fields Nutribot's dietetics LLM needs to consume from them for personalization, so those teams have something concrete to build against. Update this doc (and the adaptation points listed below) once the real interfaces are chosen — same pattern as `remote_patient_store.py`'s placeholder hospital-API contract.

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

1. **No write path for `care_path` / `objective_ids` / `difficulty_ceiling`.** No transport (API endpoint, message queue, shared DB) from the external care-path/rehab state machine into this repo's `Patient` table exists anywhere in this codebase. These three fields will read as `None`/empty until that integration is built by whoever owns that state machine.
2. **`personalization_level` relationship**: currently coexists unchanged. `clinical_risk_tier` (whether hand-set or MHR-screening-derived) is a fallback signal only where `personalization_level` is null — not a replacement, until told otherwise.
3. **`onboarding_stage` (OB1–OB3)** — updated 2026-08-12, see `docs/component_taxonomy_contract.md`. Still owned by an external solution (never written by this repo), but now consumed read-only: `Patient.onboarding_stage` + `rag._build_onboarding_block()`. This repo does not gate or progress the stage, only renders what it means once told.
