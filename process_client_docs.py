import os
import re
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


FRONT_MATTER_PATTERNS = [
    r'^statement of intent\b', r'^review of the guideline\b', r'^message from\b',
    r'^foreword\b', r'^preface\b', r'^acknowledg(e?)ments?\b',
    r'^table of contents\b', r'^list of (figures|tables|abbreviations|contributors)\b',
    r'^expert (working )?committee\b', r'^contributors?\b', r'^contents\b',
    r'^index\b', r'^references?\b', r'^bibliography\b', r'^appendix\b',
    r'^copyright\b', r'^disclaimer\b', r'^isbn\b', r'^published by\b',
]
FRONT_MATTER_REGEX = re.compile("|".join(FRONT_MATTER_PATTERNS), re.IGNORECASE)


def is_junk_chunk(text: str) -> bool:
    text = text.strip()
    if len(text) < 150:
        return True
    lines = [l for l in text.split('\n') if l.strip()]
    if not lines:
        return True
    first_line = lines[0].strip()
    if FRONT_MATTER_REGEX.match(first_line):
        return True
    if FRONT_MATTER_REGEX.search(text[:200]) and len(text) < 500:
        return True
    short_lines = sum(1 for l in lines if len(l.strip()) < 80)
    if len(lines) > 5 and short_lines / len(lines) > 0.7:
        return True
    alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
    if alpha_ratio < 0.5:
        return True
    dot_lines = sum(1 for l in lines if l.count('.') > 5 and len(l.strip()) < 100)
    if len(lines) > 3 and dot_lines / len(lines) > 0.4:
        return True
    if 'isbn' in text.lower()[:200] and len(text) < 600:
        return True
    # Catch author-year citations: (2019), et al.
    citation_pattern = re.findall(r'\([12]\d{3}\)|et al\.?', text)
    if len(citation_pattern) > 8 and len(text) < 1500:
        return True

    # Catch numbered bibliography entries: "153. Piepoli MF..." or "1. Smith J..."
    numbered_refs = re.findall(r'^\d+\.\s+[A-Z][a-z]+', text, re.MULTILINE)
    if len(numbered_refs) > 3 and len(text) < 2000:
        return True

    # Catch TOC lines with page numbers at end: "Introduction 1"
    toc_lines = re.findall(r'^.{10,60}\s+\d{1,3}\s*$', text, re.MULTILINE)
    if len(toc_lines) > 4:
        return True

    return False


def process_client_document(client_id: int, filepath: str, filename: str) -> dict:
    """Processes a single uploaded document for a B2B client with strong junk filtering."""
    from unstructured.partition.auto import partition
    from unstructured.chunking.title import chunk_by_title
    from unstructured.documents.elements import Header, Footer, PageBreak, Image, Formula

    print(f"--- Processing document for client_id: {client_id} ---")

    file_hash = calculate_file_hash(filepath)
    collection_name = f"client_{client_id}_knowledge"

    all_chunks = []
    try:
        print(f"Partitioning: {filename}")
        try:
            elements = partition(filename=filepath, strategy="fast", languages=["eng", "msa"])
        except Exception:
            elements = []

        if not elements:
            print("   Fast yielded nothing. Retrying with hi_res...")
            elements = partition(filename=filepath, strategy="hi_res", languages=["eng", "msa"])

        if not elements:
            return {"file_hash": file_hash, "chunk_count": 0, "status": "failed", "error": "No elements extracted"}

        elements = [
            el for el in elements
            if not isinstance(el, (Header, Footer, PageBreak, Image, Formula))
        ]

        chunks = chunk_by_title(elements, max_characters=1024, combine_text_under_n_chars=200)

        skipped = 0
        for chunk in chunks:
            content = str(chunk).replace("\x00", "").strip()
            if not content:
                continue
            if is_junk_chunk(content):
                skipped += 1
                continue

            title = filename
            if hasattr(chunk, "metadata") and hasattr(chunk.metadata, "title"):
                title = chunk.metadata.title or filename

            all_chunks.append(Document(
                page_content=content,
                metadata={"source": filename, "title": title, "file_hash": file_hash},
            ))

        if skipped > 0:
            print(f"   Filtered out {skipped} junk chunks")

    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return {"file_hash": file_hash, "chunk_count": 0, "status": "failed", "error": str(e)}

    if not all_chunks:
        return {"file_hash": file_hash, "chunk_count": 0, "status": "failed", "error": "No content extracted"}

    print(f"Generated {len(all_chunks)} clean chunks. Adding to pgvector collection '{collection_name}'...")

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
