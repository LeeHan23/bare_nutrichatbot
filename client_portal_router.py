import os
import secrets
from fastapi import APIRouter, HTTPException, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import database as db
from dependencies import get_db
from process_client_docs import process_client_document, calculate_file_hash

router = APIRouter()

# Simple in-memory session store (for demo - use proper session management in production)
sessions = {}

def verify_session(session_token: str = Form(...)):
    """Verify session token and return client"""
    if session_token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return sessions[session_token]

@router.get("/", response_class=HTMLResponse)
async def portal_login():
    """Login page for clients to access their document management portal"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NutriBot Client Portal</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                background: white;
                padding: 50px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 450px;
                width: 100%;
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
                font-size: 28px;
                text-align: center;
            }
            .subtitle {
                color: #666;
                margin-bottom: 40px;
                font-size: 15px;
                text-align: center;
            }
            .form-group {
                margin-bottom: 25px;
            }
            label {
                display: block;
                margin-bottom: 10px;
                color: #555;
                font-weight: 600;
                font-size: 14px;
            }
            input {
                width: 100%;
                padding: 14px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 15px;
                transition: border-color 0.3s;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                width: 100%;
                padding: 16px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
            }
            button:active {
                transform: translateY(0);
            }
            .error {
                background: #fff0f0;
                border-left: 4px solid #e74c3c;
                padding: 15px;
                border-radius: 6px;
                margin-bottom: 20px;
                display: none;
            }
            .error.show {
                display: block;
            }
            .error-text {
                color: #e74c3c;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔒 Client Portal</h1>
            <p class="subtitle">Manage your specialized knowledge base</p>
            
            <div id="error" class="error">
                <p class="error-text" id="errorText"></p>
            </div>
            
            <form id="loginForm">
                <div class="form-group">
                    <label for="api_key">API Key:</label>
                    <input type="password" id="api_key" name="api_key" required 
                           placeholder="Enter your API key (nbk_live_...)">
                </div>
                
                <button type="submit">Access Portal</button>
            </form>
        </div>

        <script>
            document.getElementById('loginForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const apiKey = document.getElementById('api_key').value;
                const errorDiv = document.getElementById('error');
                const errorText = document.getElementById('errorText');
                
                try {
                    const formData = new FormData();
                    formData.append('api_key', apiKey);
                    
                    const response = await fetch('/portal/auth', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        // Store session token and redirect to dashboard
                        localStorage.setItem('session_token', data.session_token);
                        localStorage.setItem('client_name', data.client_name);
                        localStorage.setItem('api_key', apiKey); // Store API key for chat
                        window.location.href = '/portal/dashboard';
                    } else {
                        throw new Error(data.detail || 'Authentication failed');
                    }
                } catch (error) {
                    errorDiv.classList.add('show');
                    errorText.textContent = error.message;
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content

@router.post("/auth")
async def authenticate(
    api_key: str = Form(...),
    database: Session = Depends(get_db)
):
    """Authenticate client with API key and create session"""
    client = db.get_client_by_key(database, api_key)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Create session
    session_token = secrets.token_hex(32)
    sessions[session_token] = {
        "client_id": client.id,
        "client_name": client.client_name
    }
    
    return {
        "status": "success",
        "session_token": session_token,
        "client_name": client.client_name
    }

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Client dashboard with document management"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Document Management - NutriBot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f5f5f5;
                padding: 20px;
            }
            /* Typing Indicator */
            .typing {
                display: flex;
                align-items: center;
                gap: 5px;
                padding: 5px 0;
            }
            .dot {
                width: 6px;
                height: 6px;
                background: #666;
                border-radius: 50%;
                animation: bounce 1.4s infinite ease-in-out both;
            }
            .dot:nth-child(1) { animation-delay: -0.32s; }
            .dot:nth-child(2) { animation-delay: -0.16s; }
            @keyframes bounce {
                0%, 80%, 100% { transform: scale(0); }
                40% { transform: scale(1); }
            }
            /* Markdown Styles within Chat */
            .bot-message-content ul, .bot-message-content ol {
                margin-left: 20px;
                margin-top: 5px;
                margin-bottom: 5px;
            }
            .bot-message-content p {
                margin-bottom: 8px;
            }
            .bot-message-content p:last-child {
                margin-bottom: 0;
            }
            .bot-message-content strong {
                font-weight: 600;
                color: #2d3748;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 12px;
                margin-bottom: 30px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }
            .header h1 {
                font-size: 28px;
                margin-bottom: 10px;
            }
            .header p {
                opacity: 0.9;
                font-size: 16px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }
            .stat-value {
                font-size: 32px;
                font-weight: bold;
                color: #667eea;
                margin-bottom: 5px;
            }
            .stat-label {
                color: #666;
                font-size: 14px;
            }
            .section {
                background: white;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }
            .section h2 {
                margin-bottom: 20px;
                color: #333;
                font-size: 22px;
            }
            .upload-zone {
                border: 3px dashed #e0e0e0;
                border-radius: 12px;
                padding: 40px;
                text-align: center;
                margin-bottom: 20px;
                transition: all 0.3s;
                cursor: pointer;
            }
            .upload-zone:hover, .upload-zone.drag-over {
                border-color: #667eea;
                background: #f8f9ff;
            }
            .upload-zone input {
                display: none;
            }
            .btn {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            }
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
            }
            .btn-danger {
                background: #e74c3c;
                color: white;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }
            th, td {
                padding: 15px;
                text-align: left;
                border-bottom: 1px solid #e0e0e0;
            }
            th {
                background: #f8f9fa;
                font-weight: 600;
                color: #555;
                font-size: 13px;
                text-transform: uppercase;
            }
            .badge {
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
            }
            .badge-success {
                background: #d4edda;
                color: #155724;
            }
            .badge-warning {
                background: #fff3cd;
                color: #856404;
            }
            .badge-danger {
                background: #f8d7da;
                color: #721c24;
            }
            .no-docs {
                text-align: center;
                padding: 40px;
                color: #999;
            }
            .loading {
                text-align: center;
                padding: 40px;
            }
            .logout {
                float: right;
                background: rgba(255,255,255,0.2);
                color: white;
                padding: 10px 20px;
                border: 2px solid white;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
            }
            .logout:hover {
                background: rgba(255,255,255,0.3);
            }
        </style>
    </head>
    <body>
        <div class="header">
            <button class="logout" onclick="logout()">Logout</button>
            <h1>📚 Document Management</h1>
            <p id="clientName">Loading...</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="totalDocs">-</div>
                <div class="stat-label">Total Documents</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="totalChunks">-</div>
                <div class="stat-label">Knowledge Chunks</div>
            </div>
        </div>

        <div class="section">
            <h2>💬 Test Chat</h2>
            <div class="chat-container" style="border: 1px solid #e0e0e0; border-radius: 12px; overflow: hidden; background: white;">
                <div id="chatMessages" style="height: 400px; overflow-y: auto; padding: 20px; background: #f8f9fa;">
                    <div class="message bot-message" style="margin-bottom: 15px; max-width: 80%;">
                        <div class="bot-message-content" style="background: white; padding: 12px 16px; border-radius: 12px 12px 12px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.05); display: inline-block;">
                            Hello! I'm your Nutrition Assistant. How can I help you today? 🥗
                        </div>
                    </div>
                </div>
                <div style="padding: 20px; background: white; border-top: 1px solid #e0e0e0; display: flex; gap: 10px;">
                    <input type="text" id="chatInput" placeholder="Ask a question..." style="flex: 1; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; outline: none;">
                    <button onclick="sendMessage()" id="sendBtn" style="padding: 12px 24px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">Send</button>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📤 Upload Documents</h2>
            <div class="upload-zone" id="uploadZone">
                <input type="file" id="fileInput" multiple accept=".pdf,.docx,.doc">
                <p style="font-size: 18px; margin-bottom: 10px;">🖱️ Click or drag files here</p>
                <p style="color: #999; font-size: 14px;">Supports PDF and DOCX files</p>
            </div>
            <div id="uploadProgress" style="display: none; margin-top: 20px;">
                <p id="progressText">Uploading...</p>
            </div>
        </div>

        <div class="section">
            <h2>📋 Your Documents</h2>
            <div id="documentsTable">
                <div class="loading">Loading documents...</div>
            </div>
        </div>

        <script>
            const sessionToken = localStorage.getItem('session_token');
            const clientName = localStorage.getItem('client_name');
            // We need the API Key for the chat endpoint. 
            // Since we don't store it in plain text in local storage for security in a real app, 
            // but for this demo portal we need it.
            // Ideally, we should proxy the chat request through the portal backend, 
            // but to keep it simple and fast as requested, we'll ask the user to re-enter it 
            // or we can store it temporarily if the user just logged in.
            // actually, let's just use the session token and have a portal-specific chat endpoint?
            // No, that requires more backend work.
            // Let's just store the API key in localStorage during login for this demo.
            const apiKey = localStorage.getItem('api_key'); 
            
            if (!sessionToken) {
                window.location.href = '/portal/';
            }
            
            document.getElementById('clientName').textContent = `Welcome, ${clientName}`;

            // --- Chat Logic ---
            const chatInput = document.getElementById('chatInput');
            const chatMessages = document.getElementById('chatMessages');
            const sendBtn = document.getElementById('sendBtn');

            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });

            async function sendMessage() {
                const question = chatInput.value.trim();
                if (!question) return;

                // Add User Message
                appendMessage(question, 'user');
                chatInput.value = '';
                chatInput.disabled = true;
                sendBtn.disabled = true;

                // Add Bot Placeholder with Typing Indicator
                const botMessageDiv = appendMessage('', 'bot', true); // true for typing
                const botTextDiv = botMessageDiv.querySelector('.bot-message-content');
                
                // Typing animation HTML
                botTextDiv.innerHTML = '<div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';

                let fullResponse = "";

                try {
                    const response = await fetch('/chat/get_response', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-API-Key': apiKey // We need to ensure this is saved on login
                        },
                        body: JSON.stringify({
                            question: question,
                            session_id: 'portal_demo_' + Date.now()
                        })
                    });

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let firstChunk = true;

                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        
                        if (firstChunk) {
                            botTextDiv.innerHTML = ''; // Clear typing indicator
                            firstChunk = false;
                        }

                        const text = decoder.decode(value);
                        fullResponse += text;
                        
                        // Render Markdown
                        botTextDiv.innerHTML = marked.parse(fullResponse);
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                    }

                } catch (error) {
                    botTextDiv.textContent = "Error: " + error.message;
                } finally {
                    chatInput.disabled = false;
                    sendBtn.disabled = false;
                    chatInput.focus();
                }
            }

            function appendMessage(text, sender, isTyping = false) {
                const msgDiv = document.createElement('div');
                msgDiv.className = `message ${sender}-message`;
                msgDiv.style.marginBottom = '15px';
                msgDiv.style.maxWidth = '80%';
                msgDiv.style.textAlign = sender === 'user' ? 'right' : 'left';
                msgDiv.style.marginLeft = sender === 'user' ? 'auto' : '0';

                const bubble = document.createElement('div');
                bubble.className = 'bot-message-content'; // Class for styling markdown
                
                if (!isTyping) {
                    bubble.textContent = text; // Default text content
                }
                
                bubble.style.padding = '12px 16px';
                bubble.style.display = 'inline-block';
                bubble.style.boxShadow = '0 2px 5px rgba(0,0,0,0.05)';
                
                if (sender === 'user') {
                    bubble.style.background = '#667eea';
                    bubble.style.color = 'white';
                    bubble.style.borderRadius = '12px 12px 0 12px';
                } else {
                    bubble.style.background = 'white';
                    bubble.style.color = '#333';
                    bubble.style.borderRadius = '12px 12px 12px 0';
                }

                msgDiv.appendChild(bubble);
                chatMessages.appendChild(msgDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
                return msgDiv;
            }
            
            // --- Document Logic ---
            async function loadDocuments() {
                try {
                    const formData = new FormData();
                    formData.append('session_token', sessionToken);
                    
                    const response = await fetch('/portal/documents', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    // Update stats
                    document.getElementById('totalDocs').textContent = data.total_documents;
                    document.getElementById('totalChunks').textContent = data.total_chunks;
                    
                    // Render table
                    const tableHtml = data.documents.length > 0 ? `
                        <table>
                            <thead>
                                <tr>
                                    <th>Filename</th>
                                    <th>Upload Date</th>
                                    <th>Size</th>
                                    <th>Chunks</th>
                                    <th>Status</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.documents.map(doc => `
                                    <tr>
                                        <td>${doc.filename}</td>
                                        <td>${new Date(doc.upload_date).toLocaleString()}</td>
                                        <td>${formatBytes(doc.file_size)}</td>
                                        <td>${doc.chunk_count}</td>
                                        <td><span class="badge badge-${doc.status === 'completed' ? 'success' : doc.status === 'pending' ? 'warning' : 'danger'}">${doc.status}</span></td>
                                        <td><button class="btn btn-danger" onclick="deleteDoc(${doc.id}, '${doc.filename}')">Delete</button></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<div class="no-docs">No documents uploaded yet. Upload some documents to get started!</div>';
                    
                    document.getElementById('documentsTable').innerHTML = tableHtml;
                } catch (error) {
                    document.getElementById('documentsTable').innerHTML = '<div class="no-docs">Error loading documents</div>';
                }
            }
            
            function formatBytes(bytes) {
                if (bytes === 0) return '0 Bytes';
                const k = 1024;
                const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
            }
            
            // Upload zone handlers
            const uploadZone = document.getElementById('uploadZone');
            const fileInput = document.getElementById('fileInput');
            
            uploadZone.addEventListener('click', () => fileInput.click());
            
            uploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadZone.classList.add('drag-over');
            });
            
            uploadZone.addEventListener('dragleave', () => {
                uploadZone.classList.remove('drag-over');
            });
            
            uploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadZone.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                uploadFiles(files);
            });
            
            fileInput.addEventListener('change', (e) => {
                uploadFiles(e.target.files);
            });
            
            async function uploadFiles(files) {
                if (files.length === 0) return;
                
                const formData = new FormData();
                formData.append('session_token', sessionToken);
                for (let file of files) {
                    formData.append('files', file);
                }
                
                document.getElementById('uploadProgress').style.display = 'block';
                document.getElementById('progressText').textContent = `Uploading ${files.length} file(s)...`;
                
                try {
                    const response = await fetch('/portal/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    document.getElementById('progressText').textContent = 
                        `Uploaded ${data.results.filter(r => r.status === 'completed').length} of ${files.length} files successfully!`;
                    
                    setTimeout(() => {
                        document.getElementById('uploadProgress').style.display = 'none';
                        fileInput.value = '';
                        loadDocuments();
                    }, 2000);
                } catch (error) {
                    document.getElementById('progressText').textContent = 'Upload failed: ' + error.message;
                }
            }
            
            async function deleteDoc(id, filename) {
                if (!confirm(`Delete "${filename}"?`)) return;
                
                try {
                    const formData = new FormData();
                    formData.append('session_token', sessionToken);
                    formData.append('document_id', id);
                    
                    const response = await fetch('/portal/delete', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        loadDocuments();
                    }
                } catch (error) {
                    alert('Delete failed');
                }
            }
            
            function logout() {
                localStorage.removeItem('session_token');
                localStorage.removeItem('client_name');
                localStorage.removeItem('api_key');
                window.location.href = '/portal/';
            }
            
            // Initial load
            loadDocuments();
        </script>
    </body>
    </html>
    """
    return html_content

