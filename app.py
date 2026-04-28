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
from fastapi.responses import HTMLResponse
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
    On startup: create DB tables, then seed from Docker image if needed.
    """
    db.create_db_and_tables()

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

@app.get("/", response_class=HTMLResponse)
async def home():
    """Patient app — login, verify, chat."""
    _app_html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patient_app.html")
    with open(_app_html, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/dev", response_class=HTMLResponse)
async def dev_ui():
    """Legacy test UI for developers."""
    return HTMLResponse(content=_TEST_UI_HTML)


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "NutriBot API is running"}


_TEST_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>NutriBot Test Interface</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#f0f4f8;color:#1a202c;min-height:100vh}
  header{background:#2d6a4f;color:#fff;padding:16px 24px;display:flex;align-items:center;gap:12px}
  header h1{font-size:1.25rem;font-weight:700}
  header span{font-size:.85rem;opacity:.8}
  .container{max-width:860px;margin:24px auto;padding:0 16px;display:flex;flex-direction:column;gap:20px}
  .card{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.1);padding:20px}
  .card h2{font-size:1rem;font-weight:600;color:#2d6a4f;margin-bottom:14px;border-bottom:1px solid #e2e8f0;padding-bottom:8px}
  label{display:block;font-size:.8rem;font-weight:600;color:#4a5568;margin-bottom:4px;margin-top:10px}
  input,select,textarea{width:100%;padding:9px 12px;border:1px solid #cbd5e0;border-radius:8px;font-size:.9rem;background:#f7fafc}
  input:focus,select:focus,textarea:focus{outline:none;border-color:#2d6a4f;background:#fff}
  button{background:#2d6a4f;color:#fff;border:none;padding:10px 20px;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer;margin-top:12px}
  button:hover{background:#1b4332}
  button.sec{background:#e2e8f0;color:#2d3748}
  button.sec:hover{background:#cbd5e0}
  .output{margin-top:14px;background:#f7fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;min-height:60px;font-size:.85rem;white-space:pre-wrap;max-height:300px;overflow-y:auto}
  .chat-box{display:flex;flex-direction:column;gap:10px;max-height:380px;overflow-y:auto;padding:4px}
  .msg{padding:10px 14px;border-radius:12px;max-width:80%;font-size:.9rem;line-height:1.5}
  .msg.user{background:#2d6a4f;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
  .msg.bot{background:#edf2f7;color:#1a202c;align-self:flex-start;border-bottom-left-radius:4px}
  .msg.bot.loading{color:#718096;font-style:italic}
  .chat-input-row{display:flex;gap:8px;margin-top:10px}
  .chat-input-row input{flex:1;margin:0}
  .chat-input-row button{margin:0;padding:10px 16px}
  .tag{display:inline-block;background:#c6f6d5;color:#22543d;border-radius:20px;padding:2px 10px;font-size:.75rem;margin:2px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  @media(max-width:600px){.grid2{grid-template-columns:1fr}}
  .patient-card{border:1px solid #e2e8f0;border-radius:8px;padding:12px;cursor:pointer;transition:.15s}
  .patient-card:hover{border-color:#2d6a4f;background:#f0fdf4}
  .patient-card.selected{border-color:#2d6a4f;background:#f0fdf4;box-shadow:0 0 0 2px #2d6a4f}
  .patient-name{font-weight:600;font-size:.95rem}
  .patient-meta{font-size:.78rem;color:#718096;margin-top:2px}
  #status{font-size:.8rem;color:#e53e3e;margin-top:6px;min-height:18px}
</style>
</head>
<body>
<header>
  <div>
    <h1>NutriBot Test Interface</h1>
    <span>Nutritional AI Assistant — Tester Preview</span>
  </div>
</header>

<div class="container">

  <!-- Step 1: API Key (clinic setup) -->
  <div class="card" id="apiSection">
    <h2>Step 1 — Clinic API Key</h2>
    <label>X-API-Key</label>
    <input id="apiKey" type="password" placeholder="nbk_live_..." />
    <div style="display:flex;gap:8px">
      <button onclick="confirmApiKey()">Continue</button>
      <button class="sec" onclick="document.getElementById('apiKey').type = document.getElementById('apiKey').type==='password'?'text':'password'">Show / Hide</button>
    </div>
    <div id="status"></div>
  </div>

  <!-- Step 2: Patient login by name -->
  <div class="card" id="loginSection" style="display:none">
    <h2>Step 2 — Patient Login</h2>
    <p style="font-size:.85rem;color:#4a5568;margin-bottom:12px">Enter your full name as it appears on your MyKad (IC). If you are a new patient, a profile will be created for you.</p>

    <!-- Name input (shown first) -->
    <div id="nameInputSection">
      <label>Full Name (as per IC)</label>
      <input id="patientName" type="text" placeholder="e.g. Ahmad Fadzillah bin Roslan" onkeydown="if(event.key==='Enter')loginPatient()" />
      <button onclick="loginPatient()">Continue</button>
    </div>

    <!-- IC number input (shown only when multiple matches found) -->
    <div id="icInputSection" style="display:none;margin-top:14px;padding-top:14px;border-top:1px solid #e2e8f0">
      <p id="icPromptText" style="font-size:.85rem;font-weight:600;color:#744210;margin-bottom:8px"></p>
      <label>IC Number (e.g. 731015-14-5231)</label>
      <input id="patientIC" type="text" placeholder="YYMMDD-SS-XXXX" onkeydown="if(event.key==='Enter')loginWithIC()" />
      <div style="display:flex;gap:8px">
        <button onclick="loginWithIC()">Confirm</button>
        <button class="sec" onclick="resetLogin()">Back</button>
      </div>
    </div>

    <div id="loginStatus" style="font-size:.8rem;margin-top:8px;min-height:18px"></div>
  </div>

  <!-- Step 3: Chat -->
  <div class="card" id="chatSection" style="display:none">
    <h2>Chat</h2>
    <div id="patientBadge" style="margin-bottom:10px;font-size:.85rem;color:#2d6a4f;font-weight:600"></div>
    <div id="chatBox" class="chat-box"></div>
    <div class="chat-input-row">
      <input id="chatInput" type="text" placeholder="Ask a nutrition question…" onkeydown="if(event.key==='Enter')sendMessage()" />
      <button onclick="sendMessage()">Send</button>
    </div>
    <button class="sec" style="margin-top:8px;font-size:.8rem" onclick="clearChat()">New conversation</button>
  </div>

  <!-- Raw API explorer -->
  <div class="card">
    <h2>Raw API Explorer (optional)</h2>
    <label>Endpoint</label>
    <select id="endpoint">
      <option value="GET /patients/">GET /patients/  — list all patients</option>
      <option value="GET /patients/1">GET /patients/1  — patient detail (id=1)</option>
      <option value="GET /documents/">GET /documents/  — list documents</option>
      <option value="GET /health">GET /health  — health check</option>
    </select>
    <button onclick="runRaw()">Run</button>
    <div id="rawOutput" class="output">Result will appear here…</div>
  </div>

</div>

<script>
let selectedPatient = null;
let sessionId = 'session-' + Math.random().toString(36).slice(2);

function apiKey() { return document.getElementById('apiKey').value.trim(); }
function setStatus(msg, err) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = err ? '#e53e3e' : '#2d6a4f';
}

function confirmApiKey() {
  if (!apiKey()) { setStatus('Please enter an API key.', true); return; }
  setStatus('');
  document.getElementById('apiSection').style.display = 'none';
  document.getElementById('loginSection').style.display = 'block';
  document.getElementById('patientName').focus();
}

async function loginPatient() {
  const name = document.getElementById('patientName').value.trim();
  if (!name) { setLoginStatus('Please enter your full name.', true); return; }
  setLoginStatus('Looking up your profile…');
  try {
    const r = await fetch('/patient/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey() },
      body: JSON.stringify({ name })
    });
    if (!r.ok) { setLoginStatus('Error ' + r.status + ': ' + (await r.text()), true); return; }
    const data = await r.json();

    if (data.multiple) {
      // Switch to IC entry
      document.getElementById('nameInputSection').style.display = 'none';
      document.getElementById('icInputSection').style.display = 'block';
      document.getElementById('icPromptText').textContent = data.message || 'Multiple patients found. Please enter your IC number.';
      document.getElementById('patientIC').value = '';
      document.getElementById('patientIC').focus();
      setLoginStatus('');
      return;
    }
    startChatWithPatient(data);
  } catch(e) { setLoginStatus('Network error: ' + e.message, true); }
}

async function loginWithIC() {
  const name = document.getElementById('patientName').value.trim();
  const ic = document.getElementById('patientIC').value.trim();
  if (!ic) { setLoginStatus('Please enter your IC number.', true); return; }
  setLoginStatus('Verifying IC…');
  try {
    const r = await fetch('/patient/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey() },
      body: JSON.stringify({ name, ic_number: ic })
    });
    if (!r.ok) { setLoginStatus('Error ' + r.status + ': ' + (await r.text()), true); return; }
    const data = await r.json();
    if (data.multiple) {
      setLoginStatus('IC number not matched. Please check your IC and try again.', true);
      return;
    }
    startChatWithPatient(data);
  } catch(e) { setLoginStatus('Network error: ' + e.message, true); }
}

function resetLogin() {
  document.getElementById('nameInputSection').style.display = 'block';
  document.getElementById('icInputSection').style.display = 'none';
  document.getElementById('patientIC').value = '';
  document.getElementById('patientName').value = '';
  setLoginStatus('');
  document.getElementById('patientName').focus();
}

function setLoginStatus(msg, err) {
  const el = document.getElementById('loginStatus');
  el.textContent = msg;
  el.style.color = err ? '#e53e3e' : '#2d6a4f';
}

function startChatWithPatient(data) {
  selectedPatient = data;
  document.getElementById('loginSection').style.display = 'none';
  document.getElementById('chatSection').style.display = 'block';
  document.getElementById('chatBox').innerHTML = '';
  sessionId = 'session-' + data.patient_id + '-' + Date.now();

  const badge = document.getElementById('patientBadge');
  if (data.is_new) {
    badge.textContent = 'Welcome, ' + data.name + '! Your profile has been created.';
    addMsg("Hello " + data.name + "! I'm your NutriBot dietitian. I'm here to help with personalised nutrition advice. Could you tell me a little about yourself — any health conditions or dietary goals?", 'bot');
  } else {
    const conds = (data.conditions||[]).join(', ') || 'general wellness';
    badge.textContent = 'Welcome back, ' + data.name + ' — ' + conds;
    addMsg('Welcome back, ' + data.name + '! I have your profile on file. How can I help you today with your nutrition?', 'bot');
  }
  document.getElementById('chatInput').focus();
}

function addMsg(text, role) {
  const box = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

async function sendMessage() {
  const input = document.getElementById('chatInput');
  const q = input.value.trim();
  if (!q || !selectedPatient) return;
  input.value = '';
  addMsg(q, 'user');
  const loading = addMsg('Thinking…', 'bot loading');

  try {
    const r = await fetch('/chat/get_response', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey() },
      body: JSON.stringify({ question: q, session_id: sessionId, patient_id: selectedPatient.patient_id || selectedPatient.id })
    });
    if (!r.ok) { loading.textContent = 'Error ' + r.status; loading.classList.add('err'); return; }
    // Stream the response
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let text = '';
    loading.textContent = '';
    loading.classList.remove('loading');
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
      loading.textContent = text;
      document.getElementById('chatBox').scrollTop = 9999;
    }
    if (!text) loading.textContent = '(no response)';
  } catch(e) { loading.textContent = 'Error: ' + e.message; }
}

function clearChat() {
  document.getElementById('chatBox').innerHTML = '';
  sessionId = 'session-' + (selectedPatient?.id||'x') + '-' + Date.now();
}

async function runRaw() {
  const val = document.getElementById('endpoint').value;
  const [method, path] = val.split(' ');
  const out = document.getElementById('rawOutput');
  out.textContent = 'Loading…';
  try {
    const r = await fetch(path, { headers: { 'X-API-Key': apiKey() } });
    const text = await r.text();
    try { out.textContent = JSON.stringify(JSON.parse(text), null, 2); }
    catch { out.textContent = text; }
  } catch(e) { out.textContent = 'Error: ' + e.message; }
}
</script>
</body>
</html>"""

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

