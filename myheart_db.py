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
                if not row:
                    return None
                goals_done, risk_done, med_done, med_hist_done = row
                if med_done and med_hist_done:
                    return "OB3"
                if risk_done:
                    return "OB2"
                if goals_done:
                    return "OB1"
                return None
    except Exception:
        logger.warning("[MyHeartDB] onboarding_stage lookup failed", exc_info=True)
        return None


if __name__ == "__main__":
    print(get_myheart_risk_level("+60000000000"))
    print(get_myheart_onboarding_stage("+60000000000"))
    print("OK — no exception on a non-matching lookup")
