"""Standalone document-QA API — no patient/client/chat-history mock database dependency.

Reuses the existing PGVector document store (base_knowledge collection, same
Postgres instance as the main bot) and the CLaRa-compress -> Qwen-generate
pipeline from llm.py, but never touches patients/clients/chat_messages. For
another application that just wants grounded nutrition Q&A over the document
corpus, with no patient profile or personalization.

Run standalone: .venv/bin/python -m uvicorn docs_api:app --host 0.0.0.0 --port 8100
"""

import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.orm import Session

from llm import call_clara_compress, call_ollama_generate
from vector_store import get_retriever

app = FastAPI(title="Nutribot Docs API")

DOCS_API_KEY = os.getenv("DOCS_API_KEY")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Depends(_api_key_header)) -> None:
    if DOCS_API_KEY and api_key != DOCS_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


class AskRequest(BaseModel):
    question: str


@app.post("/ask", dependencies=[Depends(verify_api_key)])
def ask(request: AskRequest) -> dict:
    # "0" = no per-client collection; only base_knowledge (24k+ ingested chunks) is searched.
    retriever = get_retriever("0")
    doc_texts = [doc.page_content for doc in retriever.invoke(request.question)]

    digest = call_clara_compress(doc_texts, request.question)
    if not digest:
        digest = "Clinical context from guidelines:\n\n" + "\n\n---\n\n".join(doc_texts)

    prompt = (
        "You are NutriBot, a clinical nutrition assistant for Malaysian cardiac patients.\n"
        f"\n## Clinical Evidence Digest\n{digest}\n"
        "\n## Instructions\nAnswer using only the evidence above. Be concise and practical.\n"
        f"\n## Question\n{request.question}\n\n## Answer"
    )

    answer = call_ollama_generate(prompt)
    if not answer:
        raise HTTPException(status_code=502, detail="Generation failed — backend unavailable")

    return {"answer": answer}


# ---------------------------------------------------------------------------
# EKA content review page — added 2026-08-14 alongside the weekly EKA
# generator's restoration (scripts/generate_weekly_eka.py). Unlike the rest
# of this file, these routes DO touch database.py/content_materials —
# ContentMaterial has no patient/client_id on it (it's generic draft content,
# not patient data), so it doesn't compromise this service's "no patient
# data" boundary the way importing Patient rows would.
#
# Approve/unapprove/edit added 2026-08-14 so non-technical reviewers don't
# need to run POST commands themselves. This duplicates the is_active toggle
# content_api_router.py's /materials/{id}/approve already does on the main
# app — deliberately: that endpoint is gated by X-Admin-Password + a tenant
# X-API-Key (get_api_client), a heavier auth model than fits "anyone on the
# team with this link." These reuse the same simple DOCS_API_KEY as the rest
# of this file instead. Since that key is shared (not per-person), there's
# no real user identity to attribute writes to — _log_review_action() below
# writes a plain-text audit line per action (reviewer name is client-supplied,
# not verified) as a lightweight trail, not a substitute for real auth.
# https://docs-api.computationalrd.com/eka-review
# ---------------------------------------------------------------------------

_EKA_REVIEW_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eka_review.html")
_REVIEW_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "eka_review_actions.log")


@app.get("/eka-review", response_class=HTMLResponse)
def eka_review_page():
    with open(_EKA_REVIEW_HTML_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/eka-review/data", dependencies=[Depends(verify_api_key)])
def eka_review_data(
    week_number: Optional[int] = None,
    content_type: Optional[str] = None,
    condition_group: Optional[str] = None,
    include_expired: bool = False,
):
    import database as db
    from content_api_router import _serialize_material

    session: Session = db.SessionLocal()
    try:
        materials = db.get_materials_by_filters(
            session,
            content_type=content_type,
            week_number=week_number,
            condition_group=condition_group,
            is_active=None,
            include_expired=include_expired,
            limit=500,
            offset=0,
        )
        return {"materials": [_serialize_material(m) for m in materials]}
    finally:
        session.close()


def _log_review_action(action: str, material_id: int, reviewer: Optional[str]) -> None:
    from datetime import datetime

    os.makedirs(os.path.dirname(_REVIEW_LOG_PATH), exist_ok=True)
    line = f"{datetime.utcnow().isoformat()}Z\t{action}\tmaterial_id={material_id}\treviewer={reviewer or 'unknown'}\n"
    with open(_REVIEW_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def _get_material_or_404(session, material_id: int):
    import database as db

    mat = session.query(db.ContentMaterial).filter(db.ContentMaterial.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    return mat


class ReviewActionRequest(BaseModel):
    reviewer: Optional[str] = None


@app.post("/eka-review/materials/{material_id}/approve", dependencies=[Depends(verify_api_key)])
def eka_review_approve(material_id: int, request: ReviewActionRequest):
    import database as db
    from content_api_router import _serialize_material

    session: Session = db.SessionLocal()
    try:
        mat = _get_material_or_404(session, material_id)
        mat.is_active = True
        session.commit()
        session.refresh(mat)
        _log_review_action("approve", material_id, request.reviewer)
        return _serialize_material(mat)
    finally:
        session.close()


@app.post("/eka-review/materials/{material_id}/unapprove", dependencies=[Depends(verify_api_key)])
def eka_review_unapprove(material_id: int, request: ReviewActionRequest):
    import database as db
    from content_api_router import _serialize_material

    session: Session = db.SessionLocal()
    try:
        mat = _get_material_or_404(session, material_id)
        mat.is_active = False
        session.commit()
        session.refresh(mat)
        _log_review_action("unapprove", material_id, request.reviewer)
        return _serialize_material(mat)
    finally:
        session.close()


class ContentEditRequest(BaseModel):
    content: dict
    title: Optional[str] = None
    reviewer: Optional[str] = None


@app.post("/eka-review/materials/{material_id}/content", dependencies=[Depends(verify_api_key)])
def eka_review_edit_content(material_id: int, request: ContentEditRequest):
    import database as db
    from content_api_router import _serialize_material

    session: Session = db.SessionLocal()
    try:
        mat = _get_material_or_404(session, material_id)
        mat.raw_tips = request.content
        if request.title:
            mat.title = request.title
        session.commit()
        session.refresh(mat)
        _log_review_action("edit", material_id, request.reviewer)
        return _serialize_material(mat)
    finally:
        session.close()
