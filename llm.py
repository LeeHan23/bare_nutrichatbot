import os
from dotenv import load_dotenv

load_dotenv()

# --- Feature flag ---
USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() in ("true", "1", "yes")

# --- OpenAI config (used when USE_OLLAMA=false) ---
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
# Optional: point at the Agent Gateway LLM proxy (e.g. http://localhost:3200)
# so all GPT calls are rate-limited centrally. Leave unset to call OpenAI directly.
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# --- Ollama config (used when USE_OLLAMA=true) ---
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "nutribot-lora")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

if not USE_OLLAMA and not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY is not set. Either set it or add USE_OLLAMA=true to .env to use the local Ollama model."
    )


def get_llm():
    """
    Returns the configured LLM instance.

    Controlled by the USE_OLLAMA environment variable:
      USE_OLLAMA=false (default) — ChatOpenAI (gpt-4-turbo or OPENAI_MODEL)
      USE_OLLAMA=true            — ChatOllama pointing to localhost Ollama server
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
    """Gets a direct response from the LLM without RAG."""
    llm = get_llm()
    response = llm.invoke(question)
    return response.content
