import os
import sys

# Fix for ChromaDB sqlite version issues (must be before other imports)
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import uvicorn
import shutil
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Security, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import database as db
from dependencies import get_db, get_api_client
from website_chat_router import chat_router
from admin_router import router as admin_router
from process_client_docs import process_client_document, calculate_file_hash

# --- Load Environment Variables ---
load_dotenv()

# --- FastAPI App Initialization ---
# --- FastAPI App Initialization ---
app = FastAPI()

# Mount static images directory
try:
    images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "images")
    os.makedirs(images_dir, exist_ok=True)
    app.mount("/images", StaticFiles(directory=images_dir), name="images")
    print(f"✅ Mounted /images pointing to: {images_dir}")
except Exception as e:
    print(f"❌ Failed to mount /images: {e}")

@app.on_event("startup")
async def startup_event():
    """
    On startup, check if the persistent volume is empty.
    If so, seed it with the data from the Docker image.
    """
    data_dir = "data"
    seed_dir = "/app/data_seed" # Absolute path in Docker container
    
    # Only run if seed directory exists (i.e., in Docker)
    if os.path.exists(seed_dir):
        print(f"🔍 Checking if seeding is needed from {seed_dir}...")
        
        # Ensure data dir exists
        os.makedirs(data_dir, exist_ok=True)
        
        # Check for users.db
        target_db = os.path.join(data_dir, "users.db")
        if not os.path.exists(target_db):
            print("📦 Seeding users.db...")
            shutil.copy2(os.path.join(seed_dir, "users.db"), target_db)
            
        # Check for vectorstores
        seed_vs = os.path.join(seed_dir, "vectorstores_client")
        target_vs = os.path.join(data_dir, "vectorstores_client")
        
        if os.path.exists(seed_vs) and not os.path.exists(target_vs):
            print("📦 Seeding vectorstores...")
            shutil.copytree(seed_vs, target_vs, dirs_exist_ok=True)
            
        print("✅ Startup checks complete.")

# --- CORS Middleware ---
origins = ["*"] # Allow all for a public API, or restrict as needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "NutriBot API is running"}

# --- API Routers ---
# Admin router (no authentication required - uses password in the form)
app.include_router(
    admin_router,
    prefix="/admin",
    tags=["Admin"]
)

# Client portal router (session-based authentication)
from client_portal_router import router as portal_router
app.include_router(
    portal_router,
    prefix="/portal",
    tags=["Client Portal"]
)

# The chat router endpoints handle authentication individually
app.include_router(
    chat_router, 
    prefix="/chat", 
    tags=["Chat"]
)

# --- NEW: Batch File Upload Endpoint ---
@app.post("/upload_documents/", tags=["Document Upload"])
async def upload_documents(
    files: list[UploadFile] = File(...),
    client = Depends(get_api_client),
    database: Session = Depends(get_db)
):
    """
    Endpoint for B2B clients to upload multiple documents for their knowledge base.
    Requires a valid 'X-API-Key' in the header.
    """
    from process_client_docs import process_client_document, calculate_file_hash
    
    # Create a temporary directory to store uploaded files
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    results = []
    
    for file in files:
        temp_filepath = os.path.join(temp_dir, file.filename)
        
        try:
            # Save the uploaded file temporarily
            with open(temp_filepath, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Calculate file hash for deduplication
            file_hash = calculate_file_hash(temp_filepath)
            file_size = os.path.getsize(temp_filepath)
            
            # Check if document already exists for this client
            existing_doc = db.get_document_by_hash(database, client.id, file_hash)
            if existing_doc:
                results.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "message": "Document already exists (duplicate)"
                })
                os.remove(temp_filepath)
                continue
            
            # Process the document
            process_result = process_client_document(
                client_id=client.id, 
                filepath=temp_filepath, 
                filename=file.filename
            )
            
            # Add document metadata to database
            doc_metadata = db.add_document_metadata(
                database,
                client_id=client.id,
                filename=file.filename,
                file_hash=process_result["file_hash"],
                file_size=file_size,
                chunk_count=process_result["chunk_count"],
                status=process_result["status"]
            )
            
            results.append({
                "filename": file.filename,
                "document_id": doc_metadata.id,
                "status": process_result["status"],
                "chunk_count": process_result["chunk_count"],
                "file_size": file_size
            })
            
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": str(e)
            })
        
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
    
    return {
        "client_name": client.client_name,
        "total_files": len(files),
        "results": results
    }

# --- NEW: Document Management Endpoints ---
@app.get("/documents/", tags=["Document Management"])
async def list_documents(
    client = Depends(get_api_client),
    database: Session = Depends(get_db)
):
    """
    List all uploaded documents for the authenticated client.
    """
    documents = db.get_client_documents(database, client.id)
    
    return {
        "client_name": client.client_name,
        "total_documents": len(documents),
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "upload_date": doc.upload_date.isoformat(),
                "file_size": doc.file_size,
                "chunk_count": doc.chunk_count,
                "status": doc.status
            }
            for doc in documents
        ]
    }

@app.get("/documents/{document_id}", tags=["Document Management"])
async def get_document_details(
    document_id: int,
    client = Depends(get_api_client),
    database: Session = Depends(get_db)
):
    """
    Get details for a specific document.
    """
    doc = db.get_document_by_id(database, document_id, client.id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "id": doc.id,
        "filename": doc.filename,
        "upload_date": doc.upload_date.isoformat(),
        "file_size": doc.file_size,
        "chunk_count": doc.chunk_count,
        "status": doc.status,
        "file_hash": doc.file_hash
    }

@app.delete("/documents/{document_id}", tags=["Document Management"])
async def delete_document(
    document_id: int,
    client = Depends(get_api_client),
    database: Session = Depends(get_db)
):
    """
    Delete a document from both the database and vector store.
    """
    from document_manager import delete_document_from_vectorstore
    
    # Get document to retrieve file_hash
    doc = db.get_document_by_id(database, document_id, client.id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete from vector store first
    vector_deleted = delete_document_from_vectorstore(client.id, doc.file_hash)
    
    # Delete metadata from database
    db_deleted = db.delete_document_metadata(database, document_id, client.id)
    
    if not db_deleted:
        raise HTTPException(status_code=500, detail="Failed to delete document metadata")
    
    return {
        "status": "success",
        "message": f"Document '{doc.filename}' deleted successfully",
        "vector_store_deleted": vector_deleted,
        "chunks_removed": doc.chunk_count
    }

# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"message": "Welcome to the Nutrition Chatbot API"}

# --- Main Entry Point ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)