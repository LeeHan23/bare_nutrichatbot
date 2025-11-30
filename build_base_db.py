import os
import json
import time
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict

# --- Load environment variables from .env file FIRST ---
load_dotenv()

from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.docstore.document import Document
from unstructured.partition.auto import partition
from unstructured.chunking.title import chunk_by_title

# --- UNIFIED PATH CONFIGURATION ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_PATH = os.path.join(APP_DIR, "data")
PERSISTENT_DISK_PATH = os.environ.get("PERSISTENT_DISK_PATH", LOCAL_DATA_PATH)

# ========= CONFIGURATION =========
BASE_DOCS_DIR = os.path.join(APP_DIR, "data", "base_docs")
BASE_INDEX_DIR = os.path.join(PERSISTENT_DISK_PATH, "vectorstore_base")
FILE_TRACKER_PATH = os.path.join(LOCAL_DATA_PATH, "file_tracker.json")
COLLECTION_NAME = "base_knowledge"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_WORKERS = os.cpu_count() or 4
# NEW: Define a safe batch size for adding documents to ChromaDB
DB_BATCH_SIZE = 4000 
# =================================

def load_processed_files_tracker():
    if os.path.exists(FILE_TRACKER_PATH):
        with open(FILE_TRACKER_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_processed_files_tracker(tracker):
    with open(FILE_TRACKER_PATH, 'w') as f:
        json.dump(tracker, f, indent=4)

def get_files_to_process():
    tracker = load_processed_files_tracker()
    files_to_process = []
    if not os.path.exists(BASE_DOCS_DIR):
        print(f"Error: The directory '{BASE_DOCS_DIR}' was not found.")
        return [], tracker

    for filename in os.listdir(BASE_DOCS_DIR):
        filepath = os.path.join(BASE_DOCS_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        modification_time = os.path.getmtime(filepath)
        if filename not in tracker or tracker[filename] < modification_time:
            files_to_process.append(filepath)
    return files_to_process, tracker

def process_single_file(filepath: str) -> List[Document]:
    """
    Processes a single document file: partitions, chunks, and creates Document objects.
    This function is designed to be run in a separate process.
    """
    print(f"Processing: {os.path.basename(filepath)}")
    try:
        elements = partition(filename=filepath, strategy="fast")
        chunks = chunk_by_title(elements, max_characters=1500, combine_text_under_n_chars=500)
        
        langchain_docs = []
        for chunk in chunks:
            title = chunk.metadata.filename
            if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'title'):
                title = chunk.metadata.title
            langchain_docs.append(Document(
                page_content=str(chunk),
                metadata={"source": os.path.basename(filepath), "title": title}
            ))
        return langchain_docs
    except Exception as e:
        print(f"Error processing {os.path.basename(filepath)}: {e}")
        return []

def build_base_database():
    start_time = time.time()
    print("--- Starting Knowledge Base Update ---")

    files_to_process, tracker = get_files_to_process()

    if not files_to_process:
        print("No new or updated files to process. Knowledge base is up to date.")
        return

    print(f"Detected {len(files_to_process)} new/updated documents. Starting parallel processing with {MAX_WORKERS} workers.")
    all_chunks = []

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_single_file, filepath): filepath for filepath in files_to_process}
        for future in as_completed(future_to_file):
            try:
                chunks_from_file = future.result()
                if chunks_from_file:
                    all_chunks.extend(chunks_from_file)
            except Exception as exc:
                print(f'File {future_to_file[future]} generated an exception: {exc}')

    if not all_chunks:
        print("No content was generated from the new files. Aborting update.")
        return

    print(f"Generated {len(all_chunks)} new chunks. Now creating embeddings and adding to the database in batches...")

    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL, max_retries=10)
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embedding_function,
        persist_directory=BASE_INDEX_DIR
    )
    
    # --- UPDATED LOGIC: Add documents in batches ---
    for i in range(0, len(all_chunks), DB_BATCH_SIZE):
        batch = all_chunks[i:i + DB_BATCH_SIZE]
        vector_store.add_documents(batch)
        print(f"Added batch {i//DB_BATCH_SIZE + 1} of {len(all_chunks)//DB_BATCH_SIZE + 1} to the vector store.")
    
    print(f"Successfully added {len(all_chunks)} new chunks to the vector store.")

    for filepath in files_to_process:
        tracker[os.path.basename(filepath)] = os.path.getmtime(filepath)
    save_processed_files_tracker(tracker)

    end_time = time.time()
    print(f"\n✅ Knowledge base update complete! Time taken: {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    build_base_database()