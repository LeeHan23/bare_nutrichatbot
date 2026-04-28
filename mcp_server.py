#!/usr/bin/env python3
"""
NutriChatbot MCP Server

Exposes the NutriChatbot's database, knowledge base, and RAG pipeline as MCP tools
so that AI agents (Claude, GPT agents, etc.) can query and interact with the system.

Transport modes:
  stdio  (default) — for Agent Gateway subprocess mode or direct MCP client connections
  sse             — HTTP/SSE transport for Docker / remote access

Usage:
    python mcp_server.py                          # stdio (Agent Gateway subprocess)
    python mcp_server.py --transport sse          # SSE on port 3101
    python mcp_server.py --transport sse --port 3200
"""
import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Ensure project root is on the path when run as a subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
import mcp.types as types

# ---------------------------------------------------------------------------
# Server definition
# ---------------------------------------------------------------------------

server = Server("nutribot-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_api_clients",
            description=(
                "List all B2B API clients registered in the NutriChatbot system. "
                "Returns each client's ID, name, and how many documents they have uploaded."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_client_documents",
            description=(
                "List all uploaded knowledge-base documents for a specific API client. "
                "Returns filename, upload date, file size, chunk count, and ingestion status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "description": "The numeric ID of the API client.",
                    }
                },
                "required": ["client_id"],
            },
        ),
        types.Tool(
            name="search_nutrition_knowledge",
            description=(
                "Perform a semantic similarity search across the NutriChatbot's nutrition "
                "knowledge base. Returns the most relevant text passages and their sources. "
                "Useful for fact-checking, retrieving guidelines, or grounding a response "
                "without making an LLM call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query, e.g. 'foods to avoid with diabetes', "
                            "'sodium limit for CKD', 'glycaemic index of roti canai'."
                        ),
                    },
                    "client_id": {
                        "type": "integer",
                        "description": (
                            "Optional. If provided, also searches this client's "
                            "private knowledge collection."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_nutrition_advice",
            description=(
                "Get a full, context-aware nutrition advice response using the RAG pipeline. "
                "Retrieves relevant knowledge then generates a dietitian-style answer via GPT. "
                "Maintains conversation history across calls sharing the same session_id. "
                "When patient_id is provided, the patient's full medical profile is automatically "
                "loaded from the database and injected into the response context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The user's nutrition question or message.",
                    },
                    "client_id": {
                        "type": "integer",
                        "description": "Client ID whose knowledge base should be included in retrieval.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": (
                            "Unique session identifier for conversation continuity. "
                            "Use a consistent UUID per conversation thread."
                        ),
                    },
                    "patient_id": {
                        "type": "integer",
                        "description": (
                            "Optional. If provided, the patient's medical profile is automatically "
                            "loaded from the database and injected into the RAG context, enabling "
                            "fully personalised advice without passing a manual profile dict."
                        ),
                    },
                },
                "required": ["question", "client_id", "session_id"],
            },
        ),
        types.Tool(
            name="get_patient_profile",
            description=(
                "Retrieve the full medical profile for a specific patient by their numeric ID. "
                "Returns demographics (name, age, gender, ethnicity, weight, height, BMI), "
                "conditions, medications, dietary restrictions, allergies, and clinical notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The numeric ID of the patient to retrieve.",
                    }
                },
                "required": ["patient_id"],
            },
        ),
        types.Tool(
            name="list_patients",
            description=(
                "List all patients registered under a specific B2B API client. "
                "Returns a summary (id, name, age, gender, ethnicity, primary conditions) "
                "for each patient — useful for browsing before fetching a full profile."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "description": "The numeric ID of the API client whose patients to list.",
                    }
                },
                "required": ["client_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "list_api_clients":
            return await _list_api_clients()
        elif name == "get_client_documents":
            return await _get_client_documents(int(arguments["client_id"]))
        elif name == "search_nutrition_knowledge":
            return await _search_nutrition_knowledge(
                query=arguments["query"],
                client_id=arguments.get("client_id"),
                top_k=min(int(arguments.get("top_k", 5)), 10),
            )
        elif name == "get_nutrition_advice":
            return await _get_nutrition_advice(
                question=arguments["question"],
                client_id=int(arguments["client_id"]),
                session_id=arguments["session_id"],
                patient_id=arguments.get("patient_id"),
            )
        elif name == "get_patient_profile":
            return await _get_patient_profile(int(arguments["patient_id"]))
        elif name == "list_patients":
            return await _list_patients(int(arguments["client_id"]))
        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _list_api_clients() -> list[types.TextContent]:
    import database as db

    session = db.SessionLocal()
    try:
        clients = db.get_all_api_clients(session)
        result = [
            {
                "id": c.id,
                "client_name": c.client_name,
                "document_count": len(c.documents),
            }
            for c in clients
        ]
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        session.close()


async def _get_client_documents(client_id: int) -> list[types.TextContent]:
    import database as db

    session = db.SessionLocal()
    try:
        docs = db.get_client_documents(session, client_id)
        if not docs:
            return [types.TextContent(type="text", text=json.dumps(
                {"client_id": client_id, "documents": [], "message": "No documents found."}
            ))]
        result = [
            {
                "id": d.id,
                "filename": d.filename,
                "upload_date": d.upload_date.isoformat(),
                "file_size_bytes": d.file_size,
                "chunk_count": d.chunk_count,
                "status": d.status,
            }
            for d in docs
        ]
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        session.close()


async def _search_nutrition_knowledge(
    query: str,
    client_id: int | None,
    top_k: int,
) -> list[types.TextContent]:
    from langchain_community.vectorstores import PGVector
    from vector_store import get_connection_string
    from embeddings import get_embedding_function

    loop = asyncio.get_event_loop()

    def _do_search():
        conn = get_connection_string()
        emb = get_embedding_function()

        base_db = PGVector(
            connection_string=conn,
            embedding_function=emb,
            collection_name="base_knowledge",
            use_jsonb=True,
        )
        docs = base_db.similarity_search(query, k=top_k)

        # Merge in client-specific results if requested
        if client_id is not None:
            client_db = PGVector(
                connection_string=conn,
                embedding_function=emb,
                collection_name=f"client_{client_id}_knowledge",
                use_jsonb=True,
            )
            seen = {d.page_content for d in docs}
            for d in client_db.similarity_search(query, k=top_k):
                if d.page_content not in seen:
                    docs.append(d)
                    seen.add(d.page_content)

        return [
            {
                "rank": i + 1,
                # Cap passage length to keep responses manageable
                "content": d.page_content[:1200],
                "source": d.metadata.get("source", d.metadata.get("file_hash", "unknown")),
            }
            for i, d in enumerate(docs[:top_k])
        ]

    result = await loop.run_in_executor(None, _do_search)
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def _get_nutrition_advice(
    question: str,
    client_id: int,
    session_id: str,
    patient_id: int | None = None,
) -> list[types.TextContent]:
    from rag import get_rag_response
    import database as db

    # Auto-load patient profile from DB when patient_id is provided
    profile = None
    if patient_id is not None:
        db_session = db.SessionLocal()
        try:
            patient = db.get_patient(db_session, patient_id)
            if patient:
                profile = db.patient_to_profile_dict(patient)
        finally:
            db_session.close()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: get_rag_response(question, client_id, session_id, profile),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def _get_patient_profile(patient_id: int) -> list[types.TextContent]:
    import database as db

    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            return [types.TextContent(type="text", text=json.dumps(
                {"error": f"Patient {patient_id} not found"}
            ))]
        bmi = None
        if patient.weight_kg and patient.height_cm:
            bmi = round(patient.weight_kg / ((patient.height_cm / 100) ** 2), 1)
        result = {
            "id": patient.id,
            "client_id": patient.client_id,
            "name": patient.name,
            "age": patient.age,
            "gender": patient.gender,
            "ethnicity": patient.ethnicity,
            "weight_kg": patient.weight_kg,
            "height_cm": patient.height_cm,
            "bmi": bmi,
            "conditions": patient.conditions,
            "medications": patient.medications,
            "dietary_restrictions": patient.dietary_restrictions,
            "allergies": patient.allergies,
            "notes": patient.notes,
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        session.close()


async def _list_patients(client_id: int) -> list[types.TextContent]:
    import database as db

    session = db.SessionLocal()
    try:
        patients = db.get_patients_by_client(session, client_id)
        result = [
            {
                "id": p.id,
                "name": p.name,
                "age": p.age,
                "gender": p.gender,
                "ethnicity": p.ethnicity,
                "conditions": p.conditions,
            }
            for p in patients
        ]
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Entry point — stdio or SSE transport
# ---------------------------------------------------------------------------

def _build_init_options() -> InitializationOptions:
    return InitializationOptions(
        server_name="nutribot-mcp",
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )


async def _run_stdio():
    print("[MCP Server] Starting with stdio transport", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, _build_init_options())


def _run_sse(port: int):
    """Start an HTTP/SSE server so Agent Gateway (or any MCP client) can connect remotely."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    import uvicorn

    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(streams[0], streams[1], _build_init_options())

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ]
    )

    print(f"[MCP Server] Starting SSE transport on http://0.0.0.0:{port}/sse", file=sys.stderr)
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NutriChatbot MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode: 'stdio' (default) for Agent Gateway subprocess, "
             "'sse' for Docker/remote HTTP access.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3101,
        help="Port for SSE transport (default: 3101). Ignored in stdio mode.",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        _run_sse(args.port)
    else:
        asyncio.run(_run_stdio())
