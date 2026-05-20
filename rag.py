from llm import get_direct_llm_response, call_clara_api, USE_CLARA
from image_handler import parse_response_for_image
from chain_factory import create_conversational_chain
from vector_store import get_retriever

_LEVEL_INSTRUCTIONS = {
    "L0": (
        "This patient has no significant risk factors or history. "
        "You may provide the full spectrum of nutrition and lifestyle advice, "
        "including vigorous activity and performance-oriented goals."
    ),
    "L1": (
        "This patient has emerging or moderate cardiovascular risk (e.g. early hypertension, elevated BMI) "
        "with no functional limitations. Provide structured, safety-aware guidance with clear "
        "do/don't boundaries. Emphasise moderation and preventing escalation of risk."
    ),
    "L2": (
        "This patient has established conditions with physical limitations and higher cardiovascular risk. "
        "Recommend low-intensity activities only. Always include symptom monitoring cues "
        "(e.g. chest pain, breathlessness) and strict stop conditions for any activity."
    ),
    "L3": (
        "This patient is at high clinical risk or has had a recent cardiac event or disability. "
        "Restrict all recommendations to medically supervised options only. "
        "Include emergency education where relevant. Do not suggest unsupervised physical activity."
    ),
}

# Second-person versions — used when the patient is the one chatting
_LEVEL_INSTRUCTIONS_SELF = {
    "L0": (
        "You have no significant risk factors or health history. "
        "Full-spectrum nutrition and lifestyle advice is appropriate for you, "
        "including vigorous activity and performance-oriented goals."
    ),
    "L1": (
        "You have emerging or moderate cardiovascular risk (e.g. early hypertension, elevated BMI) "
        "with no functional limitations. I will provide structured, safety-aware guidance with clear "
        "do/don't boundaries, emphasising moderation and preventing escalation of risk."
    ),
    "L2": (
        "You have established conditions with physical limitations and higher cardiovascular risk. "
        "Only low-intensity activities are appropriate for you. Always watch for warning signs "
        "(e.g. chest pain, breathlessness) and stop any activity immediately if they occur."
    ),
    "L3": (
        "You are at high clinical risk or have had a recent cardiac event. "
        "All recommendations will be restricted to medically supervised options only. "
        "Do not attempt unsupervised physical activity."
    ),
}


def identify_target_disease(question: str) -> str:
    """Uses the orchestration LLM (Ollama) to identify the primary health condition."""
    prompt = f"""
Analyze the following user question and identify the primary health condition or disease mentioned.
If a specific condition like 'Type 2 Diabetes', 'hypertension', 'CKD', or 'high cholesterol' is mentioned, return that name.
If no specific disease is mentioned, return the phrase 'general health and wellness'.
Respond with only the name of the condition and nothing else.
User Question: "{question}"
"""
    disease = get_direct_llm_response(prompt)
    print(f"[DEBUG] Identified target condition: {disease}")
    return disease.strip()


def get_food_context(question: str) -> str:
    """
    Uses Ollama to identify any food or drink mentioned in the question and return
    a brief factual description of it. This grounds CLaRa when the knowledge base
    does not contain descriptions of specific dishes (e.g. Malaysian local foods).
    Returns an empty string if no food item is detected.
    """
    prompt = f"""You are a nutrition assistant with deep knowledge of Malaysian, Malay, Chinese, and Indian cuisines.

The following is a question from a patient. If it mentions a specific food, drink, or dish, write 2-3 sentences describing:
- What it is (ingredients, how it is made)
- Its key nutritional properties (calories, carbohydrates, fat, sodium, sugar — approximate)

If no specific food or drink is mentioned, reply with exactly: NONE

Question: "{question}"
Food description:"""
    result = get_direct_llm_response(prompt).strip()
    if result.upper().startswith("NONE"):
        return ""
    print(f"[DEBUG] Food context enrichment: {result[:120]}...")
    return result


