from llm import (
    get_direct_llm_response,
    call_clara_api,
    call_clara_compress,
    call_ollama_generate,
    USE_CLARA,
    USE_CLARA_COMPRESS,
    USE_AGENT_TOOLS,
)
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


def _to_second_person_profile(patient_context: str) -> str:
    """Rewrite third-person profile labels to second-person for self-mode.

    Turns lines like 'Name: Lim Siew Ching' into 'Your name: Lim Siew Ching
    (do NOT repeat this name back — address them as you).' so the LLM is
    primed for second-person responses by the input itself.
    """
    import re
    replacements = [
        (r"^Name:\s*(.+)$",
            r"Your name: \1  (do NOT repeat this name back — address them as 'you')"),
        (r"^Age:", r"Your age:"),
        (r"^Gender:", r"Your gender:"),
        (r"^Ethnicity:", r"Your ethnicity:"),
        (r"^Weight\s*\(kg\):", r"Your weight (kg):"),
        (r"^Height\s*\(cm\):", r"Your height (cm):"),
        (r"^BMI:", r"Your BMI:"),
        (r"^Conditions:", r"Your conditions:"),
        (r"^Medications:", r"Your medications:"),
        (r"^Allergies:", r"Your allergies:"),
        (r"^Dietary [Rr]estrictions?:", r"Your dietary restrictions:"),
        (r"^Religion:", r"Your religion:"),
        (r"^Notes:", r"Notes about you:"),
        # Extended supplementary fields — match prefixes broadly
        (r"^Tobacco status:", r"Your tobacco status:"),
        (r"^Alcohol", r"Your alcohol"),
        (r"^Fluid intake", r"Your fluid intake"),
        (r"^Supplements:", r"Your supplements:"),
        (r"^Activity ", r"Your activity "),
        (r"^Caffeine", r"Your caffeine"),
        (r"^Sodium ", r"Your sodium "),
        (r"^Meals ", r"Your meals "),
        (r"^Snacks ", r"Your snacks "),
        (r"^Processed food", r"Your processed food"),
        (r"^Fast food", r"Your fast food"),
        (r"^Self.prepared", r"Your self-prepared"),
        (r"^Sugar drinks", r"Your sugar drinks"),
        (r"^Food avoidance:", r"Your food avoidance:"),
        (r"^Nutrition knowledge:", r"Your nutrition knowledge:"),
        (r"^Readiness to change:", r"Your readiness to change:"),
        (r"^Fat intake", r"Your fat intake"),
        (r"^Fat type", r"Your fat type"),
        (r"^Medication compliance:", r"Your medication compliance:"),
        (r"^Self-reported food allergies:", r"Your self-reported food allergies:"),
        (r"^Activity types:", r"Your activity types:"),
    ]
    out = []
    for line in patient_context.split("\n"):
        for pat, rep in replacements:
            line = re.sub(pat, rep, line, count=1)
        out.append(line)
    return "\n".join(out)


