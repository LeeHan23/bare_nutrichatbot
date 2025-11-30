from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import database as db
import rag
from fastapi.responses import StreamingResponse
import asyncio
from dependencies import get_api_client

# --- Router Initialization ---
chat_router = APIRouter()

# --- Pydantic Model ---
class ChatRequest(BaseModel):
    question: str
    session_id: str
    profile: dict | None = None  # Optional user profile from client

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
    client = Depends(get_api_client)
):
    """
    Gets a chat response using the client's specialized knowledge base.
    Authentication is handled by the API key dependency.
    """
    return StreamingResponse(
        stream_rag_response(request.question, client.id, request.session_id, request.profile),
        media_type="text/event-stream"
    )