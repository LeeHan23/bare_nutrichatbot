"""
Read-only client for the "My Heart Coach" companion app's staging MySQL DB
(credentials in .env: MYHEART_DB_*). This is a separate identity space from
our own Patient table — join key is phone_no/ic_no, not patient_id.

Real schema, explored 2026-08-18 (see docs/state_machine_contract.md): no
care_path/objective_ids/difficulty_ceiling fields exist there at all, so
those stay unimplemented placeholders. What *does* map cleanly: users.risk_level
is an enum('L0','L1','L2','L3') — the exact same vocabulary as our own
Patient.personalization_level — so that's the one signal wired in here, as a
fallback source only, same tier as the existing MHR-screening fallback for
clinical_risk_tier (database.py::patient_to_profile_dict).

Fails soft everywhere: an unreachable DB, a missing env var, or no matching
user must never break a patient-facing chat request — same philosophy as
extractor failures being swallowed (CLAUDE.md Item 19c). Never writes.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_S = 5


def _get_connection():
    host = os.getenv("MYHEART_DB_HOST")
    if not host:
        return None
    import pymysql

    return pymysql.connect(
        host=host,
        port=int(os.getenv("MYHEART_DB_PORT", "3306")),
        user=os.environ["MYHEART_DB_USER"],
        password=os.environ["MYHEART_DB_PASSWORD"],
        database=os.environ["MYHEART_DB_NAME"],
        connect_timeout=_CONNECT_TIMEOUT_S,
    )


def get_myheart_risk_level(phone_number: str | None) -> str | None:
    """Look up the My Heart Coach app's self-reported risk_level (L0-L3) for
    a patient by phone number. Returns None on any failure — unset env,
    unreachable DB, no matching user, or no phone number to look up.
    """
    if not phone_number:
        return None
    try:
        conn = _get_connection()
        if conn is None:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT risk_level FROM users WHERE phone_no = %s LIMIT 1",
                    (phone_number,),
                )
                row = cur.fetchone()
                return row[0] if row else None
    except Exception:
        logger.warning("[MyHeartDB] risk_level lookup failed", exc_info=True)
        return None


def get_myheart_onboarding_stage(phone_number: str | None) -> str | None:
    """Best-effort OB1-3 derived from the My Heart Coach staging DB's
    per-step completion flags — there is no dedicated onboarding_stage
    field in that schema (confirmed live 2026-09-16: 27 tables, `users` has
    is_goals_completed / is_risk_score_completed / is_medicine_completed /
    is_medicine_history_completed booleans instead). This mapping
    (goals -> OB1, risk_score -> OB2, medicine + medicine_history -> OB3) is
    a provisional best guess matched against taxonomy.ONBOARDING_STAGE_LABELS'
    own definitions, NOT confirmed by the My Heart Coach team — same
    fallback tier as get_myheart_risk_level(), explicitly opted into despite
    docs/state_machine_contract.md's standing caution against guessing at
    this external schema (2026-09-15 decision).
    Returns None on any failure, no match, or no completed step yet.
    """
    if not phone_number:
        return None
    try:
        conn = _get_connection()
        if conn is None:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT is_goals_completed, is_risk_score_completed, "
                    "is_medicine_completed, is_medicine_history_completed "
                    "FROM users WHERE phone_no = %s LIMIT 1",
                    (phone_number,),
                )
                row = cur.fetchone()
                return _onboarding_from_flags(*row) if row else None
    except Exception:
        logger.warning("[MyHeartDB] onboarding_stage lookup failed", exc_info=True)
        return None


def _onboarding_from_flags(goals_done, risk_done, med_done, med_hist_done) -> str | None:
    if med_done and med_hist_done:
        return "OB3"
    if risk_done:
        return "OB2"
    if goals_done:
        return "OB1"
    return None


# ---------------------------------------------------------------------------
# Full live profile for a My Heart Coach app user with no local Patient row
# (website_chat_router: ChatRequest.phone_number). Read per request, never
# copied into our DB — decision 2026-10-03. Columns explored live that day.
# ---------------------------------------------------------------------------

# medicine_history yes/no flags -> condition labels for the prompt
_CONDITION_FLAGS = [
    ("is_hbp", "Hypertension"),
    ("is_diabetes", "Diabetes"),
    ("is_poor_kidney_function", "Chronic kidney disease"),  # must hit vector_store "chronic kidney" topic boost
    ("is_heart_failure", "Heart failure"),
    ("is_heart_attack", "Previous heart attack"),
    ("is_minor_stroke", "Previous minor stroke"),
    ("is_gout_attack", "Gout"),
    ("is_leg_pain", "Leg pain when walking"),
]

# (label, column) pairs surfaced as notes; unanswered values are skipped
_GOAL_FIELDS = [
    ("Primary goal", "primary_goal"), ("Primary goals", "primary_goals"),
    ("Other goal", "primary_goal_other"), ("Self-rated health", "health_level"),
    ("Main challenge", "health_challenge"), ("Daily activity level", "daily_active_level"),
    ("Last exercised", "last_health_activity"), ("Exercise minutes per day", "daily_exercise_minute"),
    ("Physical injury", "physical_injury"), ("Physical problems", "physical_problems"),
    ("Injured body parts", "injured_body_parts"), ("Average sleep hours", "average_sleep_hours"),
    ("Target weight kg", "target_weight"),
]
_HISTORY_FIELDS = [
    ("High BP for", "hbp_duration"), ("Diabetes for", "diabetes_duration"),
    ("Kidney creatinine reading", "pkf_creatinine_reading"), ("Heart failure severity", "hf_severity_scale"),
    ("Heart failure symptoms", "hf_symptoms"), ("Heart attack how long ago", "ha_duration"),
    ("Heart procedure", "is_ha_heart_procedure"), ("Stroke how long ago", "stroke_duration"),
    ("Gout frequency", "ga_frequency"), ("BMI", "bmi"), ("Smoking", "is_cigarettes"),
    ("Cigarettes per day", "cigarettes_daily_count"), ("Stopped smoking for", "cigarettes_stopped_duration"),
    ("Vape sessions per day", "vape_sessions_per_day"),
]
_RISK_FIELDS = [
    ("Recent heart attack date", "recent_heart_attack_date"), ("Total cholesterol", "total_cholesterol"),
    ("HDL cholesterol", "good_cholesterol"), ("LDL cholesterol", "bad_cholesterol"),
    ("Blood pressure", "blood_pressure"), ("Fasting blood sugar", "fasting_blood_sugar"),
    ("Weak heart", "has_heart_weak"), ("Heart procedure", "increase_blood_flow_procedure"),
    ("Abnormal ECG", "is_ecg_abnormal"), ("Diabetes medicine", "diabetes_medicine"),
    ("On cholesterol medicine", "is_cholesterol_medicine"),
    ("On blood pressure medicine", "is_high_blood_pressure_medicine"),
    ("On heart rhythm medicine", "is_heart_rhythm_medicine"),
]
_VITAL_FIELDS = [
    ("Pulse bpm", "pulse_bpm"), ("Systolic mmHg", "systolic_mmHg"), ("Diastolic mmHg", "diastolic_mmHg"),
    ("Blood sugar mmol/L", "blood_sugar_mmolL"), ("SpO2 %", "spo2_percent"),
    ("HbA1c %", "hba1c_percent"), ("Cholesterol mg/dL", "cholesterol_mgdL"),
]
_UNANSWERED = (None, "", "NOT_SURE", "DONT_KNOW", [])


def _value(v):
    """JSON-column strings -> lists; app enums -> readable text ('IMPROVE_FITNESS' -> 'improve fitness')."""
    if isinstance(v, str) and v.startswith("["):
        v = json.loads(v)
    if isinstance(v, list):
        return [_value(x) for x in v if x not in _UNANSWERED]
    return v.replace("_", " ").lower() if isinstance(v, str) else v


def _facts(row: dict | None, fields: list) -> list[str]:
    out = []
    for label, col in fields:
        v = _value(row.get(col)) if row else None
        if v in _UNANSWERED or v == "not sure":
            continue
        out.append(f"{label}: {', '.join(map(str, v)) if isinstance(v, list) else v}")
    return out


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_myheart_profile(user, goals, history, risk, vitals, med_rows) -> dict:
    """Pure mapping of staging rows -> the profile dict rag.get_rag_response()
    consumes (same keys as database.patient_to_profile_dict)."""
    conditions = [label for col, label in _CONDITION_FLAGS if history and history.get(col)]
    if risk and risk.get("is_diabetes") and "Diabetes" not in conditions:
        conditions.append("Diabetes")
    if risk and risk.get("recent_heart_attack_date") and "Previous heart attack" not in conditions:
        conditions.append("Previous heart attack")

    medications = []
    for row in med_rows:
        for m in _value(row.get("medicines")) or []:
            if m not in medications:
                medications.append(m)
        if row.get("other_medicines"):
            medications.append(row["other_medicines"])

    notes = ["Self-reported in the My Heart Coach app."]
    if user.get("preferred_language"):
        notes.append(f"Preferred language: {user['preferred_language']}")
    for heading, row, fields in (
        ("Goals", goals, _GOAL_FIELDS),
        ("Medical history", history, _HISTORY_FIELDS),
        ("Risk questionnaire", risk, _RISK_FIELDS),
        (f"Latest vitals ({vitals['date']})" if vitals else "", vitals, _VITAL_FIELDS),
    ):
        facts = _facts(row, fields)
        if facts:
            notes.append(f"{heading}: " + "; ".join(facts))

    exercise = (_value(goals.get("exercise_types")) or [_value(goals.get("exercise_type"))]) if goals else []
    return {
        "condition": conditions,
        "medications": medications,
        "dietary_restrictions": [],
        "allergies": [],
        "name": user.get("full_name"),
        "gender": (user.get("gender") or "").capitalize() or None,
        "weight_kg": _float(goals.get("current_weight")) if goals else None,
        "height_cm": _float(goals.get("height")) if goals else None,
        "activity_types": [e for e in exercise if e and e != "none"],
        "notes": "\n".join(notes),
        "personalization_level": user.get("risk_level"),
        "onboarding_stage": _onboarding_from_flags(
            user.get("is_goals_completed"), user.get("is_risk_score_completed"),
            user.get("is_medicine_completed"), user.get("is_medicine_history_completed"),
        ),
    }


def get_myheart_profile(phone_number: str | None) -> dict | None:
    """Live profile for the staging `users` row with this phone number.
    None on any failure or no match — the chat then answers unpersonalized."""
    if not phone_number:
        return None
    try:
        conn = _get_connection()
        if conn is None:
            return None
        from pymysql.cursors import DictCursor

        with conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE phone_no = %s LIMIT 1", (phone_number,))
                user = cur.fetchone()
                if not user:
                    logger.info("[MyHeartDB] no staging user for %s", phone_number)
                    return None

                def latest(sql):
                    cur.execute(sql, (user["id"],))
                    return cur.fetchone()

                goals = latest("SELECT * FROM goals WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1")
                history = latest("SELECT * FROM medicine_history WHERE user_id = %s ORDER BY id DESC LIMIT 1")
                risk = latest("SELECT * FROM risk_score WHERE user_id = %s ORDER BY id DESC LIMIT 1")
                vitals = latest("SELECT * FROM user_vital_signs WHERE user_id = %s ORDER BY reading_time DESC LIMIT 1")
                cur.execute("SELECT medicines, other_medicines FROM medicine WHERE user_id = %s ORDER BY id", (user["id"],))
                med_rows = cur.fetchall()
        return build_myheart_profile(user, goals, history, risk, vitals, med_rows)
    except Exception:
        logger.warning("[MyHeartDB] profile lookup failed", exc_info=True)
        return None


if __name__ == "__main__":
    # Mapping self-check on rows shaped like the real staging data
    p = build_myheart_profile(
        {"full_name": "T", "gender": "FEMALE", "risk_level": "L1", "preferred_language": "BM",
         "is_goals_completed": 1, "is_risk_score_completed": 1, "is_medicine_completed": 0,
         "is_medicine_history_completed": 0},
        {"primary_goal": "HEART_HEALTH_DIET", "height": "157", "current_weight": "43",
         "exercise_type": "LIGHT", "exercise_types": None, "physical_problems": "[]"},
        {"is_hbp": 1, "is_diabetes": 0, "is_cigarettes": "NEVER_SMOKED", "bmi": "17.4"},
        {"is_diabetes": 1, "total_cholesterol": "5.2", "good_cholesterol": "NOT_SURE"},
        None,
        [{"medicines": None, "other_medicines": None}, {"medicines": '["ATORVASTATIN"]', "other_medicines": ""}],
    )
    assert p["condition"] == ["Hypertension", "Diabetes"], p["condition"]
    assert p["medications"] == ["atorvastatin"], p["medications"]
    assert (p["weight_kg"], p["height_cm"], p["gender"]) == (43.0, 157.0, "Female")
    assert p["onboarding_stage"] == "OB2" and p["personalization_level"] == "L1"
    assert p["activity_types"] == ["light"]
    assert "Primary goal: heart health diet" in p["notes"] and "HDL" not in p["notes"]
    assert "Physical problems" not in p["notes"] and "Total cholesterol: 5.2" in p["notes"]
    print(get_myheart_risk_level("+60000000000"))
    print(get_myheart_onboarding_stage("+60000000000"))
    print("OK — no exception on a non-matching lookup")
