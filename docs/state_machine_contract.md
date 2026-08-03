# State Machine → Nutribot Consumption Contract

Written 2026-07-30. **Placeholder, not a finalized spec** — the care-path/rehab state machine and the clinical risk-scoring module are being built by a separate team. This doc defines the minimal fields Nutribot's dietetics LLM needs to consume from them for personalization, so that team has something concrete to build against. Update this doc (and the adaptation points listed below) once the real interface is chosen — same pattern as `remote_patient_store.py`'s placeholder hospital-API contract.

## Why this exists

Nutribot is the dietetics chatbot module only. The 6-8 week care-path/objective/programme state machine described in the "My Heart Coach" architecture doc, and the clinical risk scoring (Framingham/REDISCOVER-style), are owned elsewhere. Nutribot's job is to read whatever state those systems produce and use it to personalize dietary advice — same role `personalization_level` (L0-L3) already plays, just sourced externally instead of hand-set by a dietitian.

## Fields Nutribot consumes

| Field | Type | Values | Source |
|---|---|---|---|
| `care_path` | string | `keep_well` \| `reduce_risk` \| `live_better` \| `recover` | state machine |
| `objective_ids` | list[string] | 1 primary + up to 2 secondary; opaque IDs from the state machine's own objective catalogue — Nutribot does not need to know what each ID means, just that they exist | state machine |
| `difficulty_ceiling` | string | `easy` \| `intermediate` \| `hard` | state machine |
| `clinical_risk_tier` | string | `LOW` \| `MODERATE` \| `HIGH` \| `VERY_HIGH` (matches `risk_calculator.py`'s existing `calculated_risk_category` casing — reuse, don't reinvent) | risk-scoring module |
| `escalation_flag` | bool (not yet stored — add when the escalation-routing phase lands) | — | state machine / risk-scoring module |

These are **read-only from Nutribot's side** — never extractor-writable, same protection tier as hospital-owned clinical fields (`conditions`, `medications`, etc.), not the `SUPPLEMENTARY_FIELDS` whitelist in `patient_store.py`.

## Where they land today

- `database.py` — `Patient.care_path`, `.objective_ids`, `.difficulty_ceiling`, `.clinical_risk_tier` columns (all nullable, additive migration: `scripts/migrate_state_machine_fields.py`).
- `database.patient_to_profile_dict()` and `local_patient_store.py`'s `_patient_to_full_profile()` both surface them into the profile dict `rag.py` consumes.

## Still undecided (adaptation points once known)

1. **Transport**: not yet decided whether the state machine/risk module write directly to this Postgres instance, call an internal PATCH endpoint Nutribot exposes, or push via webhook. No write path exists yet — build it once this is known, don't guess.
2. **`personalization_level` relationship**: currently coexists unchanged. `clinical_risk_tier` is a fallback signal only where `personalization_level` is null — not a replacement, until told otherwise.
3. **RAG prompt injection**: not yet wired into `rag.py` — next phase once the fields above are actually populated by something.
