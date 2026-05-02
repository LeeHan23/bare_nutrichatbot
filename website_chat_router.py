from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import database as db
import rag
from fastapi.responses import StreamingResponse
import asyncio
from sqlalchemy.orm import Session
from dependencies import get_api_client, get_db

# --- Router Initialization ---
chat_router = APIRouter()

# --- Pydantic Model ---
class ChatRequest(BaseModel):
    question: str
    session_id: str
    profile: dict | None = None     # Optional explicit profile dict (existing path)
    patient_id: int | None = None   # Optional: auto-load profile from DB by patient ID

async def stream_rag_response(question: str, client_id: int, session_id: str, profile: dict | None = None):
    """
    Streams the RAG response using the client's knowledge base.
    """
    try:
        response_data = rag.get_rag_response(
            question=question,
            client_id=client_id,
            chat_session_id=session_id,
            profile=profile
        )
        for chunk in response_data.get("answer", ""):
            yield chunk
            await asyncio.sleep(0.01)
    except Exception as e:
        print(f"❌ RAG Error: {e}")
        yield f"I encountered an error processing your request: {str(e)}"

@chat_router.post("/get_response")
async def get_chat_response(
    request: ChatRequest,
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """
    Gets a chat response using the client's specialised knowledge base.

    Profile resolution order:
      1. Explicit `profile` dict in the request body (legacy path, unchanged).
      2. `patient_id` in the request body — auto-loads the patient's medical record
         from the database and converts it to a profile dict.
      3. Neither provided — the RAG pipeline infers the condition from the question.
    """
    resolved_profile = request.profile

    if request.patient_id is not None and resolved_profile is None:
        patient = db.get_patient(database, request.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")
        if patient.client_id != client.id:
            raise HTTPException(status_code=403, detail="Patient does not belong to this client")
        resolved_profile = db.patient_to_profile_dict(patient)

    return StreamingResponse(
        stream_rag_response(request.question, client.id, request.session_id, resolved_profile),
        media_type="text/event-stream"
    )


@chat_router.post("/get_response_sync")
async def get_chat_response_sync(
    request: ChatRequest,
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """
    Non-streaming version of get_response. Returns the full answer as plain JSON.
    Easier to integrate for mobile apps and partner websites that don't handle SSE.

    Request body: same as /get_response
    Response: {"answer": "...", "session_id": "..."}
    """
    resolved_profile = request.profile

    if request.patient_id is not None and resolved_profile is None:
        patient = db.get_patient(database, request.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")
        if patient.client_id != client.id:
            raise HTTPException(status_code=403, detail="Patient does not belong to this client")
        resolved_profile = db.patient_to_profile_dict(patient)

    full_response = ""
    async for chunk in stream_rag_response(request.question, client.id, request.session_id, resolved_profile):
        full_response += chunk

    return {"answer": full_response, "session_id": request.session_id}