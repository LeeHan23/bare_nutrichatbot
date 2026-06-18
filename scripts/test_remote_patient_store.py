"""
test_remote_patient_store.py — End-to-end smoke test for RemotePatientStore
against mock_hospital_api.py.

Starts the mock hospital API as a subprocess on a local port, points
RemotePatientStore at it, and exercises get_profile() / update_supplementary_fields().

Usage:
    /home/han/miniconda3/bin/python scripts/test_remote_patient_store.py
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from remote_patient_store import RemotePatientStore

PORT = 8500
BASE_URL = f"http://127.0.0.1:{PORT}"


def wait_for_server(url: str, timeout_s: float = 15.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            requests.get(url, timeout=1)
            return True
        except requests.RequestException:
            time.sleep(0.3)
    return False


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mock_hospital_api:app", "--port", str(PORT)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_server(f"{BASE_URL}/patients/1"):
            print("  Mock hospital API did not start in time")
            sys.exit(1)

        store = RemotePatientStore(base_url=BASE_URL)

        # get_profile
        profile = store.get_profile(1)
        assert profile is not None, "Expected profile for patient 1"
        assert profile["name"] == "Ahmad Fadzillah bin Roslan"
        assert profile["condition"] == ["Type 2 Diabetes", "Hypertension"]
        print("  get_profile(1): OK ->", {k: profile[k] for k in ("name", "condition", "personalization_level")})

        # get_profile for missing patient
        assert store.get_profile(999) is None
        print("  get_profile(999): OK -> None (404 handled)")

        # update_supplementary_fields — allowed fields only
        applied = store.update_supplementary_fields(
            patient_id=1,
            updates={"fluid_intake_ml": 1800, "tobacco_status": "Never smoked", "not_a_real_field": "x"},
            source_session_id="remote-store-test-1",
        )
        assert applied == {"fluid_intake_ml": 1800, "tobacco_status": "Never smoked"}, applied
        print("  update_supplementary_fields(1): OK ->", applied)

        # Verify the update is reflected in a subsequent get_profile
        profile2 = store.get_profile(1)
        assert profile2["fluid_intake_ml"] == 1800
        assert profile2["tobacco_status"] == "Never smoked"
        print("  get_profile(1) after update: OK -> fluid_intake_ml=1800, tobacco_status=Never smoked")

        # update for missing patient
        applied_missing = store.update_supplementary_fields(999, {"fluid_intake_ml": 1000})
        assert applied_missing == {}
        print("  update_supplementary_fields(999): OK -> {} (404 handled)")

        print("\nAll RemotePatientStore tests passed.")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
