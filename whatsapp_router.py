"""
whatsapp_router.py — Inbound WhatsApp webhooks (Twilio + Meta Cloud API).

Both providers resolve the sender's phone number to a Patient via
database.get_patient_by_phone(), then run the question through the same
RAG pipeline used by the website chat (rag.get_rag_response), persisted
under session_id=f"whatsapp-{patient_id}" so history (item #4) carries over.

RAG calls take 10-90s, far longer than Twilio/Meta's webhook timeouts, so the
reply is generated in a BackgroundTask and sent back out via whatsapp.send_message().

STOP / START handling sets/clears Patient.whatsapp_opted_out, which gates
scheduled content delivery (_send_patient_content in mcp_server.py) — it does
NOT block direct conversational replies.
"""
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

import database as db
import rag
import whatsapp as wa
from extractor import extract_from_message
from local_patient_store import LocalPatientStore

logger = logging.getLogger(__name__)

whatsapp_router = APIRouter()

STOP_KEYWORDS = {"stop", "unsubscribe", "berhenti"}
START_KEYWORDS = {"start", "subscribe", "mula"}

# WhatsApp text messages are capped at 1600 chars (Twilio) / 4096 (Meta) — stay
# well under both so the reply is never silently dropped by the provider.
MAX_REPLY_CHARS = 1500


def _request_url(request: Request) -> str:
    """Reconstruct the public URL, honouring the Cloudflare tunnel's forwarded headers."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{proto}://{host}{request.url.path}"


def _twilio_signature_valid(request: Request, form: dict) -> bool:
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        logger.warning("[WhatsApp] TWILIO_AUTH_TOKEN not set — skipping signature validation")
        return True

    from twilio.request_validator import RequestValidator

    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(token)
    return validator.validate(_request_url(request), form, signature)


@whatsapp_router.post("/whatsapp")
async def twilio_webhook(request: Request, background_tasks: BackgroundTasks):
    """Twilio inbound WhatsApp webhook — form-encoded POST."""
    form = await request.form()
    form_dict = dict(form)

    if not _twilio_signature_valid(request, form_dict):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    from_phone = form_dict.get("From", "")
    body_text = (form_dict.get("Body") or "").strip()

    await _handle_incoming(from_phone, body_text, background_tasks)

    # Empty TwiML — the actual reply is sent asynchronously via the REST API.
    return Response(content="<Response></Response>", media_type="application/xml")


@whatsapp_router.get("/whatsapp/meta")
async def meta_verify(request: Request):
    """Meta Cloud API webhook verification handshake."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    expected_token = os.getenv("META_VERIFY_TOKEN")
    if mode == "subscribe" and expected_token and token == expected_token:
        return PlainTextResponse(content=challenge or "")
    raise HTTPException(status_code=403, detail="Verification failed")


@whatsapp_router.post("/whatsapp/meta")
async def meta_webhook(request: Request, background_tasks: BackgroundTasks):
    """Meta Cloud API inbound webhook — JSON POST."""
    payload = await request.json()
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            # Delivery/read status update, not a message — acknowledge and ignore.
            return {"status": "ok"}
        message = messages[0]
        from_phone = message.get("from", "")
        body_text = (message.get("text", {}) or {}).get("body", "").strip()
    except (KeyError, IndexError):
        return {"status": "ignored"}

    await _handle_incoming(from_phone, body_text, background_tasks)
    return {"status": "ok"}


async def _handle_incoming(from_phone: str, body_text: str, background_tasks: BackgroundTasks):
    """Shared logic: resolve patient, handle STOP/START, queue the RAG reply."""
    if not from_phone or not body_text:
        return

    session = db.SessionLocal()
    try:
        patient = db.get_patient_by_phone(session, from_phone)
        if not patient:
            logger.info(f"[WhatsApp] Message from unrecognised phone {from_phone!r}: {body_text!r}")
            wa.send_message(
                to_phone=from_phone,
                body="Sorry, we don't recognise this phone number. Please contact your clinic "
                     "to link your WhatsApp number to your NutriBot profile.",
            )
            return

        lowered = body_text.strip().lower()
        if lowered in STOP_KEYWORDS:
            patient.whatsapp_opted_out = True
            session.commit()
            wa.send_message(
                to_phone=patient.phone_number,
                body="You've been unsubscribed from NutriBot WhatsApp content updates. "
                     "Reply START to resubscribe. You can still chat with NutriBot anytime.",
            )
            return

        if lowered in START_KEYWORDS:
            patient.whatsapp_opted_out = False
            session.commit()
            wa.send_message(
                to_phone=patient.phone_number,
                body="You're resubscribed to NutriBot WhatsApp content updates. "
                     "How can I help with your nutrition today?",
            )
            return

        background_tasks.add_task(
            _process_and_reply,
            patient_id=patient.id,
            client_id=patient.client_id,
            question=body_text,
            to_phone=patient.phone_number,
        )
    finally:
        session.close()


def _process_and_reply(patient_id: int, client_id: int, question: str, to_phone: str):
    """Background task: run RAG, persist history, run extractor, send WhatsApp reply."""
    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            return

        profile = db.patient_to_profile_dict(patient)
        session_id = f"whatsapp-{patient_id}"

        db.set_first_chat_at(session, patient_id)

        response = rag.get_rag_response(
            question=question,
            client_id=client_id,
            chat_session_id=session_id,
            profile=profile,
            is_patient_self=True,
            patient_id=patient_id,
        )
        answer = response.get("answer", "")
        if len(answer) > MAX_REPLY_CHARS:
            answer = answer[:MAX_REPLY_CHARS - 1].rstrip() + "…"

        wa_result = wa.send_message(to_phone=to_phone, body=answer)
        if not wa_result.get("success"):
            logger.error(f"[WhatsApp] Failed to send reply to patient {patient_id}: {wa_result.get('error')}")

        # Best-effort profile extraction, mirrors website_chat_router's background task.
        try:
            new_fields = extract_from_message(question, profile)
            if new_fields:
                LocalPatientStore().update_supplementary_fields(
                    patient_id=patient_id,
                    updates=new_fields,
                    source_session_id=session_id,
                )
        except Exception as e:
            logger.error(f"[WhatsApp] Extractor failed for patient {patient_id}: {e}")
    except Exception as e:
        logger.error(f"[WhatsApp] _process_and_reply failed for patient {patient_id}: {e}")
        try:
            wa.send_message(
                to_phone=to_phone,
                body="Sorry, something went wrong processing your message. Please try again shortly.",
            )
        except Exception:
            pass
    finally:
        session.close()
