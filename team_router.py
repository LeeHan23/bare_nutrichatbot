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
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import database as db
from dependencies import get_db, TEAM_COOKIE_NAME

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
        <a class="tool" href="{chat_link}">Try the Chatbot</a>
        <p><a class="logout" href="/team/logout">Sign out</a></p>
    </body>
    </html>
    """)
