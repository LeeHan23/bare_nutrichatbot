"""Self-check for the patient-selected care_path write path (app.py:
/patient/{id}/care_path, /patient/care-path-options). Hits the real local
DB via FastAPI's TestClient — no mocks. Run: python scripts/test_care_path_endpoint.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from fastapi.testclient import TestClient

import app as app_module
import database as db

load_dotenv()
API_KEY = os.environ["NUTRIBOT_API_KEY"]
HEADERS = {"X-API-Key": API_KEY}

client = TestClient(app_module.app)

# Options endpoint returns all 4 values
r = client.get("/patient/care-path-options", headers=HEADERS)
assert r.status_code == 200, r.text
values = {o["value"] for o in r.json()["options"]}
assert values == {"keep_well", "reduce_risk", "live_better", "recover"}, values

# Set + persist for a real patient (id=1), then revert to whatever it was before
s = db.SessionLocal()
patient = db.get_patient(s, 1)
original = patient.care_path
s.close()

try:
    r = client.post("/patient/1/care_path", headers=HEADERS, json={"care_path": "recover"})
    assert r.status_code == 200, r.text
    assert r.json()["care_path"] == "recover"

    s = db.SessionLocal()
    assert db.get_patient(s, 1).care_path == "recover"
    s.close()

    # invalid value rejected
    r = client.post("/patient/1/care_path", headers=HEADERS, json={"care_path": "nonsense"})
    assert r.status_code == 400, r.text

    # unknown patient -> 404
    r = client.post("/patient/999999/care_path", headers=HEADERS, json={"care_path": "keep_well"})
    assert r.status_code == 404, r.text

    # login response now surfaces care_path
    r = client.post("/patient/login", headers=HEADERS, json={"name": "Ahmad Fadzillah bin Roslan"})
    assert r.status_code == 200, r.text
    assert r.json().get("care_path") == "recover", r.json()
finally:
    s = db.SessionLocal()
    db.set_patient_care_path(s, 1, original)
    s.close()

print("ALL CHECKS PASSED")
