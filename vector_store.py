import os
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.retrievers import MergerRetriever # <- New Import

# --- Load environment variables ---
load_dotenv()

# --- UNIFIED PATH CONFIGURATION ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_PATH = os.path.join(APP_DIR, "data")
PERSISTENT_DISK_PATH = os.environ.get("PERSISTENT_DISK_PATH", LOCAL_DATA_PATH)

# --- Vector Store Paths ---
BASE_INDEX_DIR = os.path.join(PERSISTENT_DISK_PATH, "vectorstore_base")
CLIENT_STORES_DIR = os.path.join(PERSISTENT_DISK_PATH, "vectorstores_client")

# --- Embedding Model ---
EMBEDDING_MODEL = "text-embedding-3-small"

def get_retriever(client_id: str):
    """
    Creates a hybrid retriever that searches both the base knowledge base
    and the specific client's private knowledge base.
    
    Args:
        client_id: The ID of the B2B client (from ApiClient.id)
    """
    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    
    # 1. Load the foundational knowledge base retriever
    base_db = Chroma(
        persist_directory=BASE_INDEX_DIR,
        embedding_function=embedding_function,
        collection_name="base_knowledge"
    )
    base_retriever = base_db.as_retriever(search_kwargs={"k": 3})

    # 2. Load the client-specific knowledge base if it exists
    client_index_dir = os.path.join(CLIENT_STORES_DIR, f"client_{client_id}")
    
    if os.path.exists(client_index_dir):
        print(f"Loading custom knowledge base for client_id: {client_id}")
        client_db = Chroma(
            persist_directory=client_index_dir,
            embedding_function=embedding_function,
            collection_name=f"client_{client_id}_knowledge"
        )
        client_retriever = client_db.as_retriever(search_kwargs={"k": 3})
        
        # 3. Create a MergerRetriever to search both simultaneously
        hybrid_retriever = MergerRetriever(retrievers=[base_retriever, client_retriever])
        return hybrid_retriever
    else:
        # If the client has no custom knowledge, return only the base retriever
        print(f"No custom knowledge base found for client_id: {client_id}. Using base knowledge only.")
        return base_retriever