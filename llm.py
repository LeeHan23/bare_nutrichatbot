import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# --- Validate Environment Variable ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY environment variable not found. Please set it in your .env file.")

# --- Language Model Initialization ---
def get_llm():
    """
    Initializes and returns the ChatOpenAI model instance.

    This function is configured to use a more powerful model (gpt-4-turbo)
    for enhanced reasoning and interpretation, which is crucial for handling
    complex patient scenarios.
    
    Returns:
        An instance of ChatOpenAI configured with the upgraded model.
    """
    try:
        # UPGRADE: Using gpt-4-turbo for superior reasoning, synthesis,
        # and ability to follow complex instructions. This is key for
        # providing dietitian-level interpretations.
        llm = ChatOpenAI(
            model_name="gpt-4-turbo",
            temperature=0.5, # Lower temperature for more factual, less creative responses
            max_tokens=1500, # Increased token limit for more detailed analysis
            openai_api_key=OPENAI_API_KEY
        )
        return llm
    except Exception as e:
        print(f"Error initializing ChatOpenAI model: {e}")
        # This will prevent the application from starting if the LLM can't be initialized
        raise

def get_direct_llm_response(question: str) -> str:
    """
    Gets a direct response from the LLM wihtout RAG
    """
    llm = get_llm()
    response = llm.predict(question)
    return response