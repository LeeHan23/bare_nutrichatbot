"""
sentiment.py — passive patient sentiment: classify each patient turn,
adapt the reply's tone, and log a row for the team dashboard
(/team/sentiment, team_router.py).

The bot never asks "how are you feeling?". The state is read from how the
patient writes, with the last few patient lines as context.

Two layers:
  1. CRISIS_PATTERN — deterministic bilingual regex. A match short-circuits
     the turn with the fixed CRISIS_RESPONSE (rag.get_rag_response), same
     idea as the cardiac RED_FLAG_PATTERN in website_chat_router.py.
  2. classify() — one Ollama call per turn, run alongside retrieval.
     Its label picks a TONE_GUIDANCE block for the prompt.

HARD RULE (user requirement, 2026-11-04): the bot never contacts emergency
services or anyone else. Nothing here dials, texts, emails or calls any
outside service. A crisis/distress turn only writes an internal
patient_sentiment row with urgent=True, which the team sees on the
dashboard. Replies give the patient numbers *they* can choose to call and
must never claim the bot has alerted anyone — see ACTION_CLAIMS and the
__main__ self-check.

Run `python sentiment.py` for the self-check (no network, no DB).
"""
import json
import os
import re
from datetime import datetime

import requests
from dotenv import load_dotenv

from extractor import _strip_json_response

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
SENTIMENT_MODEL = os.getenv("SENTIMENT_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5:32b"))
SENTIMENT_TIMEOUT_S = float(os.getenv("SENTIMENT_TIMEOUT_S", "8"))

STATES = (
    "motivated", "anxious", "frustrated", "low_mood",
    "confused", "disengaged", "distress", "neutral",
)
VALENCES = ("positive", "neutral", "negative")
NEGATIVE_STATES = {"anxious", "frustrated", "low_mood", "disengaged", "distress"}

# Sessions that are not real patients: the Cloudflare keepalive cron and
# eval/test_rag.py runs (session_id "eval-<case>-<ts>").
def is_untracked_session(session_id: str | None) -> bool:
    return not session_id or session_id == "keepalive" or session_id.startswith("eval-")


# ---------------------------------------------------------------------------
# 1. Crisis layer (deterministic)
# ---------------------------------------------------------------------------
# ponytail: keyword regex, misses indirect phrasing ("what's the point of
# anything"). The LLM "distress" label below is the second net for those.
CRISIS_PATTERN = re.compile(
    r"\b("
    # English
    r"suicid\w*|kill(?:ing)?\s+myself|end(?:ing)?\s+(?:my|it)\s+(?:own\s+)?life|"
    r"take\s+my\s+(?:own\s+)?life|self[\s-]?harm\w*|hurt(?:ing)?\s+myself|"
    r"(?:want|wanted|wanna)\s+(?:to\s+)?die|better\s+off\s+dead|no\s+reason\s+to\s+live|"
    r"(?:don'?t|do\s+not)\s+want\s+to\s+(?:live|be\s+alive)|"
    r"(?:i'?m|i\s+am|i'?ve\s+been)\s+no\s+good\s+to\s+(?:anyone|anybody)|"  # eval sign-off item 2, 2026-11-04
    # Bahasa Malaysia
    r"bunuh\s+diri|(?:nak|mahu|mau|ingin|teringin)\s+mati|"
    r"(?:tak|tidak|x)\s+(?:nak|mahu|mau|ingin)\s+hidup|"
    r"(?:cederakan|sakitkan|lukakan)\s+diri|lebih\s+baik\s+(?:saya|aku)\s+mati|"
    r"tak\s+guna\s+(?:saya\s+|aku\s+)?hidup|"
    r"(?:saya|aku)\s+(?:dah\s+|sudah\s+)?(?:tak|tidak)\s+berguna\s+(?:kepada|pada|untuk)\s+sesiapa"  # BM of the line above
    r")\b",
    re.IGNORECASE,
)

# Helpline numbers — CLINICAL TEAM TO VERIFY BEFORE GO-LIVE.
# Befrienders KL: 03-7627 2929 (24h). Talian HEAL (KKM): 15555.
CRISIS_RESPONSE = (
    "I'm really sorry things feel this heavy right now. You don't have to carry this alone, "
    "and talking to someone today can help.\n\n"
    "• Befrienders KL (24 hours): 03-7627 2929\n"
    "• Talian HEAL (Ministry of Health): 15555\n"
    "• If you are in immediate danger, please call 999 or go to the nearest Emergency Department.\n\n"
    "Please also tell your care team or someone you trust how you are feeling.\n\n"
    "---\n"
    "Saya sangat bersimpati, keadaan ini tentu terasa berat. Anda tidak perlu menanggungnya seorang diri, "
    "dan bercakap dengan seseorang hari ini boleh membantu.\n\n"
    "• Befrienders KL (24 jam): 03-7627 2929\n"
    "• Talian HEAL (KKM): 15555\n"
    "• Jika anda dalam bahaya segera, sila hubungi 999 atau pergi ke Jabatan Kecemasan terdekat.\n\n"
    "Sila beritahu pasukan penjagaan anda atau orang yang anda percayai tentang perasaan anda."
)

