import os
import json
from dotenv import load_dotenv
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.docstore.document import Document

# --- Load environment variables ---
load_dotenv()

# --- UNIFIED PATH CONFIGURATION ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_PATH = os.path.join(APP_DIR, "data")
PERSISTENT_DISK_PATH = os.environ.get("PERSISTENT_DISK_PATH", LOCAL_DATA_PATH)
USER_STORES_DIR = os.path.join(PERSISTENT_DISK_PATH, "vectorstores_user")
EMBEDDING_MODEL = "text-embedding-3-small"

def process_user_document(user_id: str, filepath: str):
    """
    Processes a single uploaded document for a specific user and adds it to their
    personal, persistent vector store.
    """

    from unstructured.partition.auto import partition
    from unstructured.chunking.title import chunk_by_title

    print(f"--- Processing document for user_id: {user_id} ---")
    
    user_index_dir = os.path.join(USER_STORES_DIR, f"user_{user_id}")
    os.makedirs(user_index_dir, exist_ok=True) # Ensure the user's directory exists

    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL, max_retries=10)
    
    all_chunks = []
    try:
        filename = os.path.basename(filepath)
        print(f"Partitioning and chunking: {filename}")
        elements = partition(filename=filepath)
        chunks = chunk_by_title(elements, max_characters=1500, combine_under_n_chars=500)
        
        for chunk in chunks:
            title = chunk.metadata.get_element_orig_filename()
            if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'title'):
                title = chunk.metadata.title
            all_chunks.append(Document(
                page_content=str(chunk),
                metadata={"source": filename, "title": title}
            ))
            
    except Exception as e:
        print(f"Error processing {os.path.basename(filepath)}: {e}")
        return

    if not all_chunks:
        print("No content was generated from the document. Aborting.")
        return

    print(f"Generated {len(all_chunks)} chunks to add to user's knowledge base.")

    # Initialize or load the user's personal ChromaDB and add the new chunks
    vector_store = Chroma(
        collection_name=f"user_{user_id}_knowledge",
        embedding_function=embedding_function,
        persist_directory=user_index_dir
    )
    
    vector_store.add_documents(all_chunks)
    print(f"✅ Successfully added new knowledge to user {user_id}'s bot.")