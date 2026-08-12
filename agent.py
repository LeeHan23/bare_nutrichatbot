"""
Agentic Qwen tool-calling loop for NutriBot.

Qwen2.5:32b via Ollama natively supports function/tool calling.
Qwen decides which tools to call, results are fed back, and it generates
a grounded, patient-specific nutritional response.

Enabled by USE_AGENT_TOOLS=true in .env.
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:32b")
MAX_TOOL_ROUNDS = 5

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_nutrition_knowledge",
            "description": (
                "Search the clinical nutrition knowledge base for guidelines, evidence, and "
                "recommendations. Always call this before answering clinical questions to "
                "ground your response in evidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'sodium limit CKD', 'foods to avoid after CABG'.",
                    },
                    "client_id": {
                        "type": "integer",
                        "description": "Optional. Include this client's private knowledge collection.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_patient_profile",
            "description": "Retrieve the full medical profile for a patient by their numeric ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The patient's numeric ID.",
                    }
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_patients",
            "description": "List all patients under a specific API client.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "description": "The API client ID.",
                    }
                },
                "required": ["client_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_client_documents",
            "description": "List all uploaded knowledge-base documents for an API client.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "description": "The API client ID.",
                    }
                },
                "required": ["client_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_patient_content",
            "description": (
                "Deliver scheduled educational content to a patient. "
                "Finds the next due queued item, returns its tips, and marks it as sent. "
                "Use when the patient asks about their learning programme or weekly tips."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The patient's numeric ID.",
                    },
                    "material_id": {
                        "type": "integer",
                        "description": "Optional. Send a specific material by ID.",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["in_app", "whatsapp", "email"],
                        "description": "Delivery channel (default: in_app).",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_clients",
            "description": "List all registered B2B API clients.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clinical_advice",
            "description": (
                "Generate evidence-based clinical nutrition advice using CLaRa, "
                "the fine-tuned clinical nutrition model. "
                "CLaRa retrieves relevant guidelines and produces a grounded, "
                "clinically accurate recommendation. "
                "Call this for any nutrition or dietary question — CLaRa handles "
                "retrieval and generation. "
                "You then present CLaRa's answer to the patient in a warm, "
                "conversational, culturally-appropriate way."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "The clinical question to send to CLaRa. "
                            "You may rephrase or focus the patient's message here "
                            "to get a more precise clinical answer, e.g. "
                            "'safe breakfast foods for CKD Stage 4 with 1L fluid restriction and low potassium diet'."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Sync tool executor — calls DB / vector store directly, no asyncio
# ---------------------------------------------------------------------------

def _execute_tool(name: str, args: dict, patient_context: str = "", client_id: int = 1) -> str:
    try:
        if name == "get_clinical_advice":
            return _tool_get_clinical_advice(
                question=args["question"],
                patient_context=patient_context,
                client_id=client_id,
            )
        elif name == "search_nutrition_knowledge":
            return _tool_search_knowledge(
                query=args["query"],
                client_id=args.get("client_id"),
                top_k=min(int(args.get("top_k", 5)), 10),
            )
        elif name == "get_patient_profile":
            return _tool_get_patient_profile(int(args["patient_id"]))
        elif name == "list_patients":
            return _tool_list_patients(int(args["client_id"]))
        elif name == "get_client_documents":
            return _tool_get_client_documents(int(args["client_id"]))
        elif name == "send_patient_content":
            return _tool_send_patient_content(
                patient_id=int(args["patient_id"]),
                material_id=int(args["material_id"]) if args.get("material_id") else None,
                channel=args.get("channel", "in_app"),
            )
        elif name == "list_api_clients":
            return _tool_list_api_clients()
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_search_knowledge(query: str, client_id: int | None, top_k: int) -> str:
    from langchain_community.vectorstores import PGVector
    from vector_store import get_connection_string
    from embeddings import get_embedding_function

    conn = get_connection_string()
    emb = get_embedding_function()
    base_db = PGVector(
        connection_string=conn,
        embedding_function=emb,
        collection_name="base_knowledge",
        use_jsonb=True,
    )
    docs = base_db.similarity_search(query, k=top_k)

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

    result = [
        {
            "rank": i + 1,
            "content": d.page_content[:1200],
            "source": d.metadata.get("source", d.metadata.get("file_hash", "unknown")),
        }
        for i, d in enumerate(docs[:top_k])
    ]
    return json.dumps(result, indent=2)


def _tool_get_patient_profile(patient_id: int) -> str:
    import database as db
    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            return json.dumps({"error": f"Patient {patient_id} not found"})
        bmi = None
        if patient.weight_kg and patient.height_cm:
            bmi = round(patient.weight_kg / ((patient.height_cm / 100) ** 2), 1)
        return json.dumps({
            "id": patient.id,
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
        }, indent=2)
    finally:
        session.close()


def _tool_list_patients(client_id: int) -> str:
    import database as db
    session = db.SessionLocal()
    try:
        patients = db.get_patients_by_client(session, client_id)
        return json.dumps([
            {"id": p.id, "name": p.name, "age": p.age, "gender": p.gender,
             "ethnicity": p.ethnicity, "conditions": p.conditions}
            for p in patients
        ], indent=2)
    finally:
        session.close()


def _tool_get_client_documents(client_id: int) -> str:
    import database as db
    session = db.SessionLocal()
    try:
        docs = db.get_client_documents(session, client_id)
        if not docs:
            return json.dumps({"client_id": client_id, "documents": [], "message": "No documents found."})
        return json.dumps([
            {"id": d.id, "filename": d.filename, "upload_date": d.upload_date.isoformat(),
             "file_size_bytes": d.file_size, "chunk_count": d.chunk_count, "status": d.status}
            for d in docs
        ], indent=2)
    finally:
        session.close()


def _tool_send_patient_content(patient_id: int, material_id: int | None, channel: str) -> str:
    import database as db
    from datetime import datetime

    session = db.SessionLocal()
    try:
        patient = db.get_patient(session, patient_id)
        if not patient:
            return json.dumps({"error": f"Patient {patient_id} not found"})

        now = datetime.utcnow()

        if material_id is not None:
            material = session.query(db.ContentMaterial).filter(
                db.ContentMaterial.id == material_id
            ).first()
            if not material:
                return json.dumps({"error": f"ContentMaterial {material_id} not found"})
            if not material.is_active:
                return json.dumps({"error": f"Material {material_id} is not active yet"})
            log_entry = session.query(db.ContentDeliveryLog).filter(
                db.ContentDeliveryLog.patient_id == patient_id,
                db.ContentDeliveryLog.material_id == material_id,
            ).first()
            if log_entry is None:
                log_entry = db.ContentDeliveryLog(
                    patient_id=patient_id, material_id=material_id,
                    condition_group=material.condition_group, day_offset=material.day_offset,
                    scheduled_date=now, status="queued",
                )
                session.add(log_entry)
                session.flush()
        else:
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
                return json.dumps({"message": "No content due for this patient right now.", "patient_id": patient_id})

            material = log_entry.material
            if material is None or not material.is_active:
                log_entry.status = "no_material"
                session.commit()
                return json.dumps({"message": "No active material available yet.", "patient_id": patient_id})

        log_entry.status = "sent"
        log_entry.sent_at = now
        log_entry.channel = channel
        session.commit()

        return json.dumps({
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
        }, indent=2)
    finally:
        session.close()


def _tool_list_api_clients() -> str:
    import database as db
    session = db.SessionLocal()
    try:
        clients = db.get_all_api_clients(session)
        return json.dumps([
            {"id": c.id, "client_name": c.client_name, "document_count": len(c.documents)}
            for c in clients
        ], indent=2)
    finally:
        session.close()


def _tool_get_clinical_advice(question: str, patient_context: str, client_id: int) -> str:
    from vector_store import get_retriever
    from llm import call_clara_api

    # Extract conditions from patient_context for condition-prefixed retrieval
    conditions = []
    for line in patient_context.split("\n"):
        if line.startswith("Conditions:"):
            conditions = [c.strip() for c in line.replace("Conditions:", "").split(",") if c.strip()]
            break

    retriever = get_retriever(str(client_id), patient_conditions=conditions)
    retrieval_query = f"{', '.join(conditions)}: {question}" if conditions else question
    retrieved_docs = retriever.invoke(retrieval_query)
    doc_texts = [doc.page_content for doc in retrieved_docs]
    print(f"[Agent/CLaRa] Retrieved {len(doc_texts)} docs for: {retrieval_query[:80]}...")

    if patient_context:
        clara_prompt = (
            f"Patient Profile:\n{patient_context}\n\n"
            "Instruction: Verify all food and drink recommendations against the patient's "
            "conditions above and flag any that are contraindicated. Be concise and practical.\n\n"
            f"Question: {question}\n\nAnswer:"
        )
    else:
        clara_prompt = (
            "Instruction: Be concise and practical; skip definitions and unnecessary preamble.\n\n"
            f"Question: {question}\n\nAnswer:"
        )

    answer = call_clara_api(clara_prompt, documents=doc_texts)
    if not answer:
        return json.dumps({"error": "CLaRa is temporarily unavailable."})
    return json.dumps({"clinical_answer": answer})


# ---------------------------------------------------------------------------
# Agentic response loop
# ---------------------------------------------------------------------------

def get_agent_response(
    question: str,
    client_id: int,
    patient_context: str,
    is_patient_self: bool,
    profile: dict | None,
    component: str | None = None,
) -> str:
    """
    Run the Qwen tool-calling loop and return the final answer string.

    Qwen is given all tool definitions. It calls tools as needed (up to
    MAX_TOOL_ROUNDS), then produces a grounded, patient-specific response.
    """
    from rag import (
        _to_second_person_profile,
        _LEVEL_INSTRUCTIONS,
        _LEVEL_INSTRUCTIONS_SELF,
        _build_care_path_block,
        _build_onboarding_block,
        _build_exercise_catalog_block,
    )
    from taxonomy import component_scope_block

    # ── System prompt ──────────────────────────────────────────────────────
    system_parts = [
        "You are NutriBot, a conversational nutrition coordinator for Malaysian cardiac patients. "
        "You have a specialist clinical model called CLaRa available via the get_clinical_advice tool. "
        "CLaRa is fine-tuned on clinical nutrition guidelines and handles all evidence-based recommendations — "
        "always call get_clinical_advice for any dietary or nutrition question before responding. "
        "Your role is to: (1) decide what clinical question to ask CLaRa, "
        "(2) SAFETY-CHECK CLaRa's answer against the patient's dietary restrictions and conditions "
        "before presenting it — remove or replace any food CLaRa suggests that is contraindicated "
        "(e.g. high-potassium foods like spinach, tomatoes, bananas for a low-potassium patient; "
        "high-phosphorus foods for a low-phosphorus patient; fluids that exceed the daily fluid limit), "
        "(3) present the corrected answer to the patient in a warm, culturally-aware, conversational way, "
        "(4) manage the flow of the conversation — ask follow-up questions, provide emotional support, "
        "and ensure the patient understands the advice in the context of Malaysian food culture."
    ]

    if patient_context:
        level = profile.get("personalization_level") if profile else None
        level_map = _LEVEL_INSTRUCTIONS_SELF if is_patient_self else _LEVEL_INSTRUCTIONS
        level_instruction = level_map.get(level, "") if level else ""

        ctx = _to_second_person_profile(patient_context) if is_patient_self else patient_context
        system_parts.append(f"\n## Patient Profile\n{ctx}")
        if level_instruction:
            system_parts.append(f"\n## Personalization Level {level}\n{level_instruction}")

        care_path_block = _build_care_path_block(profile)
        if care_path_block:
            system_parts.append(f"\n## Care Path & Objectives\n{care_path_block}")

        onboarding_block = _build_onboarding_block(profile)
        if onboarding_block:
            system_parts.append(f"\n## Onboarding Stage\n{onboarding_block}")

    scope_block = component_scope_block(component)
    if scope_block:
        system_parts.append(f"\n## Component Scope\n{scope_block}")

    if component == "exercise":
        catalog_block = _build_exercise_catalog_block(profile)
        if catalog_block:
            system_parts.append(f"\n## Approved Exercise Catalog\n{catalog_block}")

    if is_patient_self:
        system_parts.append(
            "\n## Voice Rules (apply to every word)\n"
            "- Speak directly to the person: use 'you', 'your', 'yours'\n"
            "- NEVER use their name or say 'the patient', 'they', 'she', 'he'\n"
            "- Short conversational replies: one key point + one follow-up question\n"
            "- Keep replies under 100 words"
        )
    else:
        system_parts.append(
            "\n## Instructions\n"
            "Verify all food recommendations against the patient's conditions. "
            "Flag anything contraindicated. Be concise and practical."
        )

    system_prompt = "\n".join(system_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    # ── Tool-calling loop ──────────────────────────────────────────────────
    for round_num in range(MAX_TOOL_ROUNDS):
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 1024,
                "keep_alive": -1,
            },
        }

        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Agent] Ollama error (round {round_num}): {e}")
            return ""

        message = data.get("message", {})
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            # No more tool calls — this is the final answer
            return message.get("content", "")

        # Append assistant message (with tool_calls) to history
        messages.append({
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls,
        })

        # Execute each tool call and append result
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = {}

            print(f"[Agent] Tool call: {name}({raw_args})")
            result = _execute_tool(name, raw_args, patient_context=patient_context, client_id=client_id)
            print(f"[Agent] Tool result ({name}): {result[:200]}...")

            messages.append({"role": "tool", "content": result})

    # Max rounds reached — force a final answer without tools
    print(f"[Agent] Reached max tool rounds ({MAX_TOOL_ROUNDS}), forcing final answer")
    messages.append({
        "role": "user",
        "content": "Please provide your final answer based on the information gathered above.",
    })
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 800, "keep_alive": -1},
    }
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        print(f"[Agent] Final answer error: {e}")
        return ""
