import streamlit as st
import requests
import uuid
import pandas as pd
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# --- Configuration ---
# This will be the public URL of your deployed FastAPI service
# Found in Hugging Face Space -> Embed this space -> Direct URL
API_URL = os.getenv("API_URL", "https://leehan23-nutribot-api.hf.space")

st.set_page_config(page_title="Client Knowledge Portal", layout="wide", page_icon="🏢")

# --- Session State Initialization ---
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'api_key_valid' not in st.session_state:
    st.session_state.api_key_valid = False
if 'client_name' not in st.session_state:
    st.session_state.client_name = ""
if 'chat_session_id' not in st.session_state:
    st.session_state.chat_session_id = str(uuid.uuid4())
if 'messages' not in st.session_state:
    st.session_state.messages = []

# --- Sidebar for API Key (Login) ---
st.sidebar.title("🏢 Client Portal")

if not st.session_state.api_key_valid:
    st.sidebar.header("Login")
    api_key_input = st.sidebar.text_input(
        "Enter your API Key", 
        type="password", 
        key="api_key_input"
    )
    
    if st.sidebar.button("Login"):
        if not api_key_input:
            st.sidebar.error("Please enter an API key.")
        else:
            # --- Test the API Key by calling the documents endpoint ---
            try:
                headers = {'X-API-Key': api_key_input}
                response = requests.get(f"{API_URL}/documents/", headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.api_key = api_key_input
                    st.session_state.api_key_valid = True
                    st.session_state.client_name = data.get("client_name", "Client")
                    st.rerun()
                elif response.status_code == 401:
                    st.sidebar.error("Invalid API Key.")
                else:
                    st.sidebar.error(f"API Error ({response.status_code}). Please check server.")
                    
            except requests.exceptions.RequestException as e:
                st.error(f"Could not connect to the API: {e}. Is the backend running at {API_URL}?")
else:
    # --- Main Application View (after login) ---
    st.sidebar.success(f"Logged in as: {st.session_state.client_name}")
    if st.sidebar.button("Logout"):
        st.session_state.api_key = ""
        st.session_state.api_key_valid = False
        st.session_state.messages = []
        st.rerun()

    st.title(f"👋 Welcome, {st.session_state.client_name}")
    st.markdown("Manage your specialized knowledge base and test your bot.")
    
    tab1, tab2, tab3 = st.tabs(["📤 Upload Documents", "📋 Manage Documents", "💬 Test Chat"])

    # --- Tab 1: Upload Documents ---
    with tab1:
        st.header("Upload Knowledge")
        st.info("Upload PDF or DOCX files to train your bot. These documents will be added to your private knowledge base.")
        
        uploaded_files = st.file_uploader(
            "Choose files", 
            type=['pdf', 'docx', 'doc'],
            accept_multiple_files=True
        )

        if uploaded_files:
            if st.button(f"Upload {len(uploaded_files)} Files"):
                with st.spinner("Uploading and processing..."):
                    try:
                        headers = {'X-API-Key': st.session_state.api_key}
                        files = [('files', (f.name, f, f.type)) for f in uploaded_files]
                        
                        response = requests.post(
                            f"{API_URL}/upload_documents/",
                            headers=headers,
                            files=files
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            st.success(f"Processed {result['total_files']} files!")
                            
                            # Show results detail
                            results_df = pd.DataFrame(result['results'])
                            st.dataframe(results_df)
                        else:
                            st.error(f"Upload failed ({response.status_code}): {response.text}")
                            
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- Tab 2: Manage Documents ---
    with tab2:
        st.header("Your Documents")
        
        if st.button("Refresh List"):
            st.rerun()
            
        try:
            headers = {'X-API-Key': st.session_state.api_key}
            response = requests.get(f"{API_URL}/documents/", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                docs = data.get("documents", [])
                
                if not docs:
                    st.info("No documents found. Go to the Upload tab to add some!")
                else:
                    # Display as a table with delete buttons
                    for doc in docs:
                        col1, col2, col3, col4, col5 = st.columns([3, 2, 1, 1, 1])
                        with col1:
                            st.write(f"**{doc['filename']}**")
                        with col2:
                            st.write(f"{doc['upload_date'][:10]}")
                        with col3:
                            st.write(f"{doc['chunk_count']} chunks")
                        with col4:
                            status_color = "green" if doc['status'] == "completed" else "orange"
                            st.markdown(f":{status_color}[{doc['status']}]")
                        with col5:
                            if st.button("🗑️", key=f"del_{doc['id']}", help="Delete document"):
                                with st.spinner("Deleting..."):
                                    del_res = requests.delete(
                                        f"{API_URL}/documents/{doc['id']}",
                                        headers=headers
                                    )
                                    if del_res.status_code == 200:
                                        st.success("Deleted!")
                                        st.rerun()
                                    else:
                                        st.error("Failed")
            else:
                st.error("Failed to fetch documents.")
                
        except Exception as e:
            st.error(f"Error fetching documents: {e}")

    # --- Tab 3: Test Chat ---
    with tab3:
        st.header("Test Your Bot")
        st.markdown("Test how the bot answers questions using your uploaded knowledge.")
        
        # Chat interface
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Ask a question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                try:
                    headers = {'X-API-Key': st.session_state.api_key}
                    payload = {
                        "question": prompt,
                        "session_id": st.session_state.chat_session_id
                    }
                    
                    with st.spinner("Thinking..."):
                        response = requests.post(
                            f"{API_URL}/chat/get_response",
                            headers=headers,
                            json=payload,
                            stream=True
                        )
                        
                        if response.status_code == 200:
                            for chunk in response.iter_content(chunk_size=None):
                                if chunk:
                                    content = chunk.decode('utf-8')
                                    full_response += content
                                    message_placeholder.markdown(full_response + "▌")
                            message_placeholder.markdown(full_response)
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                        else:
                            st.error(f"Error ({response.status_code}): {response.text}")
                            
                except Exception as e:
                    st.error(f"Connection error: {e}")

if not st.session_state.api_key_valid:
     st.title("Welcome to the Client Portal")
     st.markdown("""
     This portal allows B2B clients to:
     - **Upload** specialized medical/nutritional documents
     - **Manage** their private knowledge base
     - **Test** their specialized chatbot
     
     Please log in with your API Key to continue.
     """)