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
        types.Tool(
            name="send_patient_content",
            description=(
                "Deliver scheduled educational content to a patient. "
                "Finds the next queued content item whose scheduled_date is due, returns its tips, "
                "and marks it as sent in the delivery log. "
                "If material_id is provided, that specific material is sent regardless of schedule. "
                "When channel is 'whatsapp', the tips are also dispatched via WhatsApp to the patient's "
                "registered phone number (requires phone_number set via set_patient_phone). "
                "Returns the content tips and delivery metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The numeric ID of the patient to send content to.",
                    },
                    "material_id": {
                        "type": "integer",
                        "description": (
                            "Optional. Send this specific ContentMaterial by ID. "
                            "If omitted, the next due queued item is used."
                        ),
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["in_app", "whatsapp", "email"],
                        "description": "Delivery channel. Use 'whatsapp' to send via WhatsApp. Defaults to 'in_app'.",
                    },
                },
                "required": ["patient_id"],
            },
        ),
        types.Tool(
            name="generate_content_material",
            description=(
                "Generate educational nutrition tips for a specific condition group and day offset "
                "using the RAG pipeline (retrieves from ingested clinical documents, then calls Qwen to write tips). "
                "Saves the result to the content_materials table with is_active=False — a dev must approve it "
                "via approve_material before it can be sent to patients. "
                "Use this to create new materials grounded in the knowledge base."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "description": "Client ID whose knowledge base is included in retrieval.",
                    },
                    "condition_group": {
                        "type": "string",
                        "enum": ["T2DM", "HTN", "CKD", "Cardiac", "PCOS", "Dyslipidaemia", "General"],
                        "description": "Condition group for this material.",
                    },
                    "day_offset": {
                        "type": "integer",
                        "enum": [3, 5, 7, 14, 21, 30],
                        "description": "Day in the drip schedule (3, 5, 7, 14, 21, or 30).",
                    },
                    "custom_query": {
                        "type": "string",
                        "description": (
                            "Optional. Override the default RAG search query for this niche case. "
                            "Useful for generating content on a specific topic not in the preset list."
                        ),
                    },
                    "custom_prompt_topic": {
                        "type": "string",
                        "description": (
                            "Optional. Override the LLM prompt topic description. "
                            "E.g. 'managing blood sugar during Ramadan fasting for T2DM patients'."
                        ),
                    },
                },
                "required": ["client_id", "condition_group", "day_offset"],
            },
        ),
        types.Tool(
            name="list_content_materials",
            description=(
                "List educational content materials stored in the database. "
                "Shows title, condition group, day offset, approval status, and tip count. "
                "Use is_active=false to see materials pending dev review, is_active=true for approved ones."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "condition_group": {
                        "type": "string",
                        "description": "Optional. Filter to one condition group.",
                    },
                    "day_offset": {
                        "type": "integer",
                        "description": "Optional. Filter to one day offset.",
                    },
                    "is_active": {
                        "type": "boolean",
                        "description": "Optional. true = approved only, false = pending only. Omit for all.",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="approve_material",
            description=(
                "Approve a content material for patient delivery by setting is_active=True. "
                "Once approved, the material will be delivered to eligible patients on their scheduled day. "
                "Use list_content_materials to find the material_id of items pending review."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "material_id": {
                        "type": "integer",
                        "description": "The ID of the ContentMaterial to approve.",
                    },
                },
                "required": ["material_id"],
            },
        ),
        types.Tool(
            name="submit_dev_material",
            description=(
                "Submit a dev-designed or polished educational material directly into the content library. "
                "Unlike generate_content_material (which uses AI + RAG), this is for manually crafted content — "
                "e.g. infographics, dietitian-written tips, or professionally designed materials. "
                "Submitted materials are auto-approved (is_active=True) and ready for immediate delivery. "
                "Tips should be a JSON array of {tip_number, tip, source_hint} objects."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "condition_group": {
                        "type": "string",
                        "enum": ["T2DM", "HTN", "CKD", "Cardiac", "PCOS", "Dyslipidaemia", "General"],
                        "description": "Condition group this material targets.",
                    },
                    "day_offset": {
                        "type": "integer",
                        "enum": [3, 5, 7, 14, 21, 30],
                        "description": "Day in the drip schedule.",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Short topic key, e.g. 'breakfast_choices', 'sodium_basics'.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Human-readable title shown to patients, e.g. 'Day 3 — Breakfast Tips for Diabetes'.",
                    },
                    "tips": {
                        "type": "array",
                        "description": "Array of tip objects: [{tip_number, tip, source_hint}].",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tip_number": {"type": "integer"},
                                "tip": {"type": "string"},
                                "source_hint": {"type": "string"},
                            },
                        },
                    },
                    "file_url": {
                        "type": "string",
                        "description": "Optional. URL to a hosted polished file (PDF, image) to attach when sending via WhatsApp.",
                    },
                },
                "required": ["condition_group", "day_offset", "topic", "title", "tips"],
            },
        ),
        types.Tool(
            name="set_patient_phone",
            description=(
                "Store or update a patient's WhatsApp phone number. "
                "Required before content can be delivered via WhatsApp. "
                "Use international format, e.g. +60123456789 for a Malaysian number."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The numeric ID of the patient.",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number in international format, e.g. +60123456789.",
                    },
                },
                "required": ["patient_id", "phone_number"],
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
        elif name == "send_patient_content":
            return await _send_patient_content(
                patient_id=int(arguments["patient_id"]),
                material_id=int(arguments["material_id"]) if arguments.get("material_id") else None,
                channel=arguments.get("channel", "in_app"),
            )
        elif name == "generate_content_material":
            return await _generate_content_material(
                client_id=int(arguments["client_id"]),
                condition_group=arguments["condition_group"],
                day_offset=int(arguments["day_offset"]),
                custom_query=arguments.get("custom_query"),
                custom_prompt_topic=arguments.get("custom_prompt_topic"),
            )
        elif name == "list_content_materials":
            return await _list_content_materials(
                condition_group=arguments.get("condition_group"),
                day_offset=int(arguments["day_offset"]) if arguments.get("day_offset") else None,
                is_active=arguments.get("is_active"),
            )
        elif name == "approve_material":
            return await _approve_material(int(arguments["material_id"]))
        elif name == "submit_dev_material":
            return await _submit_dev_material(
                condition_group=arguments["condition_group"],
                day_offset=int(arguments["day_offset"]),
                topic=arguments["topic"],
                title=arguments["title"],
                tips=arguments["tips"],
                file_url=arguments.get("file_url"),
            )
        elif name == "set_patient_phone":
            return await _set_patient_phone(
                patient_id=int(arguments["patient_id"]),
                phone_number=arguments["phone_number"],
            )
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
                profile = db.patient_to_profile_dict(patient, db_session)
        finally:
            db_session.close()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: get_rag_response(question, client_id, session_id, profile, patient_id=patient_id),
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


