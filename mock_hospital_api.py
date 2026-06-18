"""
mock_hospital_api.py — Standalone mock of the hospital's patient API.

Implements the placeholder contract assumed by remote_patient_store.py so
RemotePatientStore can be exercised end-to-end before the real hospital API
exists. NOT for production use — in-memory data only, no auth by default.

Usage:
    /home/han/miniconda3/bin/python -m uvicorn mock_hospital_api:app --port 8500

Optional bearer-token check:
    MOCK_HOSPITAL_API_KEY=secret123 /home/han/miniconda3/bin/python -m uvicorn mock_hospital_api:app --port 8500
"""
import os
from copy import deepcopy

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock Hospital Patient API")

_API_KEY = os.getenv("MOCK_HOSPITAL_API_KEY")

# In-memory patient store, seeded with the same flat shape LocalPatientStore returns.
_PATIENTS: dict[int, dict] = {
    1: {
        "id": 1,
        "name": "Ahmad Fadzillah bin Roslan",
        "age": 58,
        "gender": "Male",
        "ethnicity": "Malay",
        "weight_kg": 78.0,
        "height_cm": 170.0,
        "condition": ["Type 2 Diabetes", "Hypertension"],
        "medications": ["Metformin 500mg BD", "Lisinopril 10mg OD"],
        "dietary_restrictions": ["Halal only", "Low sodium"],
        "allergies": [],
        "notes": "",
        "personalization_level": "L2",
    },
}


class SupplementaryUpdate(BaseModel):
    updates: dict
    source_session_id: str | None = None


def _check_auth(authorization: str | None):
    if _API_KEY and authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/patients/{patient_id}")
def get_patient(patient_id: int, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    patient = _PATIENTS.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return deepcopy(patient)


@app.patch("/patients/{patient_id}/supplementary")
def update_supplementary(patient_id: int, body: SupplementaryUpdate, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    patient = _PATIENTS.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    applied = {}
    for field, value in body.updates.items():
        patient[field] = value
        applied[field] = value

    return {"applied": applied}
