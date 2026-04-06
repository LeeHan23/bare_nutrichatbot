import os
import json
import time
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List

load_dotenv()

from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document
from unstructured.partition.auto import partition
from unstructured.chunking.title import chunk_by_title

# --- Path configuration ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Source documents: configurable via env, defaulting to /mnt/ssd/documents_to_ingest
BASE_DOCS_DIR = os.environ.get(
    "BASE_DOCS_DIR",
    os.path.join(APP_DIR, "data", "base_docs"),
)
FILE_TRACKER_PATH = os.path.join(APP_DIR, "data", "file_tracker.json")
COLLECTION_NAME = "base_knowledge"
MAX_WORKERS = min(os.cpu_count() or 4, 4)
DB_BATCH_SIZE = 500

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)


def _connection_string() -> str:
    url = PGVECTOR_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def load_tracker() -> dict:
    if os.path.exists(FILE_TRACKER_PATH):
        with open(FILE_TRACKER_PATH, "r") as f:
            return json.load(f)
    return {}


def save_tracker(tracker: dict):
    os.makedirs(os.path.dirname(FILE_TRACKER_PATH), exist_ok=True)
    with open(FILE_TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=4)


def get_files_to_process():
    tracker = load_tracker()
    if not os.path.exists(BASE_DOCS_DIR):
        print(f"Error: BASE_DOCS_DIR '{BASE_DOCS_DIR}' not found.")
        return [], tracker

    files = []
    for filename in os.listdir(BASE_DOCS_DIR):
        # Skip macOS metadata files and non-documents
        if filename.startswith("._") or filename == "image_annotations.csv":
            continue
        filepath = os.path.join(BASE_DOCS_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        mtime = os.path.getmtime(filepath)
        if filename not in tracker or tracker[filename] < mtime:
            files.append(filepath)
    return files, tracker


def process_single_file(filepath: str) -> List[Document]:
    """Partition and chunk a single file. Runs in a subprocess."""
    filename = os.path.basename(filepath)
    print(f"  Processing: {filename}")
    try:
        elements = partition(filename=filepath, strategy="fast")
        if not elements:
            elements = partition(filename=filepath, strategy="hi_res", languages=["eng", "msa"])
        chunks = chunk_by_title(elements, max_characters=1500, combine_text_under_n_chars=500)
        docs = []
        for chunk in chunks:
            title = filename
            if hasattr(chunk, "metadata") and hasattr(chunk.metadata, "title"):
                title = chunk.metadata.title or filename
            docs.append(Document(
                page_content=str(chunk),
                metadata={"source": filename, "title": title},
            ))
        return docs
    except Exception as e:
        print(f"  Error processing {filename}: {e}")
        return []


def build_base_database():
    start = time.time()
    print("--- Starting Base Knowledge Build ---")
    print(f"Source directory: {BASE_DOCS_DIR}")

    files_to_process, tracker = get_files_to_process()

    if not files_to_process:
        print("No new or updated files to process. Base knowledge is up to date.")
        return

    print(f"Found {len(files_to_process)} file(s) to process with {MAX_WORKERS} workers.")
    all_chunks = []

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_file, fp): fp for fp in files_to_process}
        for future in as_completed(futures):
            try:
                chunks = future.result()
                if chunks:
                    all_chunks.extend(chunks)
                    print(f"  Got {len(chunks)} chunks from {os.path.basename(futures[future])}")
            except Exception as e:
                print(f"  Exception from {futures[future]}: {e}")

    if not all_chunks:
        print("No content was generated. Aborting.")
        return

    print(f"\nTotal chunks: {len(all_chunks)}. Embedding and storing in pgvector...")

    from embeddings import get_embedding_function
    embedding_function = get_embedding_function()
    connection_string = _connection_string()

    for i in range(0, len(all_chunks), DB_BATCH_SIZE):
        batch = all_chunks[i: i + DB_BATCH_SIZE]
        batch_num = i // DB_BATCH_SIZE + 1
        total_batches = (len(all_chunks) + DB_BATCH_SIZE - 1) // DB_BATCH_SIZE
        print(f"  Storing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        PGVector.from_documents(
            documents=batch,
            embedding=embedding_function,
            collection_name=COLLECTION_NAME,
            connection_string=connection_string,
            pre_delete_collection=False,
            use_jsonb=True,
        )

    # Update tracker
    for fp in files_to_process:
        tracker[os.path.basename(fp)] = os.path.getmtime(fp)
    save_tracker(tracker)

    print(f"\nBase knowledge build complete in {time.time() - start:.1f}s  ({len(all_chunks)} chunks stored)")


if __name__ == "__main__":
    build_base_database()