async def _send_patient_content(
    patient_id: int,
    material_id: int | None,
    channel: str,
) -> list[types.TextContent]:
    import database as db
    from datetime import datetime

    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            return [types.TextContent(type="text", text=json.dumps(
                {"error": f"Patient {patient_id} not found"}
            ))]

        now = datetime.utcnow()

        if material_id is not None:
            # Specific material requested — find or create a delivery log entry for it
            material = session.query(db.ContentMaterial).filter(
                db.ContentMaterial.id == material_id
            ).first()
            if not material:
                return [types.TextContent(type="text", text=json.dumps(
                    {"error": f"ContentMaterial {material_id} not found"}
                ))]
            if not material.is_active:
                return [types.TextContent(type="text", text=json.dumps(
                    {"error": f"Material {material_id} is not active yet (pending dev-team approval)"}
                ))]

            # Find existing log entry or create an ad-hoc one
            log_entry = session.query(db.ContentDeliveryLog).filter(
                db.ContentDeliveryLog.patient_id == patient_id,
                db.ContentDeliveryLog.material_id == material_id,
            ).first()
            if log_entry is None:
                log_entry = db.ContentDeliveryLog(
                    patient_id=patient_id,
                    material_id=material_id,
                    condition_group=material.condition_group,
                    day_offset=material.day_offset,
                    scheduled_date=now,
                    status="queued",
                )
                session.add(log_entry)
                session.flush()
        else:
            # Find next due queued entry (scheduled_date <= now)
            log_entry = (
                session.query(db.ContentDeliveryLog)
                .filter(
                    db.ContentDeliveryLog.patient_id == patient_id,
                    db.ContentDeliveryLog.status == "queued",
                    db.ContentDeliveryLog.scheduled_date <= now,
                )
                .order_by(db.ContentDeliveryLog.scheduled_date)
                .first()
            )
            if log_entry is None:
                return [types.TextContent(type="text", text=json.dumps(
                    {"message": "No content due for this patient right now.", "patient_id": patient_id}
                ))]

            material = log_entry.material
            if material is None or not material.is_active:
                log_entry.status = "no_material"
                session.commit()
                return [types.TextContent(type="text", text=json.dumps(
                    {"message": "Queued slot found but no active material available yet.", "patient_id": patient_id, "day_offset": log_entry.day_offset, "condition_group": log_entry.condition_group}
                ))]

        # Mark as sent
        log_entry.status = "sent"
        log_entry.sent_at = now
        log_entry.channel = channel
        session.commit()

        result = {
            "delivered": True,
            "patient_id": patient_id,
            "patient_name": patient.name,
            "channel": channel,
            "material_id": material.id,
            "title": material.title,
            "condition_group": material.condition_group,
            "day_offset": material.day_offset,
            "topic": material.topic,
            "tips": material.raw_tips,
            "sent_at": now.isoformat(),
        }

        # Dispatch via WhatsApp when requested
        if channel == "whatsapp":
            if patient.whatsapp_opted_out:
                result["whatsapp"] = {"success": False, "error": "Patient has opted out of WhatsApp content (replied STOP)."}
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

            import whatsapp as wa
            first_name = patient.name.split()[0] if patient.name else "there"
            if material.content_type:
                # Weekly EKA material (Exercise / Knowledge / Activity)
                body = wa.format_eka_message(
                    content_type=material.content_type,
                    patient_first_name=first_name,
                    title=material.title,
                    content=material.raw_tips or {},
                    week_number=material.week_number,
                    personalization_level=patient.personalization_level,
                )
            else:
                # Legacy day-offset nutrition tips
                body = wa.format_tips_message(
                    patient_first_name=first_name,
                    title=material.title,
                    tips=material.raw_tips or [],
                    day_offset=material.day_offset,
                )
            media_url = material.file_path if material.file_path and material.file_path.startswith("http") else None
            wa_result = wa.send_message(
                to_phone=patient.phone_number or "",
                body=body,
                media_url=media_url,
            )
            result["whatsapp"] = wa_result

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        session.close()


