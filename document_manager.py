import os
from dotenv import load_dotenv
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings

load_dotenv()

# --- Path configuration ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_PATH = os.path.join(APP_DIR, "data")
PERSISTENT_DISK_PATH = os.environ.get("PERSISTENT_DISK_PATH", LOCAL_DATA_PATH)
CLIENT_STORES_DIR = os.path.join(PERSISTENT_DISK_PATH, "vectorstores_client")
EMBEDDING_MODEL = "text-embedding-3-small"

def delete_document_from_vectorstore(client_id: int, file_hash: str) -> bool:
    """
    Deletes all chunks associated with a specific document from the client's vector store.
    
    Args:
        client_id: The client's ID
        file_hash: The hash of the file to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    client_index_dir = os.path.join(CLIENT_STORES_DIR, f"client_{client_id}")
    
    if not os.path.exists(client_index_dir):
        print(f"No vector store found for client {client_id}")
        return False
    
    try:
        embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        vector_store = Chroma(
            collection_name=f"client_{client_id}_knowledge",
            embedding_function=embedding_function,
            persist_directory=client_index_dir
        )
        
        # Get all documents with matching file_hash
        # ChromaDB doesn't support direct deletion by metadata filter in older versions
        # We'll use get() with filter then delete()
        collection = vector_store._collection
        results = collection.get(
            where={"file_hash": file_hash}
        )
        
        if results and results['ids']:
            # Delete all matching document IDs
            collection.delete(ids=results['ids'])
            print(f"Deleted {len(results['ids'])} chunks for file_hash: {file_hash}")
            return True
        else:
            print(f"No chunks found with file_hash: {file_hash}")
            return False
            
    except Exception as e:
        print(f"Error deleting document from vector store: {e}")
        return False

def get_document_chunk_count(client_id: int, file_hash: str) -> int:
    """
    Gets the number of chunks for a specific document.
    
    Args:
        client_id: The client's ID
        file_hash: The hash of the file
        
    Returns:
        int: Number of chunks found
    """
    client_index_dir = os.path.join(CLIENT_STORES_DIR, f"client_{client_id}")
    
    if not os.path.exists(client_index_dir):
        return 0
    
    try:
        embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        vector_store = Chroma(
            collection_name=f"client_{client_id}_knowledge",
            embedding_function=embedding_function,
            persist_directory=client_index_dir
        )
        
        collection = vector_store._collection
        results = collection.get(
            where={"file_hash": file_hash}
        )
        
        return len(results['ids']) if results and results['ids'] else 0
            
    except Exception as e:
        print(f"Error getting chunk count: {e}")
        return 0
