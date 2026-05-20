"""
demo_extractor.py — Live demo of the profile extractor.

Shows how the chatbot passively learns patient data from natural conversation,
including Bahasa Malaysia messages.

Usage:
    python scripts/demo_extractor.py
    python scripts/demo_extractor.py --patient-id 4
    python scripts/demo_extractor.py --patient-id 7   # post-CABG patient
    python scripts/demo_extractor.py --reset          # clear fields before running

Requires Ollama reachable at OLLAMA_BASE_URL.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import database as db
from extractor import extract_from_message, EXTRACTOR_FIELDS
from local_patient_store import LocalPatientStore
from patient_store import SUPPLEMENTARY_FIELDS

# ─── ANSI colours ────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
RED    = "\033[31m"
WHITE  = "\033[97m"
BG_DARK = "\033[48;5;234m"

def c(text, *codes): return "".join(codes) + str(text) + RESET
def hr(char="─", width=72): return c(char * width, DIM)

# ─── Demo conversation scripts ────────────────────────────────────────────────

DEMO_MESSAGES = [
    {
        "label": "Fluid intake (Bahasa Malaysia)",
        "message": "Saya minum lebih kurang 6 gelas air sehari. Kadang-kadang minum teh tarik juga.",
        "expect": ["fluid_intake_ml"],
    },
    {
        "label": "Medication compliance (English)",
        "message": "I sometimes forget to take my evening blood pressure pill — maybe miss it once or twice a week.",
        "expect": ["medication_compliance"],
    },
    {
        "label": "Fat sources + intake level (Manglish)",
        "message": "Every day I goreng my food with palm oil lah. Sometimes use lard when cooking pork.",
        "expect": ["fat_intake_level", "fat_sources"],
    },
    {
        "label": "Religion + tobacco + alcohol (English)",
        "message": "I'm Muslim, so I don't drink alcohol at all. I've never smoked in my life.",
        "expect": ["religion", "alcohol_per_week", "tobacco_status"],
    },
    {
        "label": "Physical activity (Bahasa Malaysia)",
        "message": "Saya berjoging tiga kali seminggu, lebih kurang 30 minit setiap kali. Slow-slow je, jalan kaki kebanyakannya.",
        "expect": ["activity_freq", "activity_minutes", "activity_types", "activity_intensity"],
    },
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

SUPPLEMENTARY_DISPLAY_FIELDS = [f["field"] for f in EXTRACTOR_FIELDS]


def get_patient_supplementary(patient) -> dict:
    """Return only the supplementary fields, skipping None/empty values."""
    result = {}
    for field in SUPPLEMENTARY_DISPLAY_FIELDS:
        v = getattr(patient, field, None)
        if v is not None and v != [] and v != "":
            result[field] = v
    return result


def print_profile_table(filled: dict, label: str):
    all_fields = SUPPLEMENTARY_DISPLAY_FIELDS
    print(f"\n  {c(label, BOLD, CYAN)}")
    print(f"  {'Field':<28} {'Value'}")
    print(f"  {hr('─', 60)}")
    for field in all_fields:
        val = filled.get(field)
        if val is not None and val != [] and val != "":
            display = json.dumps(val) if isinstance(val, list) else str(val)
            print(f"  {c(field, GREEN):<37} {c(display, WHITE)}")
        else:
            print(f"  {c(field, DIM):<37} {c('—  (empty)', DIM)}")
    filled_count = sum(1 for f in all_fields if filled.get(f) not in (None, [], ""))
    print(f"\n  {c(f'{filled_count}/{len(all_fields)} fields filled', BOLD)}")


def reset_supplementary(patient_id: int):
    """Clear all supplementary fields for the demo patient."""
    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            print(c(f"Patient {patient_id} not found.", RED))
            return
        for field in SUPPLEMENTARY_FIELDS:
            col = db.Patient.__table__.columns.get(field)
            if col is not None:
                default = [] if str(col.type) == "JSON" else None
                setattr(patient, field, default)
        patient.extractor_metadata = {}
        session.commit()
        print(c(f"  Supplementary fields reset for patient {patient_id}.", YELLOW))
    finally:
        session.close()


def get_patient_info(patient_id: int):
    session = db.SessionLocal()
    try:
        return db.get_patient(session, patient_id)
    finally:
        session.close()

# ─── Main demo ────────────────────────────────────────────────────────────────

def run_demo(patient_id: int, do_reset: bool):
    store = LocalPatientStore()

    print()
    print(c("━" * 72, BOLD, CYAN))
    print(c("  NutriChatbot — Profile Extractor Live Demo", BOLD, WHITE))
    print(c("  Passive, zero-latency data collection from natural conversation", DIM))
    print(c("━" * 72, BOLD, CYAN))

    # Load patient
    patient = get_patient_info(patient_id)
    if not patient:
        print(c(f"\n  ERROR: Patient {patient_id} not found in the database.", RED))
        print(c("  Run: python seed_patients.py", DIM))
        sys.exit(1)

    print(f"\n  {c('Patient:', BOLD)}  {c(patient.name, WHITE, BOLD)}")
    print(f"  {c('ID:', BOLD)}        {patient.id}")
    print(f"  {c('Level:', BOLD)}     {c(patient.personalization_level or 'unset', YELLOW)}")
    print(f"  {c('Conditions:', BOLD)} {', '.join(patient.conditions or []) or '—'}")

    # Optionally reset
    if do_reset:
        print()
        reset_supplementary(patient_id)

    # Show before state
    current_profile = store.get_profile(patient_id)
    filled_before = get_patient_supplementary(db.SessionLocal().query(db.Patient).get(patient_id))
    print_profile_table(filled_before, "Supplementary profile — BEFORE")

    input(f"\n  {c('Press Enter to start the demo...', BOLD, YELLOW)}")

    # Run each message
    for i, item in enumerate(DEMO_MESSAGES, 1):
        print()
        print(hr())
        print(c(f"  Message {i}/{len(DEMO_MESSAGES)} — {item['label']}", BOLD, WHITE))
        print(hr())
        print()
        print(f"  {c('Patient says:', BOLD, CYAN)}")
        print(f"  {c('«', DIM)} {c(item['message'], WHITE)} {c('»', DIM)}")
        print()

        # Reload profile for current known fields
        current_profile = store.get_profile(patient_id)

        print(c("  Sending to qwen2.5:32b extractor...", DIM), end="", flush=True)
        t0 = time.time()

        new_fields = extract_from_message(item["message"], current_profile)

        elapsed = time.time() - t0
        print(c(f" done ({elapsed:.1f}s)", DIM))
        print()

        if not new_fields:
            print(c("  ✗  Nothing new extracted from this message.", YELLOW))
        else:
            print(c(f"  ✓  Extracted {len(new_fields)} new field(s):", GREEN, BOLD))
            for field, value in new_fields.items():
                expected = field in item.get("expect", [])
                marker = c("✓", GREEN) if expected else c("*", YELLOW)
                display = json.dumps(value) if isinstance(value, list) else repr(value)
                print(f"      {marker}  {c(field, BOLD):<30} = {c(display, WHITE)}")

            # Write to DB
            applied = store.update_supplementary_fields(
                patient_id=patient_id,
                updates=new_fields,
                source_session_id=f"demo-session-{i}",
            )
            print()
            print(c(f"  → Written to database ({len(applied)} field(s) saved).", GREEN))

        expected_fields = item.get("expect", [])
        missed = [f for f in expected_fields if f not in (new_fields or {})]
        if missed:
            print(c(f"  ⚠  Expected but not extracted: {', '.join(missed)}", YELLOW))

        if i < len(DEMO_MESSAGES):
            input(f"\n  {c('Press Enter for next message...', DIM, YELLOW)}")

    # Show after state
    session = db.SessionLocal()
    patient_after = session.query(db.Patient).get(patient_id)
    filled_after = get_patient_supplementary(patient_after)
    session.close()

    print()
    print(hr("━"))
    print_profile_table(filled_after, "Supplementary profile — AFTER")

    # Summary
    filled_before_count = sum(1 for f in SUPPLEMENTARY_DISPLAY_FIELDS
                               if filled_before.get(f) not in (None, [], ""))
    filled_after_count  = sum(1 for f in SUPPLEMENTARY_DISPLAY_FIELDS
                               if filled_after.get(f) not in (None, [], ""))
    gained = filled_after_count - filled_before_count

    print()
    print(c("━" * 72, BOLD, CYAN))
    print(c(f"  Demo complete. Gained {gained} new field(s) from {len(DEMO_MESSAGES)} messages.", BOLD, WHITE))
    print(c("  All writes are additive — no clinical data was touched.", DIM))
    print(c("  In production this runs silently in the background, zero patient latency.", DIM))
    print(c("━" * 72, BOLD, CYAN))
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NutriChatbot extractor demo")
    parser.add_argument(
        "--patient-id", type=int, default=4,
        help="Patient ID to demo (default: 4 — Mohd Hafizuddin, dyslipidaemia + obesity)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear all supplementary fields before running the demo",
    )
    args = parser.parse_args()

    run_demo(args.patient_id, args.reset)