def _build_qwen_prompt(
    question: str,
    patient_context: str,
    digest: str,
    food_context: str,
    profile: dict | None,
    is_patient_self: bool,
) -> str:
    """Build the Qwen generation prompt for Option B (CLaRa-compress → Qwen-generate).

    CLaRa produces a structured clinical digest; Qwen turns it into a warm,
    conversational response that respects the patient's profile and voice rules.
    """
    parts = [
        "You are NutriBot, a clinical nutrition assistant for Malaysian cardiac patients.\n"
    ]

    if patient_context:
        level = profile.get("personalization_level") if profile else None
        level_map = _LEVEL_INSTRUCTIONS_SELF if is_patient_self else _LEVEL_INSTRUCTIONS
        level_instruction = level_map.get(level, "") if level else ""

        if is_patient_self:
            ctx = _to_second_person_profile(patient_context)
            parts.append(
                "## Patient Profile (never repeat these details verbatim)\n" + ctx
            )
        else:
            parts.append("## Patient Profile\n" + patient_context)

        if level_instruction:
            parts.append(f"\n## Personalization Level {level}\n{level_instruction}")

    parts.append(f"\n## Clinical Evidence Digest\n{digest}")

    if food_context:
        parts.append(f"\n## Food Context\n{food_context}")

    if is_patient_self:
        parts.append(
            "\n## Voice Rules — apply to every word of your reply\n"
            "- Speak DIRECTLY to the person: use 'you', 'your', 'yours'\n"
            "- NEVER use their name; never say 'the patient', 'they', 'she', 'he'\n"
            "- NEVER use generic framings like 'an adult with BMI X should...'\n"
            "- Be warm, conversational, and practical — skip definitions and preamble\n"
            "- Verify every food recommendation against their conditions; flag anything contraindicated\n"
            "\n## Conversation Style — strictly follow this structure\n"
            "You are having a back-and-forth conversation, NOT writing a health article.\n"
            "ALWAYS follow this 3-part structure:\n"
            "  1. ONE short, direct answer to the question (2–4 sentences max). Pick the single most relevant point from the evidence digest.\n"
            "  2. ONE practical tip or example the person can act on immediately.\n"
            "  3. ONE follow-up question to learn more about their specific situation before giving further advice.\n"
            "Do NOT list multiple tips in a single reply. Do NOT use bullet points or numbered lists. "
            "Keep the entire reply under 100 words. Save the rest for after you hear their answer."
        )
    else:
        parts.append(
            "\n## Instructions\n"
            "Verify all food and drink recommendations against the patient's conditions. "
            "Flag anything contraindicated. Be concise and practical."
        )

    parts.append(f"\n## Question\n{question}")
    parts.append("\n## Answer")

    return "\n".join(parts)


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

        # --- v2 cardiac supplementary fields (extractor-filled) ---
        if profile.get("fat_intake_level"):
            parts.append(f"Fat intake level: {profile['fat_intake_level']}")
        fat_src = profile.get("fat_sources", [])
        if fat_src:
            parts.append(f"Fat type sources: {', '.join(fat_src)}")
        if profile.get("medication_compliance"):
            parts.append(f"Medication compliance: {profile['medication_compliance']}")
        act_types = profile.get("activity_types", [])
        if act_types:
            parts.append(f"Activity types: {', '.join(act_types)}")
        ext_allergies = profile.get("extractor_food_allergies", [])
        if ext_allergies:
            parts.append(f"Self-reported food allergies: {', '.join(ext_allergies)}")

        patient_context = "\n".join(parts)
        print(f"[DEBUG] Using patient profile: {target_disease}")
    else:
        target_disease = identify_target_disease(question)

    # ============================================================
    # Agent path — Qwen with MCP tool calling (USE_AGENT_TOOLS=true)
    # ============================================================
    if USE_AGENT_TOOLS:
        print("[DEBUG] Using agent path: Qwen with MCP tool calling")
        from agent import get_agent_response
        answer = get_agent_response(
            question=question,
            client_id=client_id,
            patient_context=patient_context,
            is_patient_self=is_patient_self,
            profile=profile,
        )
        if not answer:
            answer = (
                "I'm sorry, I couldn't generate a response right now. "
                "Please try again shortly."
            )
        return parse_response_for_image(answer)

    # ============================================================
    # CLaRa primary path — main RAG generation on Mac Studio
    # ============================================================
    if USE_CLARA:
        print("[DEBUG] Using CLaRa for generation")
        conditions_list = profile.get("condition", []) if profile else []
        retriever = get_retriever(str(client_id), patient_conditions=conditions_list)
        retrieval_query = (
            f"{', '.join(conditions_list)}: {question}" if conditions_list else question
        )
        retrieved_docs = retriever.invoke(retrieval_query)
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
                self_ctx = _to_second_person_profile(patient_context)
                header = (
                    "This is the person you are talking to. They are reading your reply.\n"
                    "Address them in second person ('you', 'your') — do NOT use their name.\n\n"
                    f"{self_ctx}"
                )
            else:
                header = f"Patient Profile:\n{patient_context}"
            if level_instruction:
                header += f"\n\nPersonalization Level {level}: {level_instruction}"
            if is_patient_self:
                instruction = (
                    "VOICE RULES — apply to every word of your reply:\n"
                    "  You are speaking DIRECTLY to the person whose profile is shown above.\n"
                    "  They are reading your reply word-for-word, in real time.\n"
                    "  ALWAYS write in second person: 'you', 'your', 'yours'.\n"
                    "  NEVER write the person's name. NEVER write 'the patient', 'they', 'she', 'he', 'her', 'his'.\n"
                    "  NEVER use generic third-person framings like 'an adult with BMI X should...'.\n"
                    "\n"
                    "Examples of CORRECT phrasing:\n"
                    "  CORRECT: 'Given your CKD and hypertension, you should aim for under 5g of sodium per day.'\n"
                    "  CORRECT: 'I would recommend you cut back on processed foods.'\n"
                    "  CORRECT: 'Because your BMI is 25.6, this is especially important for you.'\n"
                    "\n"
                    "Examples of WRONG phrasing — do NOT write like any of these:\n"
                    "  WRONG: 'Lim Siew Ching should aim for...'\n"
                    "  WRONG: 'The patient should limit...'\n"
                    "  WRONG: 'An adult with a BMI of 25.6 should...'\n"
                    "  WRONG: 'She has hypertension, so she should...'\n"
                    "\n"
                    "Also: verify every food and drink recommendation against your conditions and flag anything contraindicated. "
                    "Be conversational and practical — skip definitions and unnecessary preamble."
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
    # Option B: CLaRa compress → Qwen generate
    # CLaRa synthesises a clinical digest from retrieved docs;
    # Qwen delivers the conversational response.
    # ============================================================
    if USE_CLARA_COMPRESS:
        print("[DEBUG] Using Option B: CLaRa compress → Qwen generate")
        conditions_list = profile.get("condition", []) if profile else []
        retriever = get_retriever(str(client_id), patient_conditions=conditions_list)
        # Prefix query with patient conditions so condition-specific guideline
        # chunks score higher than generic nutrition content in vector search.
        retrieval_query = (
            f"{', '.join(conditions_list)}: {question}" if conditions_list else question
        )
        retrieved_docs = retriever.invoke(retrieval_query)
        doc_texts = [doc.page_content for doc in retrieved_docs]
        print(f"[DEBUG] Retrieved {len(doc_texts)} docs for CLaRa compress")

        for i, doc in enumerate(doc_texts):
            print(f"  [Doc {i+1}]: {doc[:120].replace(chr(10), ' ')}...")

        digest = call_clara_compress(doc_texts, question, patient_context)

        if not digest:
            # Graceful fallback: join raw chunks so Qwen still has clinical grounding
            print("[DEBUG] CLaRa compress failed — using raw chunks as fallback digest")
            digest = "Clinical context from guidelines:\n\n" + "\n\n---\n\n".join(doc_texts)

        try:
            food_context = get_food_context(question)
        except Exception as e:
            print(f"[Food context error] {e}")
            food_context = ""

        qwen_prompt = _build_qwen_prompt(
            question, patient_context, digest, food_context, profile, is_patient_self
        )
        print(f"[DEBUG] Qwen prompt length: {len(qwen_prompt)} chars")

        answer = call_ollama_generate(qwen_prompt)

        if not answer:
            answer = (
                "I'm sorry, I couldn't generate a response right now. "
                "Please try again shortly."
            )

        return parse_response_for_image(answer)

    # ============================================================
    # Legacy LangChain path (only used if USE_CLARA=false and USE_CLARA_COMPRESS=false)
    # ============================================================
    # Append personalization level to patient_context so the chain system
    # prompt receives it — same level injection as Option B and CLaRa paths.
    lc_patient_context = patient_context
    if profile:
        level = profile.get("personalization_level")
        level_map = _LEVEL_INSTRUCTIONS_SELF if is_patient_self else _LEVEL_INSTRUCTIONS
        level_instruction = level_map.get(level, "") if level else ""
        if level_instruction:
            lc_patient_context += f"\n\nPersonalization Level {level}: {level_instruction}"

    qa_chain = create_conversational_chain(
        client_id, target_disease, lc_patient_context,
        is_patient_self=is_patient_self,
        patient_conditions=profile.get("condition", []) if profile else [],
    )
    answer = qa_chain.invoke(
        {"question": question},
        config={"configurable": {"session_id": chat_session_id}},
    )

    if not answer:
        answer = "I'm sorry, I couldn't generate a response right now. Please try again."

    return parse_response_for_image(answer)
