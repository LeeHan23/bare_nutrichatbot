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


def format_eka_message(content_type: str, patient_first_name: str, title: str,
                        content: dict, week_number: int | None = None,
                        personalization_level: str | None = None) -> str:
    """Format a weekly EKA (Exercise/Knowledge/Activity) material as a WhatsApp message."""
    if not isinstance(content, dict) or content.get("parse_error"):
        return (
            f"*NutriBot — Week {week_number}*\n"
            f"Hi {patient_first_name}! Your *{title}* update is ready, "
            f"but we hit a hiccup formatting it. Our team has been notified."
        )
    if content_type == "E":
        return _format_exercise_message(patient_first_name, title, content, week_number, personalization_level)
    if content_type == "K":
        return _format_knowledge_message(patient_first_name, title, content, week_number)
    if content_type == "A":
        return _format_activity_message(patient_first_name, title, content, week_number)
    raise ValueError(f"Unknown EKA content_type: {content_type!r}")


def _format_exercise_message(patient_first_name: str, title: str, content: dict,
                              week_number: int | None, personalization_level: str | None) -> str:
    lines = [
        f"*NutriBot — Week {week_number} Exercise* 💪",
        f"Hi {patient_first_name}! Here's your exercise plan for this week.",
        f"\n*{title}*",
        f"_{content.get('exercise_type', '')} • {content.get('duration_min', '?')} min "
        f"• {content.get('frequency_per_week', '?')}x/week • {content.get('intensity', '')} intensity_\n",
    ]

    warmup = content.get("warmup") or []
    if warmup:
        lines.append("*Warm-up:*")
        lines.extend(f"- {step}" for step in warmup)

    main = content.get("main_activity") or []
    if main:
        lines.append("\n*Main activity:*")
        lines.extend(f"- {step}" for step in main)

    cooldown = content.get("cooldown") or []
    if cooldown:
        lines.append("\n*Cool-down:*")
        lines.extend(f"- {step}" for step in cooldown)

    level_mods = content.get("level_modifications") or {}
    if personalization_level and level_mods.get(personalization_level):
        lines.append(f"\n_For you:_ {level_mods[personalization_level]}")

    stop_signs = content.get("safety_stop_signs") or []
    if stop_signs:
        lines.append("\n⚠️ *Stop and rest if you feel:* " + ", ".join(stop_signs))

    if content.get("malaysian_context"):
        lines.append(f"\n🇲🇾 {content['malaysian_context']}")

    lines.append("\n_Reply STOP to unsubscribe from weekly content._")
    return "\n".join(lines)


def _format_knowledge_message(patient_first_name: str, title: str, content: dict,
                               week_number: int | None) -> str:
    lines = [
        f"*NutriBot — Week {week_number} Knowledge* 📚",
        f"Hi {patient_first_name}! This week's health topic:",
        f"\n*{title}*",
    ]
    if content.get("topic_summary"):
        lines.append(f"_{content['topic_summary']}_\n")

    for i, lp in enumerate(content.get("learning_points") or [], start=1):
        lines.append(f"{i}. *{lp.get('point', '')}* — {lp.get('explanation', '')}")
        if lp.get("why_it_matters"):
            lines.append(f"   _Why it matters:_ {lp['why_it_matters']}")

    if content.get("key_takeaway"):
        lines.append(f"\n💡 *Key takeaway:* {content['key_takeaway']}")
    if content.get("local_context"):
        lines.append(f"🇲🇾 {content['local_context']}")

    lines.append("\n_Reply STOP to unsubscribe from weekly content._")
    return "\n".join(lines)


def _format_activity_message(patient_first_name: str, title: str, content: dict,
                              week_number: int | None) -> str:
    lines = [
        f"*NutriBot — Week {week_number} Activity* 🎯",
        f"Hi {patient_first_name}! Your activity challenge this week:",
        f"\n*{title}*: {content.get('task_name', '')}",
    ]
    if content.get("description"):
        lines.append(content["description"])

    instructions = content.get("instructions") or []
    if instructions:
        lines.append("\n*How to do it:*")
        lines.extend(f"{i}. {step}" for i, step in enumerate(instructions, start=1))

    if content.get("weekly_goal"):
        lines.append(f"\n*This week's goal:* {content['weekly_goal']}")

    micro_actions = content.get("micro_actions") or []
    if micro_actions:
        lines.append("\n*Daily plan:*")
        lines.extend(f"- {step}" for step in micro_actions)

    if content.get("tracking_method"):
        lines.append(f"\n📝 Track via: {content['tracking_method']}")
    if content.get("success_looks_like"):
        lines.append(f"✅ Success looks like: {content['success_looks_like']}")

    lines.append("\n_Reply STOP to unsubscribe from weekly content._")
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
