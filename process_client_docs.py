import os
import hashlib
from dotenv import load_dotenv
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document
from embeddings import get_embedding_function

load_dotenv()

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)

def _connection_string() -> str:
    url = PGVECTOR_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def calculate_file_hash(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            sha256.update(block)
    return sha256.hexdigest()


def process_client_document(client_id: int, filepath: str, filename: str) -> dict:
    """
    Processes a single uploaded document for a B2B client and adds it to their
    pgvector collection.
    """
    from unstructured.partition.auto import partition
    from unstructured.chunking.title import chunk_by_title

    print(f"--- Processing document for client_id: {client_id} ---")

    file_hash = calculate_file_hash(filepath)
    collection_name = f"client_{client_id}_knowledge"

    all_chunks = []
    try:
        print(f"Partitioning: {filename}")
        try:
            elements = partition(filename=filepath)
        except Exception:
            elements = []

        if not elements:
            print("   No text found with default strategy. Retrying with OCR (hi_res)...")
            elements = partition(filename=filepath, strategy="hi_res", languages=["eng", "msa"])

        chunks = chunk_by_title(elements, max_characters=1500)
        for chunk in chunks:
            title = filename
            if hasattr(chunk, "metadata") and hasattr(chunk.metadata, "title"):
                title = chunk.metadata.title or filename
            all_chunks.append(Document(
                page_content=str(chunk),
                metadata={"source": filename, "title": title, "file_hash": file_hash},
            ))

    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return {"file_hash": file_hash, "chunk_count": 0, "status": "failed", "error": str(e)}

    if not all_chunks:
        return {"file_hash": file_hash, "chunk_count": 0, "status": "failed", "error": "No content extracted"}

    print(f"Generated {len(all_chunks)} chunks. Adding to pgvector collection '{collection_name}'...")

    embedding_function = get_embedding_function()
    BATCH_SIZE = 100

    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i: i + BATCH_SIZE]
        try:
            PGVector.from_documents(
                documents=batch,
                embedding=embedding_function,
                collection_name=collection_name,
                connection_string=_connection_string(),
                pre_delete_collection=False,
                use_jsonb=True,
            )
            print(f"   - Added batch {i // BATCH_SIZE + 1}/{(len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE}")
        except Exception as e:
            print(f"   Error adding batch {i // BATCH_SIZE + 1}: {e}")
            raise

    print(f"Successfully added {len(all_chunks)} chunks to client {client_id}'s knowledge base.")
    return {"file_hash": file_hash, "chunk_count": len(all_chunks), "status": "completed"}