# Phrases that would mean the bot claims to have acted on the patient's
# behalf. Must never appear in a crisis/distress reply (hard rule above).
ACTION_CLAIMS = (
    "i have contacted", "i've contacted", "i have alerted", "i've alerted",
    "i have called", "i've called", "i will call", "i'll call", "i am calling",
    "i have informed", "i've informed", "i have notified", "i've notified",
    "i'll notify", "i will notify", "i'll alert", "i will alert",
    "help is on the way", "someone will contact you", "i've let your",
    "saya telah menghubungi", "saya sudah menghubungi", "saya akan menghubungi",
    "saya telah memaklumkan", "saya sudah memaklumkan", "saya akan memaklumkan",
    "bantuan sedang dalam perjalanan",
)


def is_crisis(text: str) -> bool:
    return bool(CRISIS_PATTERN.search(text or ""))


def claims_action(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in ACTION_CLAIMS)


# ---------------------------------------------------------------------------
# 2. LLM classifier
# ---------------------------------------------------------------------------
CLASSIFY_PROMPT = """You read a cardiac patient's chat messages to a diet-and-heart-health coach and judge, quietly, how the patient is doing emotionally. Messages may be English, Bahasa Malaysia or Manglish. Judge from HOW they write (word choice, effort, resignation, worry, sarcasm, short or dismissive replies), not only from feeling words. A plain factual question with no emotional signal is "neutral".

States:
- motivated: keen, hopeful, proud of progress, wants to do more
- anxious: worried or scared about their health, food, results, or doing it wrong
- frustrated: annoyed, fed up, finds the rules hard or unfair, sarcastic
- low_mood: sad, tired of it all, discouraged, lonely, but not in danger
- confused: does not understand advice, mixed up, asks for the same thing again
- disengaged: minimal effort, "ok", "whatever", stopped trying, giving up on the plan
- distress: hopeless, despair, giving up on treatment or life, says nothing matters, feels like a burden to others or that nobody cares about them
- neutral: no clear emotional signal

A short or casual food question ("can or not eat...", "is X ok", "boleh tak") is neutral. Manglish or informal grammar is NOT a sign of confusion or disengagement. "disengaged" is for dismissive replies to the coach, not for brief questions.

Earlier patient messages (oldest first, may be empty):
{history}

Latest patient message:
{message}

Reply with JSON only, no other text:
{{"valence": "positive|neutral|negative", "state": "<one state>", "intensity": 1-3, "cues": "<the words that show it, max 12 words>"}}"""


def _patient_lines(history_text: str, n: int = 4) -> str:
    lines = [l[len("Patient: "):] for l in (history_text or "").splitlines() if l.startswith("Patient: ")]
    return "\n".join(f"- {l[:300]}" for l in lines[-n:]) or "(none)"


def parse_classification(raw: str) -> dict | None:
    """Parse and validate the model's JSON. Anything off → None."""
    try:
        data = json.loads(_strip_json_response(raw))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    state = str(data.get("state", "")).strip().lower()
    valence = str(data.get("valence", "")).strip().lower()
    if state not in STATES or valence not in VALENCES:
        return None
    try:
        intensity = min(3, max(1, int(data.get("intensity", 1))))
    except (ValueError, TypeError):
        intensity = 1
    cues = " ".join(str(data.get("cues", "")).split()[:12])
    return {"valence": valence, "state": state, "intensity": intensity, "cues": cues}


def classify(message: str, history_text: str = "") -> dict | None:
    """One Ollama call. Never raises: any failure returns None and the turn
    goes ahead with no tone adjustment."""
    prompt = CLASSIFY_PROMPT.format(history=_patient_lines(history_text), message=message[:1000])
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": SENTIMENT_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": -1,
                "options": {"temperature": 0.0, "num_predict": 80},
            },
            timeout=SENTIMENT_TIMEOUT_S,
        )
        resp.raise_for_status()
        return parse_classification(resp.json().get("response", ""))
    except Exception as e:
        print(f"[Sentiment] classify failed: {e}")
        return None


# ---------------------------------------------------------------------------
# 3. Tone adaptation
# ---------------------------------------------------------------------------
_TONE_RULE = (
    "Adjust tone only; clinical content and every safety rule above stay the same. "
    "Do NOT name or label the patient's feelings, do NOT say things like "
    "'I sense you are…' or 'it sounds like you feel…', and do NOT ask how they are feeling. "
    "That includes emotion words about the patient anywhere in the reply (worry, worried, concern, "
    "stress, upset, frustration, sad, scared, risau, takut, sedih): say what the step makes easier "
    "('so meals are simpler to plan'), not what it does to their feelings ('to ease your worry')."
)

