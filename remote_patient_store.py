"""
RemotePatientStore — production patient data backend.

Calls the hospital/university's patient API over HTTPS. The endpoint contract
below is a placeholder flat-JSON REST shape — update _PATIENT_PATH /
_SUPPLEMENTARY_PATH and _to_profile_dict() once the hospital provides their
real API spec (which may be FHIR-based, in which case _to_profile_dict()
becomes a FHIR Patient/Observation -> profile dict mapper).

Config (env vars):
    HOSPITAL_API_URL      — base URL, e.g. https://hospital.example.com/api/v1
    HOSPITAL_API_KEY      — bearer token (optional)
    HOSPITAL_API_TIMEOUT_S — request timeout in seconds (default 10)

Assumed contract:
    GET   {base_url}/patients/{patient_id}
        -> 200 {<flat profile dict, same shape as LocalPatientStore.get_profile()>}
        -> 404 if not found

    PATCH {base_url}/patients/{patient_id}/supplementary
        body: {"updates": {<field>: <value>, ...}, "source_session_id": "..."}
        -> 200 {"applied": {<field>: <value>, ...}}
        -> 404 if not found
"""
import os

import requests

from patient_store import PatientStore, SUPPLEMENTARY_FIELDS

_PATIENT_PATH = "/patients/{patient_id}"
_SUPPLEMENTARY_PATH = "/patients/{patient_id}/supplementary"


class RemotePatientStore(PatientStore):
    """Reads from and writes to the hospital's patient API over HTTPS."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout or float(os.getenv("HOSPITAL_API_TIMEOUT_S", "10"))

    def _headers(self, content_type: bool = False) -> dict:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_profile(self, patient_id: int) -> dict | None:
        url = self.base_url + _PATIENT_PATH.format(patient_id=patient_id)
        try:
            resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as e:
            print(f"[RemotePatientStore] get_profile({patient_id}) failed: {e}")
            return None

        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_profile_dict(resp.json())

    def update_supplementary_fields(
        self,
        patient_id: int,
        updates: dict,
        source_session_id: str | None = None,
    ) -> dict:
        allowed_updates = {k: v for k, v in updates.items() if k in SUPPLEMENTARY_FIELDS}
        rejected = set(updates.keys()) - set(allowed_updates.keys())
        if rejected:
            print(f"[RemotePatientStore] Rejected non-supplementary fields: {rejected}")

        if not allowed_updates:
            return {}

        url = self.base_url + _SUPPLEMENTARY_PATH.format(patient_id=patient_id)
        body = {"updates": allowed_updates, "source_session_id": source_session_id}
        try:
            resp = requests.patch(url, headers=self._headers(content_type=True), json=body, timeout=self.timeout)
        except requests.RequestException as e:
            print(f"[RemotePatientStore] update_supplementary_fields({patient_id}) failed: {e}")
            return {}

        if resp.status_code == 404:
            print(f"[RemotePatientStore] Patient {patient_id} not found")
            return {}
        resp.raise_for_status()
        return resp.json().get("applied", {})

    @staticmethod
    def _to_profile_dict(raw: dict) -> dict:
        """
        Map the hospital API's patient JSON to the flat profile dict that
        rag.get_rag_response() expects. Placeholder: assumes the hospital
        returns the same flat shape as LocalPatientStore.get_profile().
        """
        profile = dict(raw)
        if "conditions" in profile and "condition" not in profile:
            profile["condition"] = profile.pop("conditions")
        return profile
