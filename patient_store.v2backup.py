"""
PatientStore — abstraction layer for patient data access.

The bot depends on this interface, never on a concrete storage implementation.
This means swapping from local DB (dev) to a hospital API (prod) is a one-line
config change in app.py.
"""
from abc import ABC, abstractmethod
from typing import Protocol


class PatientStore(ABC):
    """Interface every patient data backend must implement."""

    @abstractmethod
    def get_profile(self, patient_id: int) -> dict | None:
        """
        Return the merged patient profile (clinical + supplementary fields)
        as a dict that rag.get_rag_response() can consume. Returns None if
        the patient is not found.
        """
        ...

    @abstractmethod
    def update_supplementary_fields(
        self,
        patient_id: int,
        updates: dict,
        source_session_id: str | None = None,
    ) -> dict:
        """
        Update only the supplementary (extractor-filled) fields for a patient.
        Never touches clinical fields (conditions, medications, etc.) — those
        are owned by the hospital system.

        `updates` keys must match the supplementary field names defined in
        the Patient model (e.g. 'fluid_intake_ml', 'religion').

        Returns a dict of {field: applied_value} for fields that were actually
        written (rejected/invalid fields are not in this dict).
        """
        ...


# List of fields the extractor is allowed to update.
# Anything not in this list is rejected — protects clinical data integrity.
SUPPLEMENTARY_FIELDS = {
    # Tier 1
    "fluid_intake_ml",
    "alcohol_per_week",
    "supplements",
    "religion",
    "tobacco_status",
    # Tier 2
    "meals_per_day",
    "snacks_per_day",
    "processed_food_freq",
    "fast_food_freq",
    "self_prepared_freq",
    "caffeine_mg_per_day",
    "sugar_drinks_ml",
    "activity_freq",
    "activity_minutes",
    "activity_intensity",
    "food_avoidance",
    "nutrition_knowledge",
    "readiness_to_change",
    "sodium_awareness",
}
