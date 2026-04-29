import os
from dotenv import load_dotenv

load_dotenv()

# --- Feature flags ---
USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() in ("true", "1", "yes")
USE_CLARA = os.getenv("USE_CLARA", "false").lower() in ("true", "1", "yes")

# --- OpenAI config (used when USE_OLLAMA=false and USE_CLARA=false) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# --- Ollama config (used when USE_OLLAMA=true) ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nutribot-lora")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- CLaRa config (used when USE_CLARA=true) ---
CLARA_BASE_URL = os.getenv("CLARA_BASE_URL", "http://localhost:8001")

if not USE_OLLAMA and not USE_CLARA and not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY is not set. Either set it, or add USE_OLLAMA=true / USE_CLARA=true to .env."
    )


def get_llm():
    """
    Returns the configured LLM instance for LangChain chains.
    Note: When USE_CLARA=true, LangChain chains still need a fallback LLM
    for tasks like identify_target_disease(). We use OpenAI/Ollama for those.
    """
    if USE_OLLAMA:
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.5,
            num_predict=1500,
        )
    else:
        from langchain_openai import ChatOpenAI
        kwargs = dict(
            model_name=OPENAI_MODEL,
            temperature=0.5,
            max_tokens=1500,
            openai_api_key=OPENAI_API_KEY,
        )
        if OPENAI_BASE_URL:
            kwargs["openai_api_base"] = OPENAI_BASE_URL
        return ChatOpenAI(**kwargs)


def get_direct_llm_response(question: str) -> str:
    """Gets a direct response from the fallback LLM without RAG."""
    llm = get_llm()
    response = llm.invoke(question)
    return response.content


def call_clara_api(prompt: str, documents: list = None) -> str:
    """Calls the remote CLaRa inference server with a prompt + retrieved docs."""
    import requests
    payload = {
        "prompt": prompt,
        "max_tokens": 512,
        "temperature": 0.3,
        "documents": documents or []
    }
    try:
        resp = requests.post(f"{CLARA_BASE_URL}/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("answer", "")
    except Exception as e:
        print(f"[CLaRa API error] {e}")
        return ""
