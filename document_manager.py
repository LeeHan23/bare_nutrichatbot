import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)

def _get_psycopg2_dsn() -> str:
    """Strip sqlalchemy driver prefix for raw psycopg2 use."""
    return PGVECTOR_URL.replace("postgresql+psycopg2://", "postgresql://")


def delete_document_from_vectorstore(client_id: int, file_hash: str) -> bool:
    """
    Deletes all chunks with the given file_hash from the client's pgvector collection.
    Uses a direct SQL DELETE on cmetadata JSONB for efficiency.
    """
    collection_name = f"client_{client_id}_knowledge"
    try:
        with psycopg2.connect(_get_psycopg2_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM langchain_pg_embedding
                    WHERE collection_id = (
                        SELECT uuid FROM langchain_pg_collection WHERE name = %s
                    )
                    AND cmetadata->>'file_hash' = %s
                    """,
                    (collection_name, file_hash),
                )
                deleted = cur.rowcount
            conn.commit()
        print(f"Deleted {deleted} chunks for file_hash: {file_hash}")
        return deleted > 0
    except Exception as e:
        print(f"Error deleting document from vector store: {e}")
        return False


def get_document_chunk_count(client_id: int, file_hash: str) -> int:
    """
    Returns the number of chunks stored for a specific document.
    """
    collection_name = f"client_{client_id}_knowledge"
    try:
        with psycopg2.connect(_get_psycopg2_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM langchain_pg_embedding
                    WHERE collection_id = (
                        SELECT uuid FROM langchain_pg_collection WHERE name = %s
                    )
                    AND cmetadata->>'file_hash' = %s
                    """,
                    (collection_name, file_hash),
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"Error getting chunk count: {e}")
        return 0