@router.post("/documents")
async def get_documents(
    session_token: str = Form(...),
    database: Session = Depends(get_db)
):
    """Get all documents for authenticated client"""
    client_data = verify_session(session_token)
    
    documents = db.get_client_documents(database, client_data["client_id"])
    
    total_chunks = sum(doc.chunk_count for doc in documents)
    
    return {
        "total_documents": len(documents),
        "total_chunks": total_chunks,
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

@router.post("/upload")
async def upload_documents(
    session_token: str = Form(...),
    files: list[UploadFile] = File(...),
    database: Session = Depends(get_db)
):
    """Upload documents via client portal"""
    client_data = verify_session(session_token)
    
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    results = []
    
    for file in files:
        temp_filepath = os.path.join(temp_dir, file.filename)
        
        try:
            with open(temp_filepath, "wb") as buffer:
                import shutil
                shutil.copyfileobj(file.file, buffer)
            
            file_hash = calculate_file_hash(temp_filepath)
            file_size = os.path.getsize(temp_filepath)
            
            # Check for duplicates
            existing_doc = db.get_document_by_hash(database, client_data["client_id"], file_hash)
            if existing_doc:
                results.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "message": "Duplicate"
                })
                os.remove(temp_filepath)
                continue
            
            # Process document
            process_result = process_client_document(
                client_id=client_data["client_id"],
                filepath=temp_filepath,
                filename=file.filename
            )
            
            # Save metadata
            db.add_document_metadata(
                database,
                client_id=client_data["client_id"],
                filename=file.filename,
                file_hash=process_result["file_hash"],
                file_size=file_size,
                chunk_count=process_result["chunk_count"],
                status=process_result["status"]
            )
            
            results.append({
                "filename": file.filename,
                "status": process_result["status"],
                "chunk_count": process_result["chunk_count"]
            })
            
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": str(e)
            })
        
        finally:
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
    
    return {"results": results}

@router.post("/delete")
async def delete_document(
    session_token: str = Form(...),
    document_id: int = Form(...),
    database: Session = Depends(get_db)
):
    """Delete document via client portal"""
    from document_manager import delete_document_from_vectorstore
    
    client_data = verify_session(session_token)
    
    doc = db.get_document_by_id(database, document_id, client_data["client_id"])
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete from vector store
    delete_document_from_vectorstore(client_data["client_id"], doc.file_hash)
    
    # Delete metadata
    db.delete_document_metadata(database, document_id, client_data["client_id"])
    
    return {"status": "success"}
