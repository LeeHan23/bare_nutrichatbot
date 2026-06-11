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
  POST /content/generate-weekly     — trigger generation for current week (admin)
"""
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header, BackgroundTasks
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
        "week_number":      mat.week_number,
        "day_offset":       mat.day_offset,
        "topic":            mat.topic,
        "title":            mat.title,
        "is_active":        mat.is_active,
        "content":          mat.raw_tips,
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
    condition_group: Optional[str] = Query(None, description="T2DM | HTN | CKD | Cardiac | PCOS | Dyslipidaemia | General"),
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
    if week_number is None:
        week_number = date.today().isocalendar()[1]

    groups = [g.strip() for g in conditions.split(",") if g.strip()]
    if not groups:
        raise HTTPException(status_code=400, detail="At least one condition group required")

    materials = db.get_weekly_feed_for_conditions(
        database, condition_groups=groups, week_number=week_number, is_active=is_active
    )

    feed: dict[str, list] = {"E": [], "K": [], "A": []}
    for mat in materials:
        if mat.content_type in feed:
            feed[mat.content_type].append(_serialize_material(mat))

    return {
        "week_number": week_number,
        "conditions":  groups,
        "is_active":   is_active,
        "feed":        feed,
        "total":       sum(len(v) for v in feed.values()),
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
    if week_number is None:
        week_number = date.today().isocalendar()[1]

    patient = db.get_patient(database, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.client_id != client.id:
        raise HTTPException(status_code=403, detail="Patient not in your account")

    from scripts.generate_content import conditions_to_groups  # type: ignore
    groups = conditions_to_groups(patient.conditions or [])

    materials = db.get_weekly_feed_for_conditions(
        database, condition_groups=groups, week_number=week_number, is_active=is_active
    )

    feed: dict[str, list] = {"E": [], "K": [], "A": []}
    for mat in materials:
        if mat.content_type in feed:
            feed[mat.content_type].append(_serialize_material(mat))

    return {
        "week_number":       week_number,
        "patient_id":        patient_id,
        "patient_name":      patient.name,
        "condition_groups":  groups,
        "personalization_level": patient.personalization_level,
        "is_active":         is_active,
        "feed":              feed,
        "total":             sum(len(v) for v in feed.values()),
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
# POST /content/generate-weekly  (admin — triggers background generation)
# ---------------------------------------------------------------------------

@router.post("/generate-weekly")
def trigger_weekly_generation(
    x_admin_password: str = Header(..., alias="X-Admin-Password"),
    week_number: Optional[int] = Query(None, description="ISO week (default: current week)"),
    force:       bool = Query(False, description="Overwrite existing rows"),
    dry_run:     bool = Query(False),
    group:       Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    client = Depends(get_api_client),
):
    """
    Trigger weekly E/K/A content generation for the current (or specified) week.

    Runs in the background — returns immediately with a job description.
    Requires X-Admin-Password header.

    Results appear in /content/materials (is_active=False) within ~30-60 min
    depending on Ollama throughput.
    """
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")

    if week_number is None:
        week_number = date.today().isocalendar()[1]

    def _run():
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from scripts.generate_weekly_eka import generate_weekly_eka  # type: ignore
        generate_weekly_eka(
            iso_week=week_number,
            filter_group=group,
            filter_type=content_type,
            dry_run=dry_run,
            force=force,
        )

    background_tasks.add_task(_run)

    return {
        "status":      "started",
        "week_number": week_number,
        "dry_run":     dry_run,
        "force":       force,
        "group":       group,
        "content_type": content_type,
        "message":     "Generation running in background. Check /content/materials to see results.",
    }


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
