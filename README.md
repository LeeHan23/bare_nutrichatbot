---
title: Nutribot-API
emoji: 🤖
colorFrom: green
colorTo: blue
sdk: docker
---
# AI Nutrition Assistant Framework

This project is a sophisticated, multi-tenant AI chatbot framework designed to serve as a customizable nutrition and wellness knowledge assistant. It is built to be deployed as a scalable backend service (SaaS), allowing various client applications (web, mobile) to connect to its powerful API.

The core architecture is built around a hybrid, Retrieval-Augmented Generation (RAG) knowledge model:

1.  A **foundational knowledge base** is pre-built from core nutrition documents, providing a consistent source of truth for all users.
2.  Clients can upload their own documents via an API endpoint to create a **private, permanent, and custom knowledge base** that augments the foundational knowledge, allowing for a highly personalized experience for their end-users.

The chatbot is hard-coded with a specialized persona to guide users through the **ADIME (Assessment, Diagnosis, Intervention, Monitoring & Evaluation)** process for a specific health condition, making it an ideal tool for healthcare and wellness applications.

---
## ✨ Features

* **Conversational AI:** Natural, human-like chat powered by OpenAI's GPT models.
* **Hybrid RAG System:** The bot answers questions by searching both a foundational knowledge base and a user-specific private knowledge base, ensuring factual and personalized responses.
* **Permanent Custom Knowledge:** Users can upload their own documents to "train" the bot on private knowledge. This knowledge is persistent and doesn't need to be re-uploaded.
* **Scalable SaaS Architecture:** Built with FastAPI, the application is designed to be deployed as a central service, accessible to multiple client applications via a REST API.
* **Specialized Persona:** The chatbot is engineered to follow the ADIME nutrition care process, providing structured and goal-oriented consultations.
* **Efficient & Cost-Effective:** The knowledge base builder uses intelligent, incremental updates to only process new or changed files, significantly reducing processing time and API costs.
* **Admin & User Interfaces:** Comes with a Streamlit-based UI for client interaction and a separate admin panel for management and testing.
* **Ready for Deployment:** Includes a Dockerfile for easy packaging and deployment on cloud services.

---
## 🛠️ Tech Stack

* **Backend:** Python, FastAPI
* **Frontend (UI):** Streamlit
* **Database (Users):** SQLite
* **AI & Orchestration:** LangChain
* **Language Models:** OpenAI (e.g., `gpt-4-turbo`, `text-embedding-3-small`)
* **Vector Store:** ChromaDB
* **Document Processing:** Unstructured.io, PyMuPDF, python-docx
* **Deployment:** Docker, Uvicorn, Gunicorn

---
## 📂 Project Structure
bare_NutriChatbot/
├── data/
│   ├── base_docs/             # Place foundational .pdf/.docx files here
│   ├── vectorstore_base/      # Stores the foundational knowledge vectorbase
│   ├── vectorstores_user/     # Stores user-specific vectorbases
│   └── users.db               # SQLite database for user management
├── .env                       # Secret keys and configuration (DO NOT COMMIT)
├── .env.example               # Example environment file
├── .gitignore                 # Specifies files to ignore for Git
├── app.py                     # Main FastAPI application and API endpoints
├── build_base_db.py           # Script to train the foundational knowledge base
├── database.py                # Database models and session management
├── llm.py                     # Language model configuration
├── process_user_docs.py       # Handles processing of user-uploaded documents
├── rag.py                     # Core RAG logic and chatbot persona
├── requirements.txt           # Python dependencies
├── ui.py                      # Streamlit client-facing user interface
├── admin_ui.py                # Streamlit admin interface
└── vector_store.py            # Manages the hybrid retriever for knowledge bases

-- 

## 🚀 Local Setup and Installation

Follow these steps to run the application on your local machine.

### 1. Prerequisites

* Python 3.10+
* An OpenAI API Key

### 2. Clone the Repository

```bash
git clone [https://github.com/YourUsername/YourRepoName.git](https://github.com/YourUsername/YourRepoName.git)
cd YourRepoName
```

### 3. Install Dependencies 
Install all the required Python packages using the `requirements.txt` file.

``` bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a .env file in the project root. You can copy the `.env.example` file to get started.

```bash
cp .env.example .env
```
Now, open the .env file and add your actual OpenAI API Key and any other configurations.

### 5. Train the Foundational Knowledge Base 
Before running the application, you must build the core knowledge base. 
1. Place your foundational nutrition documents (PDFs, DOCX files) into the `data/base_docs/` directory 
2. Run the build script from your terminal:

```bash
python build_base_dp.py
```

This will create the `vectorstore_base` directory, which contains the "brain" of your chatbot.

## 🏁 Running the Application 
The application consists of three main parts that yu can run simultaneously in seperate terminal windows.
 * Backend API (FastAPI)
 ```bash
 uvicorn app:app --reload --port 8000
 ```
 * Client User Interface (Streamlit)
 ```bash
 streamlit run ui.py
 ```
 * Admin Panel (Streamlit)
 ```bash 
 streamlit run admin_ui.py --server.port 8502
 ```
You can now access th Client UI at `http://localhost:8501` and the Admin Panel at `http://localhost:8502`

## API Endpoints
The FastAPI backend exposes the following key endpoints for client applications: 
 * `POST /chat/get_response`: The main endpoint for getting a response from the chatbot.
 * `POST /upload_document/`: The endpoint for clients to upload their custom knowledge documents.
 * `GET /`: A root endpoitn to confirm the API is running.