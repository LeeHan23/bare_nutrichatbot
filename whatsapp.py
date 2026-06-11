"""
WhatsApp delivery for NutriBot content drip.

Provider is selected via WHATSAPP_PROVIDER env var (default: twilio).

Twilio setup:
  TWILIO_ACCOUNT_SID=...
  TWILIO_AUTH_TOKEN=...
  TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   (sandbox number or approved sender)

Meta Cloud API setup:
  META_WHATSAPP_TOKEN=...
  META_WHATSAPP_PHONE_ID=...
"""
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("WHATSAPP_PROVIDER", "twilio").lower()


def send_message(to_phone: str, body: str, media_url: str | None = None) -> dict:
    """
    Send a WhatsApp message to a phone number.
    Returns {"success": bool, "sid"/"message_id": ..., "error": ...}
    """
    if not to_phone:
        return {"success": False, "error": "No phone number provided for patient."}
    if PROVIDER == "twilio":
        return _send_twilio(to_phone, body, media_url)
    if PROVIDER == "meta":
        return _send_meta(to_phone, body, media_url)
    return {"success": False, "error": f"Unknown WHATSAPP_PROVIDER: {PROVIDER}"}


def format_tips_message(patient_first_name: str, title: str, tips: list, day_offset: int) -> str:
    """Format content tips as a WhatsApp-friendly message (supports * bold, _ italic)."""
    lines = [
        f"*NutriBot — Day {day_offset}*",
        f"Hi {patient_first_name}! Here are your nutrition tips for today 🌿",
        f"\n*{title}*\n",
    ]
    for t in tips:
        num = t.get("tip_number", "")
        text = t.get("tip", "")
        lines.append(f"{num}. {text}")
    lines.append("\n_Reply STOP to unsubscribe from daily tips._")
    return "\n".join(lines)


def _send_twilio(to_phone: str, body: str, media_url: str | None) -> dict:
    try:
        from twilio.rest import Client
    except ImportError:
        return {"success": False, "error": "twilio package not installed — run: pip install twilio"}

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_wa = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not sid or not token:
        return {"success": False, "error": "TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN not set in .env"}

    to_wa = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"

    try:
        client = Client(sid, token)
        kwargs = {"body": body, "from_": from_wa, "to": to_wa}
        if media_url:
            kwargs["media_url"] = [media_url]
        msg = client.messages.create(**kwargs)
        return {"success": True, "sid": msg.sid, "status": msg.status}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _send_meta(to_phone: str, body: str, media_url: str | None) -> dict:
    import requests

    token = os.getenv("META_WHATSAPP_TOKEN")
    phone_id = os.getenv("META_WHATSAPP_PHONE_ID")

    if not token or not phone_id:
        return {"success": False, "error": "META_WHATSAPP_TOKEN or META_WHATSAPP_PHONE_ID not set"}

    # Normalise: strip whatsapp: prefix, +, spaces
    to_clean = to_phone.replace("whatsapp:", "").replace("+", "").replace(" ", "")

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "text",
        "text": {"body": body},
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        data = resp.json()
        if resp.ok:
            msg_id = data.get("messages", [{}])[0].get("id")
            return {"success": True, "message_id": msg_id}
        return {"success": False, "error": data.get("error", {}).get("message", resp.text)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
