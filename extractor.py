"""
Profile extractor — analyses patient messages and extracts new supplementary
profile fields (eNCPT 2020 aligned).

Pipeline:
    User message  →  qwen2.5:32b  →  JSON of new fields  →  PatientStore

The extractor is intentionally conservative:
- Only extracts what is explicitly stated (no inference)
- Only fills fields that are currently empty (never overwrites)
- Only writes whitelisted supplementary fields (clinical fields rejected by
  PatientStore layer regardless)
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


# Tier-1 fields the extractor is responsible for in v1.
# Each entry: (field_name, eNCPT code, type hint, format guidance)
EXTRACTOR_FIELDS = [
    {
        "field": "fluid_intake_ml",
        "encpt": "FH-1.2.1.1.1",
        "type": "integer (mL per day)",
        "guidance": "Convert glasses/cups to mL (1 glass ≈ 250mL). Only daily total fluid.",
    },
    {
        "field": "alcohol_per_week",
        "encpt": "FH-1.4.1.1",
        "type": "integer (drinks per week)",
        "guidance": "Standard drinks per week. 0 if patient says they don't drink.",
    },
    {
        "field": "supplements",
        "encpt": "FH-3.2.1",
        "type": "list of strings",
        "guidance": "Names of supplements/vitamins/minerals the patient takes. Empty list if none.",
    },
    {
        "field": "religion",
        "encpt": "CH-3.1.7",
        "type": "string",
        "guidance": "The patient's religion (e.g. Islam, Hinduism, Buddhism, Judaism, Christianity, Sikhism). Do NOT extract dietary practices like 'Halal' or 'Kosher' here — those are derived from religion, not the religion itself. Only extract when the patient mentions their religion explicitly.",
    },
    {
        "field": "tobacco_status",
        "encpt": "CH-1.1.10",
        "type": "string",
        "guidance": "One of: 'Never smoked', 'Current smoker', 'Former smoker'.",
    },
]


EXTRACTION_PROMPT = """You are a clinical data extractor for a nutrition chatbot.
Your job is to extract NEW patient information from their latest message,
based ONLY on what they explicitly say.

CRITICAL RULES:
1. ONLY extract information explicitly stated by the patient.
2. DO NOT guess, infer, or assume. If unsure, leave the field out.
3. DO NOT extract fields the patient did not mention.
4. Return a JSON object with ONLY the fields you found new information for.
5. If nothing new is found, return exactly: {{}}
6. Do not include any explanation, only valid JSON.

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
  {{"supplements": ["fish oil", "vitamin D"], "tobacco_status": "Never smoked"}}
"""


def _build_field_descriptions() -> str:
    """Format the field list for inclusion in the prompt."""
    lines = []
    for f in EXTRACTOR_FIELDS:
        lines.append(
            f'- "{f["field"]}" ({f["type"]}): {f["guidance"]}'
        )
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
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _validate_extraction(extracted: dict) -> dict:
    """Filter to only known fields and basic type sanity."""
    valid_fields = {f["field"] for f in EXTRACTOR_FIELDS}
    cleaned = {}

    for key, value in extracted.items():
        if key not in valid_fields:
            continue  # Unknown field — drop silently

        # Basic type checks
        if key == "fluid_intake_ml":
            if isinstance(value, (int, float)) and 0 < value < 10000:
                cleaned[key] = int(value)
        elif key == "alcohol_per_week":
            if isinstance(value, (int, float)) and 0 <= value < 200:
                cleaned[key] = int(value)
        elif key == "supplements":
            if isinstance(value, list) and all(isinstance(s, str) for s in value):
                cleaned[key] = [s.strip() for s in value if s.strip()]
        elif key == "religion":
            if isinstance(value, str) and value.strip() and len(value) < 100:
                cleaned[key] = value.strip()
        elif key == "tobacco_status":
            allowed = {"Never smoked", "Current smoker", "Former smoker"}
            if isinstance(value, str) and value.strip() in allowed:
                cleaned[key] = value.strip()

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
        # Treat None, empty list, empty string as "empty"
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
            "temperature": 0.0,   # Deterministic extraction
            "num_predict": 200,
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
