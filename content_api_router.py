"""
content_api_router.py — REST API for clients to fetch E/K/A weekly content.

All GET endpoints require X-API-Key header (same key used for chat).
Admin actions (approve, generate) also require X-Admin-Password header.

Endpoints:
  GET  /content/materials           — list with filters
  GET  /content/materials/{id}      — single material
  GET  /content/weekly-feed         — this week's E+K+A for given conditions
  GET  /content/patient-feed/{id}   — this week's feed matched to a specific patient
  POST /content/materials/{id}/approve  — mark is_active=True (admin)

Note: the generator itself (scripts/generate_weekly_eka.py) was retired
2026-08-12, then restored 2026-08-14 rebuilt on the taxonomy safety
guardrails (see that script's docstring) and driven by a Monday 06:00 cron
(scripts/weekly_eka_scheduler.py), not an API trigger. The POST
/content/generate-weekly admin endpoint that used to trigger it on demand
was not restored — re-add it here if on-demand generation is needed;
until then, use the script directly: `python scripts/generate_weekly_eka.py`.
"""
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import func
from sqlalchemy.orm import Session

import database as db
from dependencies import get_db, get_api_client

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_in_secrets")

TYPE_LABELS = {"E": "Exercise", "K": "Knowledge", "A": "Activity"}


def _serialize_material(mat) -> dict:
    from datetime import datetime
    expires_at = mat.expires_at.isoformat() if mat.expires_at else None
    is_expired = (mat.expires_at is not None and mat.expires_at < datetime.utcnow())
    return {
        "id":               mat.id,
        "content_type":     mat.content_type,
        "content_type_label": TYPE_LABELS.get(mat.content_type, "Nutrition"),
        "condition_group":  mat.condition_group,
        "condition_tags":   mat.condition_tags or [],
        "personalization_level": mat.personalization_level,
        "onboarding_stage": mat.onboarding_stage,
        "week_number":      mat.week_number,
        "day_offset":       mat.day_offset,
        "topic":            mat.topic,
        "title":            mat.title,
        "is_active":        mat.is_active,
        "content":          mat.raw_tips,
        "review_notes":     mat.review_notes or [],
        "created_at":       mat.created_at.isoformat() if mat.created_at else None,
        "expires_at":       expires_at,
        "is_expired":       is_expired,
    }


# ---------------------------------------------------------------------------
# GET /content/materials
# ---------------------------------------------------------------------------