async def _generate_content_material(
    client_id: int,
    condition_group: str,
    day_offset: int,
    custom_query: str | None,
    custom_prompt_topic: str | None,
) -> list[types.TextContent]:
    import database as db

    # Import generation helpers from scripts/generate_content.py
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from generate_content import _retrieve_chunks, _generate_tips, NICHE_CASES

    # Find the preset niche case, or build a custom one
    niche = next(
        (n for n in NICHE_CASES if n["group"] == condition_group and n["day_offset"] == day_offset),
        None,
    )
    if niche is None:
        # Custom niche — requires both query and prompt topic
        if not custom_query or not custom_prompt_topic:
            return [types.TextContent(type="text", text=json.dumps({
                "error": (
                    f"No preset niche case for {condition_group} / Day {day_offset}. "
                    "Provide custom_query and custom_prompt_topic to generate custom content."
                )
            }))]
        niche = {
            "group": condition_group,
            "condition_tags": [],
            "day_offset": day_offset,
            "topic": "custom",
            "title": f"Day {day_offset} — {condition_group} Custom Tips",
            "rag_query": custom_query,
            "prompt_topic": custom_prompt_topic,
        }
    else:
        # Allow overrides on preset niche
        niche = dict(niche)
        if custom_query:
            niche["rag_query"] = custom_query
        if custom_prompt_topic:
            niche["prompt_topic"] = custom_prompt_topic

    loop = asyncio.get_event_loop()

    def _run():
        chunks = _retrieve_chunks(niche["rag_query"], client_id)
        tips = _generate_tips(niche, chunks)
        db_session = db.SessionLocal()
        try:
            mat = db.upsert_content_material(
                db_session,
                condition_group=niche["group"],
                condition_tags=niche["condition_tags"],
                day_offset=niche["day_offset"],
                topic=niche["topic"],
                title=niche["title"],
                raw_tips=tips,
            )
            return {
                "created": True,
                "material_id": mat.id,
                "condition_group": mat.condition_group,
                "day_offset": mat.day_offset,
                "topic": mat.topic,
                "title": mat.title,
                "tip_count": len(tips),
                "tips": tips,
                "is_active": mat.is_active,
                "note": "Material saved with is_active=False. Call approve_material to release for delivery.",
            }
        finally:
            db_session.close()

    result = await loop.run_in_executor(None, _run)
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def _list_content_materials(
    condition_group: str | None,
    day_offset: int | None,
    is_active: bool | None,
) -> list[types.TextContent]:
    import database as db

    session = db.SessionLocal()
    try:
        materials = db.get_all_materials(session, day_offset=day_offset, condition_group=condition_group)
        if is_active is not None:
            materials = [m for m in materials if m.is_active == is_active]

        result = [
            {
                "id": m.id,
                "condition_group": m.condition_group,
                "day_offset": m.day_offset,
                "topic": m.topic,
                "title": m.title,
                "tip_count": len(m.raw_tips) if m.raw_tips else 0,
                "is_active": m.is_active,
                "has_file": bool(m.file_path),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in materials
        ]
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        session.close()


async def _approve_material(material_id: int) -> list[types.TextContent]:
    import database as db

    session = db.SessionLocal()
    try:
        mat = session.query(db.ContentMaterial).filter(db.ContentMaterial.id == material_id).first()
        if not mat:
            return [types.TextContent(type="text", text=json.dumps(
                {"error": f"ContentMaterial {material_id} not found"}
            ))]
        if mat.is_active:
            return [types.TextContent(type="text", text=json.dumps(
                {"material_id": material_id, "is_active": True, "note": "Already approved."}
            ))]
        mat.is_active = True
        session.commit()
        return [types.TextContent(type="text", text=json.dumps({
            "approved": True,
            "material_id": material_id,
            "title": mat.title,
            "condition_group": mat.condition_group,
            "day_offset": mat.day_offset,
            "note": "Material is now active and will be delivered to patients on schedule.",
        }))]
    finally:
        session.close()


async def _submit_dev_material(
    condition_group: str,
    day_offset: int,
    topic: str,
    title: str,
    tips: list,
    file_url: str | None,
) -> list[types.TextContent]:
    import database as db
    from datetime import datetime

    # Derive condition_tags from group name
    _tag_map = {
        "T2DM": ["Type 2 Diabetes"],
        "HTN": ["Hypertension"],
        "CKD": ["Chronic Kidney Disease"],
        "Cardiac": ["Ischaemic Heart Disease", "Heart Failure", "Dyslipidaemia"],
        "PCOS": ["Polycystic Ovary Syndrome (PCOS)", "Insulin Resistance"],
        "Dyslipidaemia": ["Dyslipidaemia", "Hypercholesterolaemia"],
        "General": [],
    }
    condition_tags = _tag_map.get(condition_group, [])

    session = db.SessionLocal()
    try:
        mat = db.ContentMaterial(
            condition_group=condition_group,
            condition_tags=condition_tags,
            day_offset=day_offset,
            topic=topic,
            title=title,
            raw_tips=tips,
            file_path=file_url,
            file_type="url" if file_url else None,
            is_active=True,  # Dev-submitted materials are auto-approved
            created_at=datetime.utcnow(),
        )
        session.add(mat)
        session.commit()
        session.refresh(mat)
        return [types.TextContent(type="text", text=json.dumps({
            "submitted": True,
            "material_id": mat.id,
            "condition_group": mat.condition_group,
            "day_offset": mat.day_offset,
            "topic": mat.topic,
            "title": mat.title,
            "tip_count": len(tips),
            "is_active": mat.is_active,
            "file_url": file_url,
            "note": "Dev material saved and auto-approved. Ready for patient delivery.",
        }, indent=2))]
    finally:
        session.close()


async def _set_patient_phone(patient_id: int, phone_number: str) -> list[types.TextContent]:
    import database as db

    normalised = db.normalise_phone_number(phone_number)

    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            return [types.TextContent(type="text", text=json.dumps(
                {"error": f"Patient {patient_id} not found"}
            ))]
        patient.phone_number = normalised
        patient.whatsapp_opted_out = False
        session.commit()
        return [types.TextContent(type="text", text=json.dumps({
            "updated": True,
            "patient_id": patient_id,
            "patient_name": patient.name,
            "phone_number": normalised,
            "note": "Phone number saved. Use send_patient_content with channel='whatsapp' to send content.",
        }))]
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
