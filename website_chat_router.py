import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database as db
import rag
from dependencies import get_api_client, get_db
from extractor import extract_from_message
from local_patient_store import LocalPatientStore

logger = logging.getLogger(__name__)

# --- Router Initialization ---
chat_router = APIRouter()

# --- Single PatientStore instance — swap to RemotePatientStore for production ---
patient_store = LocalPatientStore()


# --- Pydantic Model ---
class ChatRequest(BaseModel):
    question: str
    session_id: str
    profile: dict | None = None      # Optional explicit profile dict (legacy path)
    patient_id: int | None = None    # Optional: auto-load profile from DB by patient ID
    is_patient_self: bool | None = None  # True = patient is chatting (second-person). Defaults to True when patient_id is set; pass False explicitly for clinician tools.


async def stream_rag_response(
    question: str,
    client_id: int,
    session_id: str,
    profile: dict | None = None,
    is_patient_self: bool = False,
):
    """Streams the RAG response using the client's knowledge base."""
    try:
        response_data = rag.get_rag_response(
            question=question,
            client_id=client_id,
            chat_session_id=session_id,
            profile=profile,
            is_patient_self=is_patient_self,
        )
        for chunk in response_data.get("answer", ""):
            yield chunk
            await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"RAG Error: {e}")
        yield f"I encountered an error processing your request: {str(e)}"


def _resolve_patient_profile(
    request: ChatRequest,
    client,
    database: Session,
) -> dict | None:
    """
    Resolve the patient profile from the request.
    Order: explicit profile → patient_id lookup → None.
    Validates the patient belongs to the calling client.
    """
    if request.profile is not None:
        return request.profile

    if request.patient_id is None:
        return None

    patient = db.get_patient(database, request.patient_id)
    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {request.patient_id} not found",
        )
    if patient.client_id != client.id:
        raise HTTPException(
            status_code=403,
            detail="Patient does not belong to this client",
        )
    return db.patient_to_profile_dict(patient)


async def _record_first_chat(patient_id: int):
    """Set first_chat_at on the patient record the first time they chat."""
    try:
        loop = asyncio.get_event_loop()
        session = db.SessionLocal()
        await loop.run_in_executor(None, lambda: db.set_first_chat_at(session, patient_id))
        session.close()
    except Exception as e:
        logger.error(f"[first_chat_at] Failed to set for patient {patient_id}: {e}")


async def _run_extractor_background(
    patient_id: int,
    message: str,
    current_profile: dict,
    session_id: str,
):
    """
    Async background task: extract supplementary fields from the patient's
    message and persist via the PatientStore. Runs after the response is sent
    so it adds zero user-facing latency.
    """
    try:
        # Extractor is sync (blocking HTTP to Ollama), run it in a thread
        # so we don't block the asyncio event loop.
        loop = asyncio.get_event_loop()
        new_fields = await loop.run_in_executor(
            None,
            lambda: extract_from_message(message, current_profile),
        )

        if not new_fields:
            return

        applied = await loop.run_in_executor(
            None,
            lambda: patient_store.update_supplementary_fields(
                patient_id=patient_id,
                updates=new_fields,
                source_session_id=session_id,
            ),
        )
        if applied:
            logger.info(
                f"[Extractor] Patient {patient_id} updated: {list(applied.keys())}"
            )
    except Exception as e:
        # Never let extractor failures affect the user. Log and move on.
        logger.error(f"[Extractor] Background task failed: {e}")


@chat_router.post("/get_response")
async def get_chat_response(
    request: ChatRequest,
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """
    Streaming chat response.
    Profile resolution order:
      1. Explicit `profile` dict in the request body
      2. `patient_id` → auto-loaded from the database
      3. Neither — RAG infers the condition from the question
    """
    resolved_profile = _resolve_patient_profile(request, client, database)

    # Infer is_patient_self: default True when a patient_id is provided and the
    # caller did not explicitly set the flag. Clinician tools should pass False.
    is_patient_self = request.is_patient_self
    if is_patient_self is None:
        is_patient_self = request.patient_id is not None

    if request.patient_id is not None and resolved_profile is not None:
        asyncio.create_task(_record_first_chat(request.patient_id))
        asyncio.create_task(
            _run_extractor_background(
                patient_id=request.patient_id,
                message=request.question,
                current_profile=resolved_profile,
                session_id=request.session_id,
            )
        )

    return StreamingResponse(
        stream_rag_response(
            request.question,
            client.id,
            request.session_id,
            resolved_profile,
            is_patient_self=is_patient_self,
        ),
        media_type="text/event-stream",
    )


@chat_router.post("/get_response_sync")
async def get_chat_response_sync(
    request: ChatRequest,
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """
    Non-streaming version. Returns the full answer as JSON.
    Same profile resolution and extractor logic as /get_response.
    """
    resolved_profile = _resolve_patient_profile(request, client, database)

    is_patient_self = request.is_patient_self
    if is_patient_self is None:
        is_patient_self = request.patient_id is not None

    if request.patient_id is not None and resolved_profile is not None:
        asyncio.create_task(_record_first_chat(request.patient_id))
        asyncio.create_task(
            _run_extractor_background(
                patient_id=request.patient_id,
                message=request.question,
                current_profile=resolved_profile,
                session_id=request.session_id,
            )
        )

    full_response = ""
    async for chunk in stream_rag_response(
        request.question,
        client.id,
        request.session_id,
        resolved_profile,
        is_patient_self=is_patient_self,
    ):
        full_response += chunk

    return {"answer": full_response, "session_id": request.session_id}