@router.get("/materials")
def list_materials(
    content_type:    Optional[str] = Query(None, description="E | K | A"),
    week_number:     Optional[int] = Query(None, description="ISO week number"),
    condition_group: Optional[str] = Query(None, description="T2DM | HTN | CKD | Cardiac | Dyslipidaemia | General | Mental Health | Stress Management | Sleep | Atrial Fibrillation | Heart Failure | CVD Risk Management | PCOS"),
    is_active:       Optional[bool] = Query(None, description="Filter by approval status"),
    include_expired: bool = Query(False, description="Include materials past their 14-day expiry (default: false)"),
    limit:           int  = Query(100, ge=1, le=500),
    offset:          int  = Query(0, ge=0),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """
    List content materials with optional filters.

    Returns weekly E/K/A materials matching the given filters.
    Expired materials (older than 14 days) are excluded by default.
    Use `week_number` to get a specific week; omit for all weeks.
    """
    materials = db.get_materials_by_filters(
        database,
        content_type=content_type,
        week_number=week_number,
        condition_group=condition_group,
        is_active=is_active,
        include_expired=include_expired,
        limit=limit,
        offset=offset,
    )
    return {
        "total":     len(materials),
        "offset":    offset,
        "limit":     limit,
        "materials": [_serialize_material(m) for m in materials],
    }


# ---------------------------------------------------------------------------
# GET /content/materials/{id}
# ---------------------------------------------------------------------------

@router.get("/materials/{material_id}")
def get_material(
    material_id: int,
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """Get a single content material by ID, including full structured content."""
    mat = database.query(db.ContentMaterial).filter(db.ContentMaterial.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    return _serialize_material(mat)


# ---------------------------------------------------------------------------
# GET /content/weekly-feed
# ---------------------------------------------------------------------------

@router.get("/weekly-feed")
def weekly_feed(
    conditions:  str  = Query(..., description="Comma-separated condition groups, e.g. T2DM,HTN"),
    week_number: Optional[int] = Query(None, description="ISO week (default: current week)"),
    is_active:   bool = Query(True, description="Only return approved materials"),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """
    Return this week's E, K, and A materials for the given condition groups.

    Designed for clients to build patient-facing content cards / visuals.
    One E + one K + one A per matching condition group.

    Example:
        GET /content/weekly-feed?conditions=T2DM,Cardiac
    """
    groups = [g.strip() for g in conditions.split(",") if g.strip()]
    if not groups:
        raise HTTPException(status_code=400, detail="At least one condition group required")

    return {"conditions": groups, **_feed(database, groups, week_number, is_active)}


def _feed(database, groups, week_number, is_active, personalization_level=None, onboarding_stage=None) -> dict:
    """E/K/A feed for these groups. With no explicit week and nothing approved
    for the current ISO week, serves the latest approved week instead
    (expiry ignored) so app clients keep getting reviewed content while newer
    weeks wait for review; `fallback_from_week` says when that happened."""
    week = week_number or date.today().isocalendar()[1]
    fallback_from = None
    if week_number is None and is_active:
        M = db.ContentMaterial
        if not database.query(M.id).filter(M.week_number == week, M.is_active.is_(True)).first():
            # ponytail: max(week_number) has no year, so at the Jan rollover week 52
            # beats week 1; add a year column if content spans years.
            latest = database.query(func.max(M.week_number)).filter(M.is_active.is_(True)).scalar()
            if latest:
                fallback_from, week = week, latest

    materials = db.get_weekly_feed_for_conditions(
        database,
        condition_groups=groups,
        week_number=week,
        is_active=is_active,
        personalization_level=personalization_level,
        onboarding_stage=onboarding_stage,
        include_expired=fallback_from is not None,
    )
    feed: dict[str, list] = {"E": [], "K": [], "A": []}
    for mat in materials:
        if mat.content_type in feed:
            feed[mat.content_type].append(_serialize_material(mat))
    return {
        "week_number":        week,
        "fallback_from_week": fallback_from,
        "is_active":          is_active,
        "feed":               feed,
        "total":              sum(len(v) for v in feed.values()),
    }


# ---------------------------------------------------------------------------
# GET /content/patient-feed?phone_number=...  (My Heart Coach app users)
# ---------------------------------------------------------------------------

@router.get("/patient-feed")
def myheart_patient_feed(
    phone_number: str = Query(..., description="My Heart Coach app user's phone, e.g. +60173362070"),
    week_number:  Optional[int] = Query(None, description="ISO week (default: current, else latest approved)"),
    is_active:    bool = Query(True),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """E/K/A feed for a My Heart Coach app user, matched on the conditions and
    level read live from the MHC staging DB (same lookup as chat). MHC key only."""
    import myheart_db
    from website_chat_router import _MYHEART_CLIENT_ID
    from scripts.generate_content import conditions_to_groups  # type: ignore

    if client.id != _MYHEART_CLIENT_ID:
        raise HTTPException(status_code=403, detail="Phone lookup is only available to the My Heart Coach account")
    phone = db.normalise_phone_number(phone_number)
    profile = myheart_db.get_myheart_profile(phone)
    if not profile:
        raise HTTPException(status_code=404, detail="No My Heart Coach user with this phone number")

    groups = conditions_to_groups(profile["condition"])
    level, stage = profile["personalization_level"], profile["onboarding_stage"]
    return {
        "phone_number":     phone,
        "patient_name":     profile["name"],
        "condition_groups": groups,
        "personalization_level": level,
        "onboarding_stage": stage,
        **_feed(database, groups, week_number, is_active, level, stage),
    }


# ---------------------------------------------------------------------------
# GET /content/patient-feed/{patient_id}
# ---------------------------------------------------------------------------

@router.get("/patient-feed/{patient_id}")
def patient_feed(
    patient_id:  int,
    week_number: Optional[int] = Query(None, description="ISO week (default: current week)"),
    is_active:   bool = Query(True),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """
    Return this week's E/K/A feed matched to a specific patient's conditions.

    Looks up the patient's condition list, maps to condition groups, and returns
    the matched weekly materials.
    """
    patient = db.get_patient(database, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.client_id != client.id:
        raise HTTPException(status_code=403, detail="Patient not in your account")

    from scripts.generate_content import conditions_to_groups  # type: ignore
    groups = conditions_to_groups(patient.conditions or [])

    # personalization_level: dietitian-set value wins; falls back to the My
    # Heart Coach staging DB's users.risk_level when unset (same helper the
    # chat prompt path uses — see database.get_effective_personalization_level).
    # personalization_level wins over onboarding_stage once a patient is
    # risk-stratified, same precedence as taxonomy.resolve_active_role().
    personalization_level = db.get_effective_personalization_level(patient)
    onboarding_stage = db.get_effective_onboarding_stage(patient)
    return {
        "patient_id":        patient_id,
        "patient_name":      patient.name,
        "condition_groups":  groups,
        "personalization_level": personalization_level,
        "onboarding_stage": onboarding_stage,
        **_feed(database, groups, week_number, is_active, personalization_level, onboarding_stage),
    }


# ---------------------------------------------------------------------------
# POST /content/materials/{id}/approve
# ---------------------------------------------------------------------------

@router.post("/materials/{material_id}/approve")
def approve_material(
    material_id: int,
    x_admin_password: str = Header(..., alias="X-Admin-Password"),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """
    Mark a content material as approved (is_active=True).

    Requires X-Admin-Password header in addition to X-API-Key.
    Once approved, the material appears in weekly-feed responses.
    """
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")

    mat = database.query(db.ContentMaterial).filter(db.ContentMaterial.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")

    mat.is_active = True
    database.commit()
    database.refresh(mat)

    return {
        "status":       "approved",
        "material_id":  mat.id,
        "title":        mat.title,
        "is_active":    mat.is_active,
    }


# ---------------------------------------------------------------------------
# POST /content/materials/{id}/unapprove
# ---------------------------------------------------------------------------

@router.post("/materials/{material_id}/unapprove")
def unapprove_material(
    material_id: int,
    x_admin_password: str = Header(..., alias="X-Admin-Password"),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """Revoke approval for a content material (sets is_active=False)."""
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")

    mat = database.query(db.ContentMaterial).filter(db.ContentMaterial.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")

    mat.is_active = False
    database.commit()
    return {"status": "unapproved", "material_id": mat.id}


# ---------------------------------------------------------------------------
# GET /content/summary  — quick stats for dashboards
# ---------------------------------------------------------------------------

@router.get("/summary")
def content_summary(
    week_number: Optional[int] = Query(None, description="ISO week (default: current week)"),
    database: Session = Depends(get_db),
    client = Depends(get_api_client),
):
    """
    Summary stats for the content library.
    Useful for building admin dashboards or client-facing progress indicators.
    """
    if week_number is None:
        week_number = date.today().isocalendar()[1]

    all_mats = db.get_materials_by_filters(database, week_number=week_number, limit=500)
    eka_mats = [m for m in all_mats if m.content_type is not None]

    by_type = {}
    for ctype in ("E", "K", "A"):
        items = [m for m in eka_mats if m.content_type == ctype]
        by_type[ctype] = {
            "label":    TYPE_LABELS[ctype],
            "total":    len(items),
            "active":   sum(1 for m in items if m.is_active),
            "pending":  sum(1 for m in items if not m.is_active),
        }

    return {
        "week_number":    week_number,
        "current_week":   date.today().isocalendar()[1],
        "total_materials": len(eka_mats),
        "active_materials": sum(1 for m in eka_mats if m.is_active),
        "by_type":        by_type,
        "groups_present": sorted({m.condition_group for m in eka_mats}),
    }
