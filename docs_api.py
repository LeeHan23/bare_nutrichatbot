"""Standalone document-QA API — no patient/client/chat-history mock database dependency.

Reuses the existing PGVector document store (base_knowledge collection, same
Postgres instance as the main bot) and the CLaRa-compress -> Qwen-generate
pipeline from llm.py, but never touches patients/clients/chat_messages. For
another application that just wants grounded nutrition Q&A over the document
corpus, with no patient profile or personalization.

Run standalone: .venv/bin/python -m uvicorn docs_api:app --host 0.0.0.0 --port 8100
"""

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from llm import call_clara_compress, call_ollama_generate
from vector_store import get_retriever

app = FastAPI(title="Nutribot Docs API")

DOCS_API_KEY = os.getenv("DOCS_API_KEY")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Depends(_api_key_header)) -> None:
    if DOCS_API_KEY and api_key != DOCS_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


class AskRequest(BaseModel):
    question: str


@app.post("/ask", dependencies=[Depends(verify_api_key)])
def ask(request: AskRequest) -> dict:
    # "0" = no per-client collection; only base_knowledge (24k+ ingested chunks) is searched.
    retriever = get_retriever("0")
    doc_texts = [doc.page_content for doc in retriever.invoke(request.question)]

    digest = call_clara_compress(doc_texts, request.question)
    if not digest:
        digest = "Clinical context from guidelines:\n\n" + "\n\n---\n\n".join(doc_texts)

    prompt = (
        "You are NutriBot, a clinical nutrition assistant for Malaysian cardiac patients.\n"
        f"\n## Clinical Evidence Digest\n{digest}\n"
        "\n## Instructions\nAnswer using only the evidence above. Be concise and practical.\n"
        f"\n## Question\n{request.question}\n\n## Answer"
    )

    answer = call_ollama_generate(prompt)
    if not answer:
        raise HTTPException(status_code=502, detail="Generation failed — backend unavailable")

    return {"answer": answer}