# --- Patient Login ---
from pydantic import BaseModel as _BaseModel

class PatientLoginRequest(_BaseModel):
    name: str
    ic_number: str | None = None   # For disambiguation when multiple name matches exist

@app.post("/patient/login", tags=["Patients"])
async def patient_login(
    request: PatientLoginRequest,
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """
    Match a patient by name (as per IC). Returns their full profile if found.
    If multiple patients share the same name, pass ic_number to disambiguate.
    If no match, creates a minimal new patient record so the session can continue.
    """
    matches = db.get_patients_by_name(database, request.name.strip(), client.id)

    # --- IC disambiguation path ---
    if request.ic_number:
        p = db.get_patient_by_ic(database, request.ic_number.strip(), client.id)
        if p:
            return {
                "found": True,
                "is_new": False,
                "patient_id": p.id,
                "name": p.name,
                "age": p.age,
                "gender": p.gender,
                "ethnicity": p.ethnicity,
                "conditions": p.conditions or [],
                "medications": p.medications or [],
                "dietary_restrictions": p.dietary_restrictions or [],
                "allergies": p.allergies or [],
            }
        # IC provided but not matched — fall through to create new
        matches = []

    if len(matches) == 1:
        p = matches[0]
        return {
            "found": True,
            "is_new": False,
            "patient_id": p.id,
            "name": p.name,
            "age": p.age,
            "gender": p.gender,
            "ethnicity": p.ethnicity,
            "conditions": p.conditions or [],
            "medications": p.medications or [],
            "dietary_restrictions": p.dietary_restrictions or [],
            "allergies": p.allergies or [],
        }

    if len(matches) > 1:
        # Ask the patient to confirm via IC number
        return {
            "found": True,
            "multiple": True,
            "message": "Multiple patients found with this name. Please enter your IC number to identify yourself.",
        }

    # Not found — return clear error, do NOT auto-create records
    return {"found": False, "message": "No patient record found with that name. Please check your spelling or contact your clinic."}


# --- Patient Endpoints ---
@app.get("/patients/", tags=["Patients"])
async def list_patients(
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """List all patients registered under the authenticated B2B client."""
    patients = db.get_patients_by_client(database, client.id)
    return {
        "client_name": client.client_name,
        "total_patients": len(patients),
        "patients": [
            {
                "id": p.id,
                "name": p.name,
                "age": p.age,
                "gender": p.gender,
                "ethnicity": p.ethnicity,
                "conditions": p.conditions,
                "medications": p.medications,
                "dietary_restrictions": p.dietary_restrictions,
                "allergies": p.allergies,
                "username": p.username,
            }
            for p in patients
        ],
    }


@app.get("/patients/{patient_id}", tags=["Patients"])
async def get_patient_detail(
    patient_id: int,
    client = Depends(get_api_client),
    database: Session = Depends(get_db),
):
    """Get the full medical profile for a specific patient."""
    patient = db.get_patient(database, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.client_id != client.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "id": patient.id,
        "name": patient.name,
        "age": patient.age,
        "gender": patient.gender,
        "ethnicity": patient.ethnicity,
        "weight_kg": patient.weight_kg,
        "height_cm": patient.height_cm,
        "conditions": patient.conditions,
        "medications": patient.medications,
        "dietary_restrictions": patient.dietary_restrictions,
        "allergies": patient.allergies,
        "notes": patient.notes,
        "username": patient.username,
        "client_id": patient.client_id,
    }


# --- Main Entry Point ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)