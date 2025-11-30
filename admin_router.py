import os
import secrets
from fastapi import APIRouter, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import database as db

router = APIRouter()

# --- Admin Password from Environment ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_in_secrets")

def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

@router.get("/create-api-key", response_class=HTMLResponse)
async def create_api_key_form():
    """
    Admin dashboard for managing API keys.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NutriBot Admin Dashboard</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 20px;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                max-width: 600px;
                width: 100%;
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
                font-size: 24px;
                text-align: center;
            }
            .subtitle {
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
                text-align: center;
            }
            .tabs {
                display: flex;
                margin-bottom: 20px;
                border-bottom: 2px solid #eee;
            }
            .tab {
                padding: 10px 20px;
                cursor: pointer;
                font-weight: 600;
                color: #666;
                border-bottom: 2px solid transparent;
                margin-bottom: -2px;
            }
            .tab.active {
                color: #667eea;
                border-bottom-color: #667eea;
            }
            .tab-content {
                display: none;
            }
            .tab-content.active {
                display: block;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                color: #555;
                font-weight: 600;
                font-size: 14px;
            }
            input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                box-sizing: border-box;
                transition: border-color 0.3s;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
            }
            .result {
                margin-top: 30px;
                padding: 20px;
                background: #f0f7ff;
                border-left: 4px solid #667eea;
                border-radius: 6px;
                display: none;
            }
            .result.success { display: block; }
            .result.error { 
                display: block; 
                background: #fff0f0; 
                border-left-color: #e74c3c; 
            }
            .api-key {
                background: #333;
                color: #0f0;
                padding: 15px;
                border-radius: 6px;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                margin: 15px 0;
                word-break: break-all;
                cursor: pointer;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }
            th, td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }
            th {
                background: #f8f9fa;
                font-weight: 600;
                color: #555;
            }
            .badge {
                background: #e0e0e0;
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🛡️ Admin Dashboard</h1>
            <p class="subtitle">Manage B2B Clients & API Keys</p>
            
            <div class="tabs">
                <div class="tab active" onclick="switchTab('create')">Create Key</div>
                <div class="tab" onclick="switchTab('list')">View Clients</div>
            </div>
            
            <!-- Create Key Tab -->
            <div id="create" class="tab-content active">
                <form id="apiKeyForm">
                    <div class="form-group">
                        <label for="password">Admin Password:</label>
                        <input type="password" id="password" name="password" required placeholder="Enter admin password">
                    </div>
                    <div class="form-group">
                        <label for="client_name">Client Name:</label>
                        <input type="text" id="client_name" name="client_name" required placeholder="e.g., HealthTechCo">
                    </div>
                    <button type="submit">Generate API Key</button>
                </form>
                <div id="createResult" class="result"></div>
            </div>
            
            <!-- List Clients Tab -->
            <div id="list" class="tab-content">
                <form id="listClientsForm">
                    <div class="form-group">
                        <label for="list_password">Admin Password:</label>
                        <input type="password" id="list_password" name="password" required placeholder="Enter admin password">
                    </div>
                    <button type="submit">Load Clients</button>
                </form>
                <div id="listResult" style="margin-top: 20px;"></div>
            </div>
        </div>

        <script>
            function switchTab(tabName) {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                event.target.classList.add('active');
                document.getElementById(tabName).classList.add('active');
                
                // Sync password if typed
                const p1 = document.getElementById('password').value;
                const p2 = document.getElementById('list_password').value;
                if(p1 && !p2) document.getElementById('list_password').value = p1;
                if(!p1 && p2) document.getElementById('password').value = p2;
            }

            // Create Key Handler
            document.getElementById('apiKeyForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const resultDiv = document.getElementById('createResult');
                
                try {
                    const response = await fetch('/admin/create-api-key', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    
                    if (response.ok) {
                        resultDiv.className = 'result success';
                        resultDiv.innerHTML = `
                            <h3 style="margin-top: 0; color: #27ae60;">✅ Created!</h3>
                            <p><strong>Client:</strong> ${data.client_name} (ID: ${data.client_id})</p>
                            <div class="api-key" onclick="navigator.clipboard.writeText(this.textContent); alert('Copied!')">
                                ${data.api_key}
                            </div>
                            <p style="color: #e74c3c; font-size: 12px;">⚠️ Copy now! Won't be shown again.</p>
                        `;
                        e.target.reset();
                    } else {
                        throw new Error(data.detail || 'Error');
                    }
                } catch (error) {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = `<p>❌ ${error.message}</p>`;
                }
            });

            // List Clients Handler
            document.getElementById('listClientsForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const resultDiv = document.getElementById('listResult');
                resultDiv.innerHTML = '<p style="text-align:center">Loading...</p>';
                
                try {
                    const response = await fetch('/admin/list-clients', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    
                    if (response.ok) {
                        if (data.clients.length === 0) {
                            resultDiv.innerHTML = '<p style="text-align:center; color:#666">No clients found.</p>';
                            return;
                        }
                        
                        let html = `
                            <p><strong>Total Clients:</strong> ${data.count}</p>
                            <table>
                                <thead><tr><th>ID</th><th>Name</th></tr></thead>
                                <tbody>
                        `;
                        
                        data.clients.forEach(client => {
                            html += `<tr>
                                <td><span class="badge">${client.id}</span></td>
                                <td>${client.name}</td>
                            </tr>`;
                        });
                        
                        html += '</tbody></table>';
                        resultDiv.innerHTML = html;
                    } else {
                        throw new Error(data.detail || 'Error');
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<p style="color: #e74c3c; text-align: center;">❌ ${error.message}</p>`;
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content

@router.post("/create-api-key")
async def create_api_key(
    password: str = Form(...),
    client_name: str = Form(...),
    database: Session = Depends(get_db)
):
    """
    Create a new API key for a B2B client.
    Protected by admin password.
    """
    # Verify admin password
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    
    # Validate client name
    if not client_name or not client_name.strip():
        raise HTTPException(status_code=400, detail="Client name cannot be empty")
    
    client_name = client_name.strip()
    
    # Check if client already exists
    existing_client = db.get_api_client_by_name(database, client_name)
    if existing_client:
        raise HTTPException(status_code=400, detail=f"Client '{client_name}' already exists")
    
    # Generate secure API key
    api_key = f"nbk_live_{secrets.token_hex(32)}"
    
    # Add client to database
    new_client = db.add_api_client(database, client_name, api_key)
    
    return {
        "status": "success",
        "client_name": new_client.client_name,
        "client_id": new_client.id,
        "api_key": api_key,
        "message": "API Key created successfully. This key will not be shown again."
    }

@router.post("/list-clients")
async def list_clients(
    password: str = Form(...),
    database: Session = Depends(get_db)
):
    """
    List all registered clients.
    Protected by admin password.
    """
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    
    clients = db.get_all_api_clients(database)
    
    return {
        "count": len(clients),
        "clients": [
            {"id": c.id, "name": c.client_name}
            for c in clients
        ]
    }
