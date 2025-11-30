import os
import glob
import sys
import nltk

# Download necessary NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('taggers/averaged_perceptron_tagger')
except LookupError:
    nltk.download('averaged_perceptron_tagger')

# --- CONFIGURATION FOR INTERNAL DRIVE ---
# We write the DB to the Desktop to avoid locking issues on external drives
INTERNAL_DATA_PATH = os.path.expanduser("~/Desktop/nutribot_data")
if not os.path.exists(INTERNAL_DATA_PATH):
    os.makedirs(INTERNAL_DATA_PATH)
    print(f"📁 Created internal data directory: {INTERNAL_DATA_PATH}")

# Force paths to internal drive
os.environ["PERSISTENT_DISK_PATH"] = INTERNAL_DATA_PATH
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(INTERNAL_DATA_PATH, 'users.db')}"

print(f"💾 Database will be saved to: {INTERNAL_DATA_PATH}")

from sqlalchemy.orm import Session
import database as db
from process_client_docs import process_client_document

# --- Configuration ---
# Directory containing your PDF files
SOURCE_DIRECTORY = "./documents_to_ingest" 

# Client Name to associate these documents with
# Default to "LocalClient" if not provided via CLI
if len(sys.argv) > 1:
    CLIENT_NAME = sys.argv[1]
else:
    CLIENT_NAME = "LocalClient"

def ingest_local_documents():
    print(f"🚀 Starting local ingestion for client: {CLIENT_NAME}")
    
    # 1. Setup Database
    database = db.SessionLocal()
    
    # 2. Get or Create Client
    client = db.get_api_client_by_name(database, CLIENT_NAME)
    if not client:
        print(f"Creating new client: {CLIENT_NAME}")
        # Generate a dummy key for local use
        import secrets
        api_key = f"nbk_local_{secrets.token_hex(16)}"
        client = db.add_api_client(database, CLIENT_NAME, api_key)
        print(f"✅ Created client. API Key: {api_key}")
    else:
        print(f"Found existing client ID: {client.id}")
        
    # 3. Find Files (PDF, DOCX, TXT, CSV)
    if not os.path.exists(SOURCE_DIRECTORY):
        os.makedirs(SOURCE_DIRECTORY)
        print(f"⚠️ Created directory '{SOURCE_DIRECTORY}'. Please put your documents there and run again.")
        return

    extensions = ["*.pdf", "*.docx", "*.txt", "*.csv"]
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(SOURCE_DIRECTORY, ext)))
        
    if not files:
        print(f"❌ No documents found in '{SOURCE_DIRECTORY}'")
        return
        
    print(f"Found {len(files)} documents to process.")
    
    # 4. Process Each File
    for i, filepath in enumerate(files, 1):
        filename = os.path.basename(filepath)
        print(f"\n[{i}/{len(files)}] Processing: {filename}...")
        
        try:
            # Check for duplicates first
            from process_client_docs import calculate_file_hash
            file_hash = calculate_file_hash(filepath)
            existing_doc = db.get_document_by_hash(database, client.id, file_hash)
            
            if existing_doc:
                print(f"   ⏭️  Skipping (Already exists)")
                continue
                
            # Process
            file_size = os.path.getsize(filepath)
            result = process_client_document(client.id, filepath, filename)
            
            if result["status"] == "completed":
                # Save metadata
                db.add_document_metadata(
                    database,
                    client_id=client.id,
                    filename=filename,
                    file_hash=result["file_hash"],
                    file_size=file_size,
                    chunk_count=result["chunk_count"],
                    status="completed"
                )
                print(f"   ✅ Done! Added {result['chunk_count']} chunks.")
            else:
                print(f"   ❌ Failed: {result.get('error')}")
                
        except Exception as e:
            print(f"   ❌ Error processing file: {e}")
            
    print("\n🎉 Ingestion complete!")
    print(f"Vector store is located at: {os.path.join(INTERNAL_DATA_PATH, 'vectorstores_client', f'client_{client.id}')}")
    print(f"User DB is located at: {os.path.join(INTERNAL_DATA_PATH, 'users.db')}")

if __name__ == "__main__":
    ingest_local_documents()
