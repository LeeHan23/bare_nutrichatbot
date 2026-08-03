"""
LocalPatientStore — current dev/staging implementation.

Wraps the local Postgres `patients` table via SQLAlchemy. Used until the
hospital system provides a real API. To swap, just write a RemotePatientStore
that implements the same PatientStore interface.

Privacy note: this implementation persists patient data to the local machine.
It is acceptable ONLY for dev/staging with synthetic patients. Production
deployment must replace this with a remote store.
"""
from datetime import datetime, timezone
from typing import Any

import database as db
from patient_store import PatientStore, SUPPLEMENTARY_FIELDS


class LocalPatientStore(PatientStore):
    """Reads from and writes to the local SQLAlchemy `patients` table."""

    def get_profile(self, patient_id: int) -> dict | None:
        session = db.SessionLocal()
        try:
            patient = db.get_patient(session, patient_id)
            if patient is None:
                return None
            return self._patient_to_full_profile(patient)
        finally:
            session.close()

    def update_supplementary_fields(
        self,
        patient_id: int,
        updates: dict,
        source_session_id: str | None = None,
    ) -> dict:
        # Filter — only allow whitelisted supplementary fields
        allowed_updates = {
            k: v for k, v in updates.items() if k in SUPPLEMENTARY_FIELDS
        }
        rejected = set(updates.keys()) - set(allowed_updates.keys())
        if rejected:
            print(f"[PatientStore] Rejected non-supplementary fields: {rejected}")

        if not allowed_updates:
            return {}

        session = db.SessionLocal()
        try:
            patient = db.get_patient(session, patient_id)
            if patient is None:
                print(f"[PatientStore] Patient {patient_id} not found")
                return {}

            # Apply updates and track provenance
            applied = {}
            metadata = dict(patient.extractor_metadata or {})
            now_iso = datetime.now(timezone.utc).isoformat()

            for field, value in allowed_updates.items():
                setattr(patient, field, value)
                metadata[field] = {
                    "last_updated": now_iso,
                    "source_session_id": source_session_id,
                }
                applied[field] = value

            patient.extractor_metadata = metadata
            session.commit()
            return applied
        finally:
            session.close()

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _patient_to_full_profile(self, patient) -> dict:
        """
        Build the merged profile dict (clinical + supplementary).
        Backwards-compatible with the existing rag.get_rag_response() schema —
        clinical keys remain unchanged so existing prompt logic works.
        """
        # Existing clinical fields (matches db.patient_to_profile_dict shape)
        profile: dict[str, Any] = {
            "condition":             patient.conditions           or [],
            "medications":           patient.medications          or [],
            "dietary_restrictions":  patient.dietary_restrictions or [],
            "name":                  patient.name,
            "age":                   patient.age,
            "gender":                patient.gender,
            "ethnicity":             patient.ethnicity,
            "weight_kg":             patient.weight_kg,
            "height_cm":             patient.height_cm,
            "allergies":             patient.allergies            or [],
            "notes":                 patient.notes                or "",
            "personalization_level": patient.personalization_level,
            # External state-machine fields (see docs/state_machine_contract.md)
            "care_path":             patient.care_path,
            "objective_ids":         patient.objective_ids        or [],
            "difficulty_ceiling":    patient.difficulty_ceiling,
            "clinical_risk_tier":    patient.clinical_risk_tier,
        }

        # Supplementary fields — only included if they have values
        for field in SUPPLEMENTARY_FIELDS:
            value = getattr(patient, field, None)
            # Skip empty defaults to keep prompt clean
            if value is None or value == [] or value == {}:
                continue
            profile[field] = value

        # Provenance metadata (handy for debugging, the bot prompt won't include it)
        if patient.extractor_metadata:
            profile["_extractor_metadata"] = patient.extractor_metadata

        return profile