def get_rag_response(question: str, client_id: int, chat_session_id: str, profile: dict | None = None, is_patient_self: bool = False) -> dict:
    patient_context = ""
    if profile:
        # --- Existing keys (backward-compatible with raw profile dicts) ---
        conditions = ", ".join(profile.get("condition", []))
        meds = ", ".join(profile.get("medications", []))
        restrictions = ", ".join(profile.get("dietary_restrictions", []))
        target_disease = f"Conditions: {conditions}. Medications: {meds}. Restrictions: {restrictions}."

        # --- Build richer patient_context block from extended profile fields ---
        # Conditions first — CLaRa must see the medical constraints before demographics
        parts = []
        if conditions: parts.append(f"Conditions: {conditions}")
        if meds: parts.append(f"Medications: {meds}")
        if restrictions: parts.append(f"Dietary restrictions: {restrictions}")
        allergies_str = ", ".join(profile.get("allergies", []))
        if allergies_str: parts.append(f"Allergies: {allergies_str}")
        if profile.get("notes"): parts.append(f"Clinical notes: {profile['notes']}")
        if profile.get("name"): parts.append(f"Name: {profile['name']}")
        if profile.get("age"): parts.append(f"Age: {profile['age']}")
        if profile.get("gender"): parts.append(f"Gender: {profile['gender']}")
        if profile.get("ethnicity"): parts.append(f"Ethnicity: {profile['ethnicity']}")
        w, h = profile.get("weight_kg"), profile.get("height_cm")
        if w and h:
            bmi = w / ((h / 100) ** 2)
            parts.append(f"Weight: {w}kg, Height: {h}cm, BMI: {bmi:.1f}")
        patient_context = "\n".join(parts)
        print(f"[DEBUG] Using patient profile: {target_disease}")
    else:
        target_disease = identify_target_disease(question)

    # ============================================================
    # CLaRa primary path — main RAG generation on Mac Studio
    # ============================================================
    if USE_CLARA:
        print("[DEBUG] Using CLaRa for generation")
        retriever = get_retriever(str(client_id))
        retrieved_docs = retriever.invoke(question)
        doc_texts = [doc.page_content for doc in retrieved_docs]
        print(f"[DEBUG] Retrieved {len(doc_texts)} docs for CLaRa")

        # Show preview of each retrieved doc to verify relevance
        for i, doc in enumerate(doc_texts):
            preview = doc[:150].replace('\n', ' ')
            print(f"  [Doc {i+1}]: {preview}...")

        # Enrich with food context if the question mentions a specific dish/food
        food_context = get_food_context(question)

        # Build the prompt with optional patient context
        if patient_context:
            level = profile.get("personalization_level") if profile else None
            level_map = _LEVEL_INSTRUCTIONS_SELF if is_patient_self else _LEVEL_INSTRUCTIONS
            level_instruction = level_map.get(level, "") if level else ""
            if is_patient_self:
                header = f"Your Profile:\n{patient_context}"
            else:
                header = f"Patient Profile:\n{patient_context}"
            if level_instruction:
                header += f"\n\nPersonalization Level {level}: {level_instruction}"
            if is_patient_self:
                instruction = (
                    "Respond directly to the patient using 'you' and 'your' — never use their name or say 'the patient'. "
                    "Verify all food and drink recommendations against the conditions listed above and flag any that are contraindicated. "
                    "Be conversational and practical; skip definitions and unnecessary preamble."
                )
            else:
                instruction = (
                    "Verify all food and drink recommendations against the patient's conditions above and flag any that are contraindicated. "
                    "Be concise and practical; skip definitions and unnecessary preamble."
                )
            food_block = f"\n\nFood context: {food_context}" if food_context else ""
            clara_prompt = f"{header}{food_block}\n\nInstruction: {instruction}\n\nQuestion: {question}\n\nAnswer:"
        else:
            food_block = f"Food context: {food_context}\n\n" if food_context else ""
            clara_prompt = f"{food_block}Instruction: Be conversational and practical; skip definitions and unnecessary preamble.\n\nQuestion: {question}\n\nAnswer:"

        answer = call_clara_api(clara_prompt, documents=doc_texts)

        if not answer:
            answer = (
                "I'm sorry, I couldn't generate a response right now. "
                "The nutrition assistant may be temporarily unavailable. Please try again shortly."
            )

        return parse_response_for_image(answer)

    # ============================================================
    # Legacy LangChain path (only used if USE_CLARA=false)
    # ============================================================
    qa_chain = create_conversational_chain(client_id, target_disease, patient_context, is_patient_self=is_patient_self)
    answer = qa_chain.invoke(
        {"question": question},
        config={"configurable": {"session_id": chat_session_id}},
    )

    if not answer:
        answer = "I'm sorry, I couldn't generate a response right now. Please try again."

    return parse_response_for_image(answer)
