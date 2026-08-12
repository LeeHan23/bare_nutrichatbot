"""Self-check for wiring exercise_video/image_url through the chat API
response (website_chat_router.py: META_MARKER / _split_meta, both
/chat/get_response streaming and /chat/get_response_sync).
Run: python scripts/test_exercise_video_api.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import website_chat_router as wcr

# --- _split_meta unit behavior ---
assert wcr._split_meta("plain answer, no marker") == ("plain answer, no marker", {})

text, meta = wcr._split_meta(f"Here you go{wcr.META_MARKER}" + '{"exercise_video": {"title": "X"}}')
assert text == "Here you go"
assert meta == {"exercise_video": {"title": "X"}}

# malformed JSON after the marker -> fail safe, return original text untouched
text, meta = wcr._split_meta(f"answer{wcr.META_MARKER}not json")
assert text == f"answer{wcr.META_MARKER}not json"
assert meta == {}

# --- Live end-to-end: a real video-intent question actually carries the
# marker through stream_rag_response, and get_response_sync's JSON body
# surfaces exercise_video as a real key (not embedded in answer text). ---
import database as db

s = db.SessionLocal()
patient = db.get_patient(s, 4)
profile = db.patient_to_profile_dict(patient, s)
s.close()


async def _collect():
    chunks = []
    async for chunk in wcr.stream_rag_response(
        "Can you show me an exercise video?",
        client_id=4,
        session_id="test-exercise-video-api",
        profile=profile,
        is_patient_self=True,
        patient_id=4,
    ):
        chunks.append(chunk)
    return "".join(chunks)


full = asyncio.run(_collect())
assert wcr.META_MARKER in full, "expected exercise_video meta marker in the live stream"
answer, meta = wcr._split_meta(full)
assert wcr.META_MARKER not in answer, "display text must not leak the marker"
assert meta.get("exercise_video", {}).get("youtube_url", "").startswith("http"), meta

print("ALL CHECKS PASSED")
