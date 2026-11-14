"""
team_router.py — sign in with your existing X-API-Key, once, to reach the
team's internal tools (EKA content review, judge calibration, and a
ready-to-use link into the chatbot) without re-entering a key on every
subdomain.

Mounted at /team on the main nutribot app. The session is a cookie holding
the person's own API key, set with Domain=.computationalrd.com so it's sent
to nutribot., docs-api., and eval.computationalrd.com alike — one sign-in
covers all three. Nobody reaches docs-api's /eka-review or eval's judge
calibration page without it: both redirect here first (see docs_api.py /
eval_api.py).

This is deliberately NOT self-service key creation — a key still has to
come from Han via /admin/create-api-key (password-gated). "Sign up" here
means "register this browser's session using a key you already hold."
"""
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import database as db
from dependencies import get_db, get_team_client_from_cookie, is_team_session, TEAM_COOKIE_NAME
from sentiment import NEGATIVE_STATES

router = APIRouter()

COOKIE_DOMAIN = os.getenv("TEAM_COOKIE_DOMAIN", ".computationalrd.com")
_HUB_PATH = "/team"


def _login_page(error: str = "", next_url: str = "") -> HTMLResponse:
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Nutribot Team Sign-In</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; max-width: 380px; margin: 80px auto; padding: 0 20px; color: #1a1a1a; }}
        h1 {{ font-size: 20px; margin-bottom: 6px; }}
        p.sub {{ color: #666; font-size: 13.5px; margin-top: 0; }}
        input {{ width: 100%; padding: 11px; border: 1.5px solid #ddd; border-radius: 6px; font-size: 14px; box-sizing: border-box; margin-bottom: 14px; }}
        button {{ width: 100%; padding: 12px; background: #146356; color: white; border: none; border-radius: 6px; font-size: 15px; font-weight: 600; cursor: pointer; }}
        .err {{ color: #c0392b; font-size: 13px; margin-bottom: 12px; }}
    </style>
    </head>
    <body>
        <h1>Sign in with your API key</h1>
        <p class="sub">Unlocks EKA Content Review, Judge Calibration, and the chatbot — no key needed again after this.</p>
        {f'<p class="err">{error}</p>' if error else ''}
        <form method="post" action="/team/login">
            <input type="password" name="api_key" placeholder="nbk_live_..." autocomplete="off" required autofocus>
            <input type="hidden" name="next" value="{next_url}">
            <button type="submit">Sign in</button>
        </form>
    </body>
    </html>
    """)


@router.get("/login")
def login_page(next: str = ""):
    return _login_page(next_url=next)


@router.post("/login")
def login_submit(api_key: str = Form(...), next: str = Form(""), database: Session = Depends(get_db)):
    client = db.get_client_by_key(database, api_key.strip())
    if not client:
        return _login_page(error="That API key wasn't recognised.", next_url=next)

    response = RedirectResponse(url=next or _HUB_PATH, status_code=303)
    response.set_cookie(
        key=TEAM_COOKIE_NAME,
        value=api_key.strip(),
        domain=COOKIE_DOMAIN,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/team/login")
    response.delete_cookie(key=TEAM_COOKIE_NAME, domain=COOKIE_DOMAIN)
    return response


@router.get("/whoami")
def whoami(request: Request, database: Session = Depends(get_db)):
    client = db.get_client_by_key(database, request.cookies.get(TEAM_COOKIE_NAME))
    if not client:
        return {"signed_in": False}
    return {"signed_in": True, "name": client.client_name}


@router.get("", response_class=HTMLResponse)
def hub(request: Request, database: Session = Depends(get_db)):
    key = request.cookies.get(TEAM_COOKIE_NAME)
    client = db.get_client_by_key(database, key) if key else None
    if not client:
        return RedirectResponse(url=f"/team/login?next={quote(_HUB_PATH)}")

    chat_link = f"https://nutribot.computationalrd.com/?key={quote(key)}"
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Nutribot Team Hub</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; }}
        h1 {{ font-size: 20px; }}
        a.tool {{ display: block; padding: 14px 18px; margin: 10px 0; background: #f0f7ff;
             border-left: 4px solid #146356; border-radius: 6px; text-decoration: none;
             color: #333; font-weight: 600; }}
        a.tool:hover {{ background: #e4edff; }}
        a.logout {{ font-size: 13px; color: #888; }}
    </style>
    </head>
    <body>
        <h1>Signed in as {client.client_name}</h1>
        <a class="tool" href="https://docs-api.computationalrd.com/eka-review">EKA Content Review</a>
        <a class="tool" href="https://eval.computationalrd.com/">Judge Calibration</a>
        <a class="tool" href="/team/sentiment">Patient Sentiment</a>
        <a class="tool" href="{chat_link}">Try the Chatbot</a>
        <p><a class="logout" href="/team/logout">Sign out</a></p>
    </body>
    </html>
    """)


# ---------------------------------------------------------------------------
# Patient sentiment dashboard (rows written by sentiment.record via rag.py).
# Lives here, not in docs_api/eval_api: both of those promise no patient data.
# ---------------------------------------------------------------------------
_SENTIMENT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sentiment_dashboard.html")


def _row(r: "db.PatientSentiment") -> dict:
    return {
        "id": r.id, "session_id": r.session_id, "patient_id": r.patient_id,
        "created_at": r.created_at.isoformat() + "Z", "valence": r.valence, "state": r.state,
        "intensity": r.intensity, "cues": r.cues, "message": r.message_excerpt,
        "urgent": r.urgent, "source": r.source,
        "acknowledged_at": r.acknowledged_at.isoformat() + "Z" if r.acknowledged_at else None,
        "acknowledged_by": r.acknowledged_by,
    }


@router.get("/sentiment", response_class=HTMLResponse)
def sentiment_page(request: Request, database: Session = Depends(get_db)):
    if not is_team_session(request, database):
        return RedirectResponse(url=f"/team/login?next={quote('/team/sentiment')}")
    with open(_SENTIMENT_HTML, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/sentiment/data", dependencies=[Depends(get_team_client_from_cookie)])
def sentiment_data(days: int = 30, database: Session = Depends(get_db)):
    days = max(1, min(days, 365))
    since = datetime.utcnow() - timedelta(days=days)
    S = db.PatientSentiment
    # Unacknowledged urgent rows are shown whatever their age.
    urgent = (
        database.query(S).filter(S.urgent.is_(True), S.acknowledged_at.is_(None))
        .order_by(S.created_at.desc()).all()
    )
    # ponytail: aggregates in Python over the window; move to SQL GROUP BY
    # if this ever passes ~100k rows.
    rows = database.query(S).filter(S.created_at >= since).order_by(S.created_at).all()

    names = {
        p.id: p.name for p in database.query(db.Patient.id, db.Patient.name)
        .filter(db.Patient.id.in_({r.patient_id for r in rows + urgent if r.patient_id})).all()
    }

    daily = defaultdict(Counter)
    subjects = {}
    for r in rows:
        daily[r.created_at.date().isoformat()][r.state] += 1
        key = f"p{r.patient_id}" if r.patient_id else f"s:{r.session_id}"
        s = subjects.setdefault(key, {
            "key": key, "patient_id": r.patient_id, "name": names.get(r.patient_id),
            "session_id": r.session_id, "turns": 0, "negative": 0, "urgent": 0, "trend": [],
        })
        s["turns"] += 1
        s["negative"] += r.state in NEGATIVE_STATES
        s["urgent"] += bool(r.urgent)
        s["trend"].append(r.state)
        s["latest_state"] = r.state
        s["last_seen"] = r.created_at.isoformat() + "Z"
        s["session_id"] = r.session_id  # most recent session, for the transcript link
    for s in subjects.values():
        s["trend"] = s["trend"][-20:]

    urgent_out = [dict(_row(r), name=names.get(r.patient_id)) for r in urgent]
    return {
        "days": days,
        "total": len(rows),
        "state_counts": dict(Counter(r.state for r in rows)),
        "daily": [{"date": d, **c} for d, c in sorted(daily.items())],
        "subjects": sorted(subjects.values(), key=lambda s: s["last_seen"], reverse=True),
        "urgent": urgent_out,
    }


@router.get("/sentiment/session/{session_id}", dependencies=[Depends(get_team_client_from_cookie)])
def sentiment_session(session_id: str, database: Session = Depends(get_db)):
    msgs = db.get_chat_history(database, session_id, limit=200)
    S = db.PatientSentiment
    labels = database.query(S).filter(S.session_id == session_id).order_by(S.created_at).all()
    return {
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() + "Z"}
            for m in msgs
        ],
        "labels": [_row(r) for r in labels],
    }


@router.post("/sentiment/{row_id}/ack", dependencies=[Depends(get_team_client_from_cookie)])
def sentiment_ack(row_id: int, request: Request, database: Session = Depends(get_db)):
    row = database.get(db.PatientSentiment, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.acknowledged_at = datetime.utcnow()
    row.acknowledged_by = unquote(request.cookies.get("reviewer_name", "")) or "team"
    database.commit()
    return _row(row)
