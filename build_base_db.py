import os
import json
import time
import re
import logging
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import List

load_dotenv()

# Silence pdfminer's noisy color warnings before importing unstructured
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.ERROR)
logging.getLogger("pdfminer.layout").setLevel(logging.ERROR)
logging.getLogger("pdfminer.cmapdb").setLevel(logging.ERROR)
logging.getLogger("unstructured").setLevel(logging.WARNING)

from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document
from unstructured.partition.auto import partition
from unstructured.chunking.title import chunk_by_title
from unstructured.documents.elements import Header, Footer, PageBreak, Image, Formula

# --- Path configuration ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DOCS_DIR = os.environ.get(
    "BASE_DOCS_DIR",
    os.path.join(APP_DIR, "data", "base_docs"),
)
FILE_TRACKER_PATH = os.path.join(APP_DIR, "data", "file_tracker.json")
COLLECTION_NAME = "base_knowledge"
MAX_WORKERS = min(os.cpu_count() or 4, 4)
DB_BATCH_SIZE = 500
PER_FILE_TIMEOUT = 600  # 10 minutes max per file

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)

# filename -> MyHeartCoach Component slug (see taxonomy.py). Anything not
# listed here defaults to "nutrition" — the entire corpus today is
# nutrition-guideline PDFs. Add an entry when ingesting a new document set
# for a different component.
DOC_COMPONENT_OVERRIDES = {}


def _connection_string() -> str:
    url = PGVECTOR_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


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
    citation_pattern = re.findall(r'\([12]\d{3}\)|et al\.?', text)
    if len(citation_pattern) > 8 and len(text) < 1500:
        return True
    numbered_refs = re.findall(r'^\d+\.\s+[A-Z][a-z]+', text, re.MULTILINE)
    if len(numbered_refs) > 3 and len(text) < 2000:
        return True
    toc_lines = re.findall(r'^.{10,60}\s+\d{1,3}\s*$', text, re.MULTILINE)
    if len(toc_lines) > 4:
        return True
    return False


def filter_elements(elements):
    return [
        el for el in elements
        if not isinstance(el, (Header, Footer, PageBreak, Image, Formula))
    ]


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
        if filename.startswith("._") or filename == "image_annotations.csv" or filename == ".DS_Store":
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
    # Silence loggers in subprocess too
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    logging.getLogger("unstructured").setLevel(logging.WARNING)

    filename = os.path.basename(filepath)
    file_size_mb = os.path.getsize(filepath) / 1024 / 1024
    file_start = time.time()
    print(f"  [START] {filename} ({file_size_mb:.1f} MB)", flush=True)
    try:
        elements = partition(filename=filepath, strategy="fast", languages=["eng", "msa"])
        if not elements:
            print(f"  [RETRY hi_res] {filename}", flush=True)
            elements = partition(filename=filepath, strategy="hi_res", languages=["eng", "msa"])

        if not elements:
            print(f"  [WARN] No elements from {filename}", flush=True)
            return []

        elements = filter_elements(elements)
        chunks = chunk_by_title(elements, max_characters=1024, combine_text_under_n_chars=200)

        docs = []
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

            component = DOC_COMPONENT_OVERRIDES.get(filename, "nutrition")
            docs.append(Document(
                page_content=content,
                metadata={"source": filename, "title": title, "doc_components": [component]},
            ))

        elapsed = time.time() - file_start
        kept = len(docs)
        total = kept + skipped
        keep_pct = (kept / total * 100) if total > 0 else 0
        print(f"  [DONE] {filename}: {kept}/{total} chunks kept ({keep_pct:.0f}%) in {elapsed:.0f}s", flush=True)
        return docs
    except Exception as e:
        print(f"  [ERROR] {filename}: {e}", flush=True)
        return []


def build_base_database():
    start = time.time()
    print(f"--- Starting Base Knowledge Build ---", flush=True)
    print(f"Source directory: {BASE_DOCS_DIR}", flush=True)
    print(f"Per-file timeout: {PER_FILE_TIMEOUT}s", flush=True)

    files_to_process, tracker = get_files_to_process()

    if not files_to_process:
        print("No new or updated files to process.", flush=True)
        return

    print(f"Found {len(files_to_process)} file(s) to process with {MAX_WORKERS} workers.", flush=True)
    all_chunks = []
    timed_out_files = []

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_file, fp): fp for fp in files_to_process}
        for future in as_completed(futures):
            filepath = futures[future]
            filename = os.path.basename(filepath)
            try:
                chunks = future.result(timeout=PER_FILE_TIMEOUT)
                if chunks:
                    all_chunks.extend(chunks)
            except FuturesTimeoutError:
                print(f"  [TIMEOUT] {filename} exceeded {PER_FILE_TIMEOUT}s — skipping", flush=True)
                timed_out_files.append(filename)
                future.cancel()
            except Exception as e:
                print(f"  [EXCEPTION] {filename}: {e}", flush=True)

    if timed_out_files:
        print(f"\n[WARNING] {len(timed_out_files)} file(s) timed out: {timed_out_files}", flush=True)

    if not all_chunks:
        print("No content was generated. Aborting.", flush=True)
        return

    print(f"\nTotal clean chunks: {len(all_chunks)}. Embedding and storing in pgvector...", flush=True)

    from embeddings import get_embedding_function
    embedding_function = get_embedding_function()
    connection_string = _connection_string()

    for i in range(0, len(all_chunks), DB_BATCH_SIZE):
        batch = all_chunks[i: i + DB_BATCH_SIZE]
        batch_num = i // DB_BATCH_SIZE + 1
        total_batches = (len(all_chunks) + DB_BATCH_SIZE - 1) // DB_BATCH_SIZE
        print(f"  Storing batch {batch_num}/{total_batches} ({len(batch)} chunks)...", flush=True)
        PGVector.from_documents(
            documents=batch,
            embedding=embedding_function,
            collection_name=COLLECTION_NAME,
            connection_string=connection_string,
            pre_delete_collection=False,
            use_jsonb=True,
        )

    for fp in files_to_process:
        if os.path.basename(fp) not in timed_out_files:
            tracker[os.path.basename(fp)] = os.path.getmtime(fp)
    save_tracker(tracker)

    print(f"\nBuild complete in {time.time() - start:.1f}s ({len(all_chunks)} chunks stored)", flush=True)


if __name__ == "__main__":
    build_base_database()
