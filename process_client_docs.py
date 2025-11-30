import os
import hashlib
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
CLIENT_STORES_DIR = os.path.join(PERSISTENT_DISK_PATH, "vectorstores_client")
EMBEDDING_MODEL = "text-embedding-3-small"

def calculate_file_hash(filepath: str) -> str:
    """
    Calculate SHA256 hash of a file for deduplication.
    """
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def process_client_document(client_id: int, filepath: str, filename: str):
    """
    Processes a single uploaded document for a specific client and adds it to their
    personal, persistent vector store.
    
    Returns:
        dict: Contains file_hash, chunk_count, and status
    """
    from unstructured.partition.auto import partition
    from unstructured.chunking.title import chunk_by_title

    print(f"--- Processing document for client_id: {client_id} ---")
    
    client_index_dir = os.path.join(CLIENT_STORES_DIR, f"client_{client_id}")
    os.makedirs(client_index_dir, exist_ok=True)

    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL, max_retries=10)
    
    # Calculate file hash for deduplication
    file_hash = calculate_file_hash(filepath)
    
    all_chunks = []
    try:
        print(f"Partitioning and chunking: {filename}")
        # Try default strategy first (fast)
        try:
            elements = partition(filename=filepath)
        except Exception:
            elements = []

        # If empty, try hi_res (OCR)
        if not elements:
            print("   ⚠️  No text found with default strategy. Retrying with OCR (hi_res)...")
            # "msa" is Malay, "eng" is English
            elements = partition(filename=filepath, strategy="hi_res", languages=["eng", "msa"])
            
        chunks = chunk_by_title(elements, max_characters=1500)
        
        for chunk in chunks:
            title = chunk.metadata.get_element_orig_filename() if hasattr(chunk.metadata, 'get_element_orig_filename') else filename
            if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'title'):
                title = chunk.metadata.title
            
            # Tag chunks with document metadata for later deletion
            all_chunks.append(Document(
                page_content=str(chunk),
                metadata={
                    "source": filename,
                    "title": title,
                    "file_hash": file_hash  # Important for deletion
                }
            ))
            
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return {
            "file_hash": file_hash,
            "chunk_count": 0,
            "status": "failed",
            "error": str(e)
        }

    if not all_chunks:
        print("No content was generated from the document.")
        return {
            "file_hash": file_hash,
            "chunk_count": 0,
            "status": "failed",
            "error": "No content extracted"
        }

    print(f"Generated {len(all_chunks)} chunks to add to client's knowledge base.")

    # Initialize or load the client's personal ChromaDB and add the new chunks
    # Initialize or load the client's personal ChromaDB and add the new chunks
    vector_store = Chroma(
        collection_name=f"client_{client_id}_knowledge",
        embedding_function=embedding_function,
        persist_directory=client_index_dir
    )
    
    # Batch add documents to avoid hitting API token limits (max 300k tokens per request)
    BATCH_SIZE = 100
    total_chunks = len(all_chunks)
    print(f"Adding {total_chunks} chunks in batches of {BATCH_SIZE}...")
    
    for i in range(0, total_chunks, BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]
        try:
            vector_store.add_documents(batch)
            print(f"   - Added batch {i//BATCH_SIZE + 1}/{(total_chunks + BATCH_SIZE - 1)//BATCH_SIZE}")
        except Exception as e:
            print(f"   ❌ Error adding batch {i//BATCH_SIZE + 1}: {e}")
            # If a batch fails, we might want to stop or continue? 
            # For now, let's re-raise so the file is marked as failed
            raise e
    print(f"✅ Successfully added new knowledge to client {client_id}'s bot.")
    
    return {
        "file_hash": file_hash,
        "chunk_count": len(all_chunks),
        "status": "completed"
    }
