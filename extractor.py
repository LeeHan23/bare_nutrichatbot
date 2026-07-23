"""
Profile extractor — analyses patient messages and extracts new supplementary
profile fields aligned with the cardiac eNCPT schema.

Pipeline:
    User message  →  qwen2.5:32b  →  JSON of new fields  →  PatientStore

The extractor is intentionally conservative:
- Only extracts what is explicitly stated (no inference)
- Only fills fields that are currently empty (never overwrites)
- Validates against allowed_values where applicable
- Handles patient messages in English, Bahasa Malaysia, or mixed
"""
import json
import os
import re
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:32b")
EXTRACTOR_TIMEOUT_S = 30


# ─────────────────────────────────────────────────────────────────────────
# Field definitions for v2 — cardiac focus
# Maps eNCPT codes to DB column names and validation rules
# ─────────────────────────────────────────────────────────────────────────

EXTRACTOR_FIELDS = [
    # ── Tier 1 (cardiac critical) ───────────────────────────────────────
    {
        "field": "fluid_intake_ml",
        "encpt": "FH-1.2.1.1.1",
        "type": "integer (mL per day)",
        "guidance": "Convert glasses/cups to mL (1 glass ≈ 250mL, 1 cup ≈ 250mL). Only daily total fluid. Range 0-10000.",
    },
    {
        "field": "alcohol_per_week",
        "encpt": "FH-1.4.1.1",
        "type": "integer (drinks per week)",
        "guidance": "Standard drinks per week. 0 if patient says they don't drink.",
    },
    {
        "field": "tobacco_status",
        "encpt": "CH-1.1.10",
        "type": "string (one of: 'Never smoked', 'Current smoker', 'Former smoker')",
        "guidance": "Map patient statements: 'never smoked'/'tidak merokok' → 'Never smoked'; 'I smoke'/'saya merokok' → 'Current smoker'; 'quit X years ago'/'berhenti X tahun lepas' → 'Former smoker'.",
    },
    {
        "field": "fat_intake_level",
        "encpt": "FH-1.5.1.1",
        "type": "string (one of: 'low', 'moderate', 'high')",
        "guidance": "Estimate qualitative level from food sources mentioned. Daily fried/fatty foods, OR daily use of a fat/oil/butter/ghee/lard as a cooking medium → 'high'. Few times/week fried foods or fatty cooking fats → 'moderate'. Rarely fried, mostly steamed/grilled, or uses oil sparingly → 'low'. Don't extract if patient hasn't described their fat-related eating.",
    },
    {
        "field": "sodium_awareness",
        "encpt": "FH-1.5.6.1",
        "type": "string (one of: 'low_awareness_high_intake', 'moderate', 'actively_restricting')",
        "guidance": "If patient adds salt freely / never reads labels / uses lots of soy sauce → 'low_awareness_high_intake'. If they're aware but inconsistent → 'moderate'. If actively reducing salt / reads labels → 'actively_restricting'.",
    },
    {
        "field": "religion",
        "encpt": "CH-3.1.7",
        "type": "string (e.g. 'Islam', 'Hinduism', 'Buddhism', 'Christianity')",
        "guidance": "The patient's religion (e.g. Islam, Hinduism, Buddhism, Judaism, Christianity, Sikhism). Do NOT extract dietary practices like 'Halal' or 'Kosher' here — those are derived from religion. Only extract when the patient mentions their religion explicitly.",
    },
    {
        "field": "supplements",
        "encpt": "FH-3.2.1",
        "type": "list of strings",
        "guidance": "Names of supplements/vitamins/minerals the patient takes. Empty list if none. Examples: ['fish oil', 'vitamin D', 'CoQ10'].",
    },

    # ── Tier 2 (cardiac priority) ────────────────────────────────────────
    {
        "field": "medication_compliance",
        "encpt": "FH-3.1.1.1",
        "type": "string (one of: 'good', 'variable', 'poor')",
        "guidance": "If patient says they always take meds → 'good'. If 'sometimes I forget' / 'occasional misses' → 'variable'. If 'often skip' / 'don't like taking' / 'haven't taken in weeks' → 'poor'.",
    },
    {
        "field": "fat_sources",
        "encpt": "FH-1.5.1.2",
        "type": "list of strings",
        "guidance": "Capture raw food sources mentioned: cooking oils (palm oil, olive oil, coconut oil, ghee), butter, margarine, lard, fatty meats. Empty list if not mentioned.",
    },
    {
        "field": "activity_freq",
        "encpt": "FH-7.3.1",
        "type": "string (frequency phrase)",
        "guidance": "How often patient exercises. Examples: 'daily', '3 times a week', 'twice a week', 'rarely', 'never'.",
    },
    {
        "field": "activity_minutes",
        "encpt": "FH-7.3.2",
        "type": "integer (minutes per session)",
        "guidance": "Duration of one exercise session in minutes. Range 0-300.",
    },
    {
        "field": "activity_types",
        "encpt": "FH-7.3.1.1",
        "type": "list of strings",
        "guidance": "Types of activity mentioned. Examples: ['walking', 'cycling', 'swimming', 'gym', 'yoga', 'badminton', 'football'].",
    },
    {
        "field": "activity_intensity",
        "encpt": "FH-7.3.3",
        "type": "string (one of: 'light', 'moderate', 'vigorous')",
        "guidance": "Patient's described exertion. 'Easy'/'leisurely' → 'light'. 'Bit out of breath'/'sweat a bit' → 'moderate'. 'Very intense'/'cardio' → 'vigorous'.",
    },
    {
        "field": "extractor_food_allergies",
        "encpt": "PD-1.1.9",
        "type": "list of strings",
        "guidance": "Food allergies the patient self-reports in conversation (distinct from the hospital-supplied 'allergies' clinical field). Examples: ['shellfish', 'peanuts', 'shrimp']. Empty list if none mentioned.",
    },
]


EXTRACTION_PROMPT = """You are a clinical data extractor for a cardiac nutrition chatbot.
Your job is to extract NEW patient information from their latest message,
based ONLY on what they explicitly say.

The patient may write in English, Bahasa Malaysia, or a mix of both (rojak).
Extract from any of these languages.

CRITICAL RULES:
1. ONLY extract information explicitly stated by the patient.
2. DO NOT guess, infer, or assume. If unsure, leave the field out.
3. DO NOT extract fields the patient did not mention.
4. For fields with allowed values, use ONLY those exact values.
5. Return a JSON object with ONLY the fields you found new information for.
6. If nothing new is found, return exactly: {{}}
7. Do not include any explanation, only valid JSON.

FIELDS TO EXTRACT (only if the patient mentions them):
{field_descriptions}

WHAT THE BOT ALREADY KNOWS ABOUT THIS PATIENT (do not extract these again):
{known}

PATIENT'S LATEST MESSAGE:
"{message}"

Return ONLY a JSON object. No prose. No markdown. Just JSON.
Example valid responses:
  {{}}
  {{"fluid_intake_ml": 1500}}
  {{"fat_intake_level": "high", "fat_sources": ["palm oil", "butter"]}}
  {{"medication_compliance": "variable", "activity_types": ["walking"]}}
  {{"extractor_food_allergies": ["shellfish", "peanuts"]}}
"""


def _build_field_descriptions() -> str:
    """Format the field list for inclusion in the prompt."""
    lines = []
    for f in EXTRACTOR_FIELDS:
        lines.append(f'- "{f["field"]}" ({f["type"]}): {f["guidance"]}')
    return "\n".join(lines)


def _build_known_summary(profile: dict | None) -> str:
    """Show the LLM what's already known so it doesn't re-extract."""
    if not profile:
        return "Nothing yet."

    relevant_keys = [f["field"] for f in EXTRACTOR_FIELDS]
    known_items = []
    for k in relevant_keys:
        v = profile.get(k)
        if v is not None and v != [] and v != {}:
            known_items.append(f"  {k}: {v}")

    if not known_items:
        return "Nothing relevant to the extractor fields yet."
    return "\n".join(known_items)


def _strip_json_response(text: str) -> str:
    """Strip markdown fences and other LLM noise from a JSON response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# Validators per field
def _validate_field(key: str, value: Any) -> tuple[bool, Any]:
    """Returns (valid, cleaned_value)."""
    if key == "fluid_intake_ml":
        if isinstance(value, (int, float)) and 0 < value < 10000:
            return True, int(value)

    elif key == "alcohol_per_week":
        if isinstance(value, (int, float)) and 0 <= value < 200:
            return True, int(value)

    elif key == "supplements":
        if isinstance(value, list) and all(isinstance(s, str) for s in value):
            cleaned = [s.strip() for s in value if s.strip()]
            return True, cleaned

    elif key == "religion":
        if isinstance(value, str) and value.strip() and len(value) < 100:
            return True, value.strip()

    elif key == "tobacco_status":
        allowed = {"Never smoked", "Current smoker", "Former smoker"}
        if isinstance(value, str) and value.strip() in allowed:
            return True, value.strip()

    elif key == "fat_intake_level":
        allowed = {"low", "moderate", "high"}
        if isinstance(value, str) and value.strip().lower() in allowed:
            return True, value.strip().lower()

    elif key == "sodium_awareness":
        allowed = {"low_awareness_high_intake", "moderate", "actively_restricting"}
        if isinstance(value, str) and value.strip() in allowed:
            return True, value.strip()

    elif key == "medication_compliance":
        allowed = {"good", "variable", "poor"}
        if isinstance(value, str) and value.strip().lower() in allowed:
            return True, value.strip().lower()

    elif key == "fat_sources":
        if isinstance(value, list) and all(isinstance(s, str) for s in value):
            cleaned = [s.strip().lower() for s in value if s.strip()]
            return True, cleaned

    elif key == "activity_freq":
        if isinstance(value, str) and value.strip() and len(value) < 100:
            return True, value.strip()

    elif key == "activity_minutes":
        if isinstance(value, (int, float)) and 0 < value < 300:
            return True, int(value)

    elif key == "activity_types":
        if isinstance(value, list) and all(isinstance(s, str) for s in value):
            cleaned = [s.strip().lower() for s in value if s.strip()]
            return True, cleaned

    elif key == "activity_intensity":
        allowed = {"light", "moderate", "vigorous"}
        if isinstance(value, str) and value.strip().lower() in allowed:
            return True, value.strip().lower()

    elif key == "extractor_food_allergies":
        if isinstance(value, list) and all(isinstance(s, str) for s in value):
            cleaned = [s.strip().lower() for s in value if s.strip()]
            return True, cleaned

    return False, None


def _validate_extraction(extracted: dict) -> dict:
    """Filter to only known fields and validate types/values."""
    valid_fields = {f["field"] for f in EXTRACTOR_FIELDS}
    cleaned = {}

    for key, value in extracted.items():
        if key not in valid_fields:
            continue  # Unknown field — drop silently

        valid, cleaned_value = _validate_field(key, value)
        if valid:
            cleaned[key] = cleaned_value

    return cleaned


def _filter_already_filled(extracted: dict, current_profile: dict | None) -> dict:
    """
    Apply the 'only fill if empty' policy: drop fields that already have a value.
    Hospital-supplied data is sacred; the extractor is purely additive.
    """
    if not current_profile:
        return extracted

    result = {}
    for key, value in extracted.items():
        existing = current_profile.get(key)
        if existing is None or existing == [] or existing == "":
            result[key] = value
    return result


def call_ollama_extractor(prompt: str) -> str:
    """Call Ollama and return the raw text response."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 250,
        },
    }
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=EXTRACTOR_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def extract_from_message(message: str, current_profile: dict | None = None) -> dict:
    """
    Main entry point. Given a patient message and their current profile,
    return a dict of NEW supplementary fields to write.

    Returns {} if nothing new was found or on any extraction error.
    """
    if not message or not message.strip():
        return {}

    prompt = EXTRACTION_PROMPT.format(
        field_descriptions=_build_field_descriptions(),
        known=_build_known_summary(current_profile),
        message=message.strip(),
    )

    try:
        raw = call_ollama_extractor(prompt)
    except Exception as e:
        print(f"[Extractor] Ollama call failed: {e}")
        return {}

    cleaned = _strip_json_response(raw)
    if not cleaned:
        return {}

    try:
        extracted = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"[Extractor] Invalid JSON from LLM: {cleaned[:200]}")
        return {}

    if not isinstance(extracted, dict):
        return {}

    validated = _validate_extraction(extracted)
    only_new = _filter_already_filled(validated, current_profile)

    if only_new:
        print(f"[Extractor] Extracted {len(only_new)} new field(s): {list(only_new.keys())}")
    return only_new
