from llm import get_direct_llm_response
from image_handler import parse_response_for_image
from chain_factory import create_conversational_chain

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
    if profile:
        conditions = ", ".join(profile.get("condition", []))
        meds = ", ".join(profile.get("medications", []))
        restrictions = ", ".join(profile.get("dietary_restrictions", []))
        target_disease = f"Conditions: {conditions}. Medications: {meds}. Restrictions: {restrictions}."
        print(f"[DEBUG] Using provided profile context: {target_disease}")
    else:
        target_disease = identify_target_disease(question)

    qa_chain = create_conversational_chain(client_id, target_disease)

    # LCEL chain returns a plain string (StrOutputParser)
    answer = qa_chain.invoke(
        {"question": question},
        config={"configurable": {"session_id": chat_session_id}},
    )

    if not answer or any(phrase.lower() in answer.lower() for phrase in RAG_FAILURE_PHRASES):
        print("RAG response insufficient. Falling back to direct LLM.")
        answer = get_direct_llm_response(question)

    return parse_response_for_image(answer)
