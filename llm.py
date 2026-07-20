import os
from dotenv import load_dotenv

load_dotenv()

# --- Feature flags ---
USE_CLARA = os.getenv("USE_CLARA", "false").lower() in ("true", "1", "yes")
USE_CLARA_COMPRESS = os.getenv("USE_CLARA_COMPRESS", "false").lower() in ("true", "1", "yes")
USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() in ("true", "1", "yes")
USE_AGENT_TOOLS = os.getenv("USE_AGENT_TOOLS", "false").lower() in ("true", "1", "yes")

# --- CLaRa config (main RAG model on Mac Studio) ---
CLARA_BASE_URL = os.getenv("CLARA_BASE_URL", "http://localhost:8001")

# --- Ollama config (small orchestration tasks on local GPU) ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Eval judge config (kept separate from the generation model above so the
# eval harness isn't grading a model's answers with that same model) ---
JUDGE_OLLAMA_MODEL = os.getenv("JUDGE_OLLAMA_MODEL", OLLAMA_MODEL)
JUDGE_OLLAMA_BASE_URL = os.getenv("JUDGE_OLLAMA_BASE_URL", OLLAMA_BASE_URL)

# --- OpenAI config (kept as optional emergency fallback only) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# --- Timeouts ---
# The public Cloudflare path is already observed to time out client-side at
# ~100s (see CLAUDE.md's WhatsApp/keep-alive notes). Option B stacks two
# sequential calls (compress -> generate) to the same Mac Studio tunnel, so
# their combined budget is kept comfortably under that ceiling: if the
# backend is going to fail, it fails fast enough that the response still
# lands before the client would have already given up, instead of the
# server silently grinding for minutes on a request nobody is waiting for
# anymore.
CLARA_COMPRESS_TIMEOUT_S = int(os.getenv("CLARA_COMPRESS_TIMEOUT_S", "40"))
OLLAMA_GENERATE_TIMEOUT_S = int(os.getenv("OLLAMA_GENERATE_TIMEOUT_S", "50"))
# Single-call path (CLaRa-primary, USE_CLARA=true) — nothing stacks after it,
# so it gets a bit more headroom, but still well under the old 120s.
CLARA_GENERATE_TIMEOUT_S = int(os.getenv("CLARA_GENERATE_TIMEOUT_S", "90"))

if not USE_OLLAMA and not OPENAI_API_KEY:
    raise EnvironmentError(
        "No orchestration LLM configured. Set USE_OLLAMA=true (recommended) "
        "or provide OPENAI_API_KEY in .env."
    )


def get_llm():
    """
    Returns the orchestration LLM (used by LangChain chains for small tasks
    like identify_target_disease, NOT for the main RAG response).
    Defaults to Ollama, falls back to OpenAI if Ollama is not enabled.
    """
    if USE_OLLAMA:
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,
            num_predict=512,
            keep_alive=-1,
            timeout=90,
        )
    else:
        from langchain_openai import ChatOpenAI
        kwargs = dict(
            model_name=OPENAI_MODEL,
            temperature=0.3,
            max_tokens=512,
            openai_api_key=OPENAI_API_KEY,
        )
        if OPENAI_BASE_URL:
            kwargs["openai_api_base"] = OPENAI_BASE_URL
        return ChatOpenAI(**kwargs)


def get_direct_llm_response(question: str) -> str:
    """Direct response from the orchestration LLM, no RAG.
    Used for small auxiliary tasks like disease identification."""
    try:
        llm = get_llm()
        response = llm.invoke(question)
        return response.content
    except Exception as e:
        print(f"[LLM error] get_direct_llm_response: {e}")
        return ""


def call_clara_api(prompt: str, documents: list = None) -> str:
    """Calls the remote CLaRa inference server (Mac Studio) for main RAG generation."""
    import requests
    payload = {
        "prompt": prompt,
        "max_tokens": 512,
        "temperature": 0.3,
        "documents": documents or []
    }
    try:
        resp = requests.post(f"{CLARA_BASE_URL}/generate", json=payload, timeout=CLARA_GENERATE_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json().get("answer", "")
    except Exception as e:
        print(f"[CLaRa API error] {e}")
        return ""


def call_clara_compress(documents: list, question: str = "", patient_context: str = "") -> str:
    """Calls CLaRa /compress to synthesise a structured clinical digest from retrieved docs.

    Returns a ~300-500 token digest with RECOMMENDATIONS / CAUTIONS / KEY NUMBERS sections.
    Returns "" on failure — caller should fall back to raw chunks.
    """
    import requests
    payload = {
        "documents": documents,
        "question": question,
        "patient_context": patient_context,
        "max_tokens": 500,
        "temperature": 0.1,
    }
    try:
        resp = requests.post(f"{CLARA_BASE_URL}/compress", json=payload, timeout=CLARA_COMPRESS_TIMEOUT_S)
        resp.raise_for_status()
        digest = resp.json().get("digest", "")
        if digest:
            print(f"[CLaRa compress] digest length={len(digest)} chars")
        return digest
    except Exception as e:
        print(f"[CLaRa compress error] {e}")
        return ""


def call_ollama_generate(prompt: str, max_tokens: int = 800) -> str:
    """Calls Ollama directly (not via LangChain) for full-response generation.

    Used by Option B after CLaRa produces the clinical digest.
    Larger token budget than get_direct_llm_response (800 vs 512).
    """
    import requests
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "num_predict": max_tokens,
            "keep_alive": -1,
        },
    }
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=OLLAMA_GENERATE_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        print(f"[Ollama generate error] {e}")
        return ""


def call_judge_llm(prompt: str, max_tokens: int = 10) -> str:
    """Calls the eval judge model (JUDGE_OLLAMA_MODEL/JUDGE_OLLAMA_BASE_URL),
    kept independent from the generation model so eval isn't self-graded."""
    import requests
    payload = {
        "model": JUDGE_OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": max_tokens,
            "keep_alive": -1,
        },
    }
    try:
        resp = requests.post(f"{JUDGE_OLLAMA_BASE_URL}/api/generate", json=payload, timeout=OLLAMA_GENERATE_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        print(f"[Judge LLM error] {e}")
        return ""
