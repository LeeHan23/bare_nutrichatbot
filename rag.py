from llm import get_direct_llm_response, call_clara_api, USE_CLARA
from image_handler import parse_response_for_image
from chain_factory import create_conversational_chain
from vector_store import get_retriever

RAG_FAILURE_PHRASES = ["i don't know", "i am not sure", "i cannot answer"]


def identify_target_disease(question: str) -> str:
    """Uses the LLM to identify the primary health condition in the user's query."""
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


def get_rag_response(question: str, client_id: int, chat_session_id: str, profile: dict | None = None) -> dict:
    patient_context = ""
    if profile:
        # --- Existing keys (backward-compatible with raw profile dicts) ---
        conditions = ", ".join(profile.get("condition", []))
        meds = ", ".join(profile.get("medications", []))
        restrictions = ", ".join(profile.get("dietary_restrictions", []))
        target_disease = f"Conditions: {conditions}. Medications: {meds}. Restrictions: {restrictions}."

        # --- Build richer patient_context block from extended profile fields ---
        parts = []
        if profile.get("name"): parts.append(f"Name: {profile['name']}")
        if profile.get("age"): parts.append(f"Age: {profile['age']}")
        if profile.get("gender"): parts.append(f"Gender: {profile['gender']}")
        if profile.get("ethnicity"): parts.append(f"Ethnicity: {profile['ethnicity']}")
        w, h = profile.get("weight_kg"), profile.get("height_cm")
        if w and h:
            bmi = w / ((h / 100) ** 2)
            parts.append(f"Weight: {w}kg, Height: {h}cm, BMI: {bmi:.1f}")
        if conditions: parts.append(f"Conditions: {conditions}")
        if meds: parts.append(f"Medications: {meds}")
        if restrictions: parts.append(f"Dietary restrictions: {restrictions}")
        allergies_str = ", ".join(profile.get("allergies", []))
        if allergies_str: parts.append(f"Allergies: {allergies_str}")
        if profile.get("notes"): parts.append(f"Clinical notes: {profile['notes']}")
        patient_context = "\n".join(parts)
        print(f"[DEBUG] Using patient profile: {target_disease}")
    else:
        target_disease = identify_target_disease(question)

    # ============================================================
    # NEW: CLaRa branch — retrieve docs, then send to CLaRa
    # ============================================================
    if USE_CLARA:
        print("[DEBUG] Using CLaRa for generation")
        try:
            # Use existing hybrid retriever to fetch relevant docs from ChromaDB
            retriever = get_retriever(str(client_id))
            retrieved_docs = retriever.invoke(question)
            doc_texts = [doc.page_content for doc in retrieved_docs]
            print(f"[DEBUG] Retrieved {len(doc_texts)} docs for CLaRa")

            # Build a prompt that includes patient context + question
            if patient_context:
                clara_prompt = (
                    f"Patient Profile:\n{patient_context}\n\n"
                    f"Question: {question}\n\nAnswer:"
                )
            else:
                clara_prompt = f"Question: {question}\n\nAnswer:"

            answer = call_clara_api(clara_prompt, documents=doc_texts)

            if not answer or any(phrase in answer.lower() for phrase in RAG_FAILURE_PHRASES):
                print("CLaRa response insufficient. Falling back to direct LLM.")
                answer = get_direct_llm_response(question)

            return parse_response_for_image(answer)
        except Exception as e:
            print(f"[CLaRa pipeline error] {e}. Falling back to standard chain.")
            # Fall through to the existing OpenAI/Ollama path below

    # ============================================================
    # Existing OpenAI/Ollama path (unchanged)
    # ============================================================
    qa_chain = create_conversational_chain(client_id, target_disease, patient_context)
    answer = qa_chain.invoke(
        {"question": question},
        config={"configurable": {"session_id": chat_session_id}},
    )

    if not answer or any(phrase.lower() in answer.lower() for phrase in RAG_FAILURE_PHRASES):
        print("RAG response insufficient. Falling back to direct LLM.")
        answer = get_direct_llm_response(question)

    return parse_response_for_image(answer)
