import os
import shutil
from dotenv import load_dotenv

load_dotenv()

from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.document_loaders import PyMuPDFLoader, Docx2txtLoader
from fastapi import UploadFile
from uploader import save_uploaded_file_as_text

# (Path configurations and other constants remain the same)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_PATH = os.path.join(APP_DIR, "data")
PERSISTENT_DISK_PATH = os.environ.get("PERSISTENT_DISK_PATH", LOCAL_DATA_PATH)
USER_DB_PATH = os.path.join(PERSISTENT_DISK_PATH, "chroma_db") 
BASE_DB_PATH = os.path.join(PERSISTENT_DISK_PATH, "vectorstore_base")
USER_COLLECTION_NAME = "user_knowledge"
BASE_COLLECTION_NAME = "base_knowledge"
PROMOS_PATH = os.path.join(APP_DIR, "data", "promos")
INSTRUCTIONS_PATH = os.path.join(APP_DIR, "data", "instructions")

# --- UPDATED: Function now accepts and processes tags ---
def add_document_to_base_db(doc_path: str, tags: str = ""):
    if not os.path.exists(doc_path): return False
    if not os.path.exists(BASE_DB_PATH): return False

    print(f"--- Starting incremental update for: {os.path.basename(doc_path)} with tags: '{tags}' ---")
    try:
        if doc_path.endswith(".pdf"):
            loader = PyMuPDFLoader(doc_path)
        elif doc_path.endswith(".docx"):
            loader = Docx2txtLoader(doc_path)
        else:
            return False
            
        documents = loader.load()
        if not documents: return False

        # Add the tags to the metadata of each document chunk
        for doc in documents:
            doc.metadata["tags"] = tags

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(documents)
        if not chunks: return False

        embedding_function = OpenAIEmbeddings(model="text-embedding-ada-002")
        vector_store = Chroma(
            persist_directory=BASE_DB_PATH,
            embedding_function=embedding_function,
            collection_name=BASE_COLLECTION_NAME
        )
        vector_store.add_documents(chunks)
        
        print("✅ Incremental update complete.")
        return True
    except Exception as e:
        print(f"An error occurred during the incremental update: {e}")
        return False

# (The rest of the functions in this file remain the same)
def build_user_database(user_id: str, uploaded_files: list, status_callback=None):
    if not user_id:
        if status_callback: status_callback("Error: A User ID must be provided.")
        return

    user_db_path = os.path.join(USER_DB_PATH, user_id)
    if status_callback: status_callback(f"Preparing to build knowledge base for user '{user_id}'...")

    if os.path.exists(user_db_path):
        if status_callback: status_callback("Clearing old custom knowledge base...")
        shutil.rmtree(user_db_path)
    
    os.makedirs(user_db_path, exist_ok=True)
    
    all_docs = []
    temp_dir = os.path.join(user_db_path, "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)

    for file_obj in uploaded_files:
        try:
            temp_file_path = os.path.join(temp_dir, file_obj.name)
            
            with open(temp_file_path, "wb") as f:
                f.write(file_obj.getbuffer())

            if temp_file_path.endswith(".docx"):
                loader = Docx2txtLoader(temp_file_path)
            elif temp_file_path.endswith(".pdf"):
                 loader = PyMuPDFLoader(temp_file_path)
            else:
                continue

            all_docs.extend(loader.load())
        except Exception as e:
            if status_callback: status_callback(f"Error loading file {file_obj.name}: {e}")
            continue
    
    shutil.rmtree(temp_dir)

    if not all_docs:
        if status_callback: status_callback("No documents found to process.")
        return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(all_docs)
    if status_callback: status_callback(f"Split documents into {len(chunks)} chunks.")

    if chunks:
        if status_callback: status_callback("Embedding documents...")
        embedding_function = OpenAIEmbeddings(model="text-embedding-ada-002")
        Chroma.from_documents(
            documents=chunks,
            embedding=embedding_function,
            persist_directory=user_db_path,
            collection_name=USER_COLLECTION_NAME
        )
        if status_callback: status_callback("✅ Training complete!")
    else:
        if status_callback: status_callback("No content found in documents.")

def save_instruction_file(user_id: str, uploaded_file: UploadFile):
    if not user_id or not uploaded_file: return None
    user_instructions_dir = os.path.join(INSTRUCTIONS_PATH, str(user_id))
    os.makedirs(user_instructions_dir, exist_ok=True)
    try:
        saved_path = save_uploaded_file_as_text(uploaded_file, user_instructions_dir)
        return saved_path
    except Exception as e:
        print(f"Error saving instruction file for user '{user_id}': {e}")
        return None

def _get_latest_file_content(directory: str) -> str:
    try:
        if not os.path.exists(directory): return ""
        files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".txt")]
        if not files: return ""
        latest_file = max(files, key=os.path.getmtime)
        with open(latest_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error reading from {directory}: {e}")
        return ""

def get_prompts(user_id: str = None) -> tuple[str, str]:
    instructions = ""
    if user_id:
        user_instructions_dir = os.path.join(INSTRUCTIONS_PATH, str(user_id))
        if os.path.exists(user_instructions_dir):
            instructions = _get_latest_file_content(user_instructions_dir)
    if not instructions:
        instructions = _get_latest_file_content(INSTRUCTIONS_PATH)
    promotions = _get_latest_file_content(PROMOS_PATH)
    if not instructions:
        instructions = "You are a helpful general assistant."
    if not promotions:
        promotions = "There are no special promotions at this time."
    full_instructions = f"{instructions}\n\n[LATEST PROMOTIONS & OFFERS]\n{promotions}"
    return full_instructions, ""