TONE_GUIDANCE = {
    "motivated": "The patient sounds keen. Briefly affirm the effort in a few words, then give the advice and one clear next step.",
    "anxious": "The patient seems worried. Open with calm reassurance grounded in fact, use steady simple wording, and give one concrete thing they can do. Avoid alarming words unless safety needs them.",
    "frustrated": "The patient seems fed up. Acknowledge indirectly that changes like this are hard work, do not lecture or repeat rules, and offer the easiest realistic swap or a middle way.",
    "low_mood": "The patient seems discouraged. Be warm and gentle, suggest one small achievable step, and mention that their care team is there to support them too.",
    "confused": "The patient seems unsure what to do. Use simpler words, one idea at a time, and a concrete everyday example.",
    "disengaged": "The patient is giving short or low-effort replies. Keep the reply very short, give one easy practical tip, and end with a light, optional question that invites them back in.",
    "distress": (
        "The patient may be struggling badly (hopeless or giving up). Be gentle and brief, give at most one small "
        "practical point, and include one sentence encouraging them to talk to their care team, or to call "
        "Befrienders KL 03-7627 2929 or Talian HEAL 15555 if they feel overwhelmed. Never say or imply you have "
        "contacted, alerted or called anyone, including emergency services or the care team."
    ),
}


def tone_block(sentiment: dict | None) -> str:
    """Prompt block for rag._build_qwen_prompt. Empty for neutral/None."""
    if not sentiment or sentiment.get("state") not in TONE_GUIDANCE:
        return ""
    return f"\n## Patient's Current State\n{TONE_GUIDANCE[sentiment['state']]} {_TONE_RULE}"


# ---------------------------------------------------------------------------
# 4. Logging for the team dashboard
# ---------------------------------------------------------------------------
def record(session_id, patient_id, client_id, message, sentiment, source="llm") -> None:
    """Best-effort insert into patient_sentiment. Never breaks a reply."""
    if not sentiment or is_untracked_session(session_id):
        return
    try:
        import database as db

        s = db.SessionLocal()
        try:
            s.add(db.PatientSentiment(
                session_id=session_id,
                patient_id=patient_id,
                client_id=client_id,
                created_at=datetime.utcnow(),
                valence=sentiment["valence"],
                state=sentiment["state"],
                intensity=sentiment.get("intensity", 1),
                cues=sentiment.get("cues", ""),
                message_excerpt=(message or "")[:300],
                urgent=sentiment["state"] == "distress",
                source=source,
            ))
            s.commit()
        finally:
            s.close()
    except Exception as e:
        print(f"[Sentiment] record failed: {e}")


CRISIS_SENTIMENT = {"valence": "negative", "state": "distress", "intensity": 3, "cues": "crisis keywords"}


if __name__ == "__main__":
    hits = [
        "I want to die", "sometimes I think about suicide", "I keep hurting myself",
        "I'd be better off dead honestly", "I don't want to live like this anymore",
        "saya rasa nak bunuh diri", "aku nak mati je", "saya tak nak hidup lagi",
        "lebih baik aku mati", "I'm thinking of ending my life", "self-harm",
    ]
    misses = [
        "I want to diet properly", "can I eat durian?", "my diet is killing me lol, so much rice",
        "nak matikan api dapur dulu", "is it ok to die-t during Ramadan", "hidup sihat macam mana?",
        "my father died of a heart attack, am I at risk?",
    ]
    for t in hits:
        assert is_crisis(t), f"should hit: {t}"
    for t in misses:
        assert not is_crisis(t), f"should miss: {t}"

    assert not claims_action(CRISIS_RESPONSE)
    assert not claims_action(TONE_GUIDANCE["distress"].replace("Never say or imply you have", ""))
    assert claims_action("Don't worry, I've alerted your doctor.")
    assert claims_action("Saya telah menghubungi pasukan kecemasan.")
    for n in ("03-7627 2929", "15555", "999"):
        assert n in CRISIS_RESPONSE

    good = '```json\n{"valence":"negative","state":"frustrated","intensity":5,"cues":"so tired of all these rules"}\n```'
    assert parse_classification(good) == {
        "valence": "negative", "state": "frustrated", "intensity": 3, "cues": "so tired of all these rules"}
    assert parse_classification('{"valence":"negative","state":"angry","intensity":2}') is None
    assert parse_classification('{"valence":"bad","state":"anxious"}') is None
    assert parse_classification("not json") is None
    assert parse_classification("[1,2]") is None

    assert tone_block(None) == "" and tone_block({"state": "neutral"}) == ""
    assert "never" in tone_block({"state": "distress"}).lower()
    assert _patient_lines("Patient: a\nNutriBot: b\nPatient: c") == "- a\n- c"
    assert is_untracked_session("keepalive") and is_untracked_session("eval-3-1") and not is_untracked_session("app-user-11")
    print("sentiment.py self-check OK")
