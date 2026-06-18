# NutriChatbot — Full Architecture Document

> Last updated: 15 June 2026

## Table of Contents

0. [Use Cases](#0-use-cases)
1. [System Overview](#1-system-overview)
2. [System Flowchart](#2-system-flowchart)
3. [High-Level Architecture Diagram](#3-high-level-architecture-diagram)
3. [Technology Stack](#3-technology-stack)
4. [Application Entry Point & Startup](#4-application-entry-point--startup)
5. [Routing & API Surface](#5-routing--api-surface)
6. [Authentication & Authorization](#6-authentication--authorization)
7. [Patient Identity System](#7-patient-identity-system)
   - 7.1 [Patient Database Model](#71-patient-database-model)
   - 7.2 [Patient Login & IC Verification Flow](#72-patient-login--ic-verification-flow)
   - 7.3 [Profile Injection into RAG](#73-profile-injection-into-rag)
   - 7.4 [PatientStore Abstraction](#74-patientstore-abstraction)
   - 7.5 [Profile Extractor — Dynamic Data Collection](#75-profile-extractor--dynamic-data-collection)
   - 7.6 [Nutrition Assessment Priority List — eNCPT v2 Cardiac Schema](#76-nutrition-assessment-priority-list--encpt-v2-cardiac-schema)
8. [RAG Pipeline — Core Chat Flow](#8-rag-pipeline--core-chat-flow)
   - 8.1 [Disease Identification](#81-disease-identification)
   - 8.2 [Conversational Chain Construction](#82-conversational-chain-construction)
   - 8.3 [Retriever — Hybrid Multi-Tenant Vector Search](#83-retriever--hybrid-multi-tenant-vector-search)
   - 8.4 [LLM Configuration](#84-llm-configuration)
   - 8.5 [Fallback Mechanism](#85-fallback-mechanism)
   - 8.6 [Image Injection](#86-image-injection)
9. [Embedding Model](#9-embedding-model)
   - 9.1 [Base Model: BAAI/bge-m3](#91-base-model-baaibge-m3)
   - 9.2 [LoRA Adapter Inference](#92-lora-adapter-inference)
10. [Database Layer](#10-database-layer)
    - 10.1 [Relational Database (SQLAlchemy)](#101-relational-database-sqlalchemy)
    - 10.2 [Vector Store (pgvector)](#102-vector-store-pgvector)
11. [Document Ingestion Pipelines](#11-document-ingestion-pipelines)
    - 11.1 [Base Knowledge Build (`build_base_db.py`)](#111-base-knowledge-build-build_base_dbpy)
    - 11.2 [Client Document Ingestion (`process_client_docs.py`)](#112-client-document-ingestion-process_client_docspy)
    - 11.3 [Document Deletion (`document_manager.py`)](#113-document-deletion-document_managerpy)
12. [Multi-Tenancy Model](#12-multi-tenancy-model)
13. [Conversation Memory](#13-conversation-memory)
14. [Persona & Prompt Engineering](#14-persona--prompt-engineering)
15. [Streaming Response Delivery](#15-streaming-response-delivery)
16. [UI Layers](#16-ui-layers)
    - 16.1 [Patient-Facing App (`patient_app.html`)](#161-patient-facing-app-patient_apphtml)
    - 16.2 [Admin Dashboard](#162-admin-dashboard)
    - 16.3 [Client Portal](#163-client-portal)
17. [Embedding Fine-Tuning Pipeline](#17-embedding-fine-tuning-pipeline)
    - 17.1 [Training Data Generation](#171-training-data-generation)
    - 17.2 [LoRA Fine-Tuning (`finetune_embeddings.py`)](#172-lora-fine-tuning-finetune_embeddingspy)
    - 17.3 [Hyperparameter Decisions](#173-hyperparameter-decisions)
18. [LLM Fine-Tuning Pipeline](#18-llm-fine-tuning-pipeline)
    - 18.1 [Training Data Generation](#181-training-data-generation)
    - 18.2 [LoRA Fine-Tuning (Ollama/Unsloth)](#182-lora-fine-tuning-ollamaunsloth)
19. [Evaluation Framework](#19-evaluation-framework)
20. [Testing Strategy](#20-testing-strategy)
21. [Deployment](#21-deployment)
22. [Environment Variables Reference](#22-environment-variables-reference)
23. [Data Flow: End-to-End Request Trace](#23-data-flow-end-to-end-request-trace)
24. [Module Reference Table](#24-module-reference-table)
25. [Content Drip Pipeline — Weekly EKA Content](#25-content-drip-pipeline--weekly-eka-content)
    - 25.1 [Two-Pipeline Model](#251-two-pipeline-model)
    - 25.2 [Data Model Changes](#252-data-model-changes)
    - 25.3 [Weekly Generation (`generate_weekly_eka.py`)](#253-weekly-generation-generate_weekly_ekapy)
    - 25.4 [Scheduler (`weekly_eka_scheduler.py`)](#254-scheduler-weekly_eka_schedulerpy)
    - 25.5 [Content API (`content_api_router.py`)](#255-content-api-content_api_routerpy)
    - 25.6 [Dev Review & Approval Workflow](#256-dev-review--approval-workflow)
    - 25.7 [WhatsApp Delivery](#257-whatsapp-delivery)
    - 25.8 [Patient App — "This Week" Tab](#258-patient-app--this-week-tab)
26. [WhatsApp Inbound Integration](#26-whatsapp-inbound-integration)

---

## 0. Use Cases

NutriChatbot is designed for the Malaysian outpatient clinical setting where dietitians and clinics serve a multilingual, multicultural patient population with complex chronic disease profiles. The following use cases represent the primary scenarios the system is built to handle.

---

### UC-01 — Patient Walks In for Dietary Counselling

**Actor:** Patient (Malay/Chinese/Indian, 30–70 years old)
**Trigger:** Patient is referred by a doctor or self-presents for nutrition advice
**Precondition:** Clinic has registered with NutriChatbot and seeded the patient's profile (conditions, medications, restrictions)

**Flow:**
1. Patient opens the app on a clinic tablet or their phone via a QR code link (`?key=<clinic_api_key>`)
2. Patient types their name → system finds their record
3. Patient confirms identity with their IC number → enters the dashboard
4. Chat opens with a personalised greeting: *"Welcome back, Ahmad! I have your profile on file..."*
5. Patient asks about breakfast options → system retrieves relevant guidelines from the knowledge base + applies Ahmad's T2DM + Halal + low-sodium constraints
6. GPT-4-turbo generates a response naming specific local foods (e.g., Oat porridge, Roti wholemeal), avoiding Nasi Lemak and high-sugar Teh Tarik
7. Patient can ask follow-up questions; the system remembers the full conversation context

**Value delivered:** The dietitian's clinical notes and the clinic's own uploaded guidelines shape every answer — not generic internet advice.

---

### UC-02 — Dietitian Uploads New Clinical Guidelines

**Actor:** Dietitian / Clinic Admin
**Trigger:** New Malaysian CPG (Clinical Practice Guideline) or facility-specific diet sheet is published
**Precondition:** Dietitian has a B2B API key and access to the Client Portal

**Flow:**
1. Dietitian logs into `/portal/` with their API key
2. Uploads PDF (e.g., *Management of Dyslipidaemia 2023, 6th Edition*)
3. System hashes the file for deduplication, parses and chunks it via Unstructured.io
4. Chunks are embedded via bge-m3 + LoRA adapter and stored in the clinic's isolated `client_{id}_knowledge` collection
5. All future patient conversations for this clinic now include this document in retrieval

**Value delivered:** Clinics can keep their knowledge base current without any developer intervention. The knowledge is isolated — other clinics cannot access it.

---

### UC-03 — Chronic Disease Management Follow-Up

**Actor:** Patient with multiple comorbidities (e.g., T2DM + CKD + Hypertension)
**Trigger:** Returning patient with a complex medication-diet interaction question

**Example question:** *"My doctor added Furosemide last week. Are there any foods I need to be more careful about now?"*

**Flow:**
1. Patient logs in → profile loaded (medications list includes Furosemide 40mg OD)
2. RAG retrieves chunks on Furosemide-potassium interaction and fluid restriction guidelines
3. Patient context block in the system prompt already includes `Medications: Furosemide 40mg OD` and `Dietary restrictions: Low potassium, Fluid restriction 1.5L/day`
4. GPT-4 cross-references the retrieved guidelines with the patient's existing profile and generates specific advice — e.g., avoiding high-potassium foods like bananas, coconut water, and herbal soups common in Chinese diet

**Value delivered:** The system connects the newly retrieved drug-diet interaction knowledge with the patient's existing profile to give contextually accurate, personalised advice that a generic chatbot could not produce.

---

### UC-04 — B2B Client Onboarding (New Clinic/Hospital)

**Actor:** Hospital IT Administrator or Clinic Manager
**Trigger:** Hospital wants to deploy NutriChatbot for their dietetic department

**Flow:**
1. Admin contacts NutriChatbot → receives a `nbk_live_{hex}` API key via admin panel
2. Admin configures the URL with `?key=<api_key>` for the clinic tablets/QR codes
3. Admin uploads facility-specific documents (local dietary guidelines, custom diet sheets) via `/portal/`
4. Admin seeds patient records via `seed_patients.py` or the patient management API
5. Clinic goes live — patients can authenticate with IC number and start chatting

**Value delivered:** Full multi-tenant isolation. Hospital A's patients and documents are completely separate from Hospital B's. A single deployment serves multiple clients.

---

### UC-05 — System Administrator Monitors and Improves Model Quality

**Actor:** ML Engineer / System Admin
**Trigger:** Periodic quality review, or after ingesting a new batch of documents

**Flow:**
1. Run `python eval_ragas.py --out results.json` to score the current pipeline on 25 ground-truth questions
2. Review faithfulness (hallucination rate), context_precision (retrieval quality), and answer_relevancy scores
3. If context scores are low: generate more training data (`generate_embedding_training_data.py`) and re-run embedding fine-tuning (`finetune_embeddings.py`)
4. If answer quality is low: update the system prompt in `chain_factory.py` or switch to a stronger LLM
5. Re-run eval to confirm improvement

**Value delivered:** A closed feedback loop — the system can be objectively measured and iteratively improved without subjective testing.

---

## 2. System Flowchart

The following Mermaid diagrams show how all components connect across the four main journeys: patient chat, document ingestion, patient login, and the embedding pipeline.

### 2.1 — Patient Chat Request (End-to-End)

```mermaid
flowchart TD
    A([Patient sends question\nvia patient_app.html]) --> B[POST /chat/get_response\nX-API-Key header]
    B --> C{API Key valid?}
    C -- No --> D([HTTP 401 Unauthorised])
    C -- Yes --> E[Resolve patient profile\nfrom patient_id]
    E --> F{Profile found\nin DB?}
    F -- No --> G[identify_target_disease\nLLM call to extract condition]
    F -- Yes --> H[Build patient_context string\nname, age, BMI, conditions,\nmeds, restrictions, notes]
    G --> I[create_conversational_chain\nchain_factory.py]
    H --> I
    I --> J[MergedRetriever\nvector_store.py]
    J --> K[Embed query\nbge-m3 + LoRA adapter\nembeddings.py]
    K --> L[Cosine search\nbase_knowledge\npgvector]
    K --> M[Cosine search\nclient_id_knowledge\npgvector]
    L --> N[Merge + deduplicate\ntop ~8 chunks]
    M --> N
    N --> O[Build prompt\nSystem: ADIME + patient block\nHistory: prior turns\nContext: retrieved chunks\nHuman: question]
    O --> P{USE_OLLAMA?}
    P -- false --> Q[GPT-4-turbo\nOpenAI API]
    P -- true --> R[Local Ollama model\nnuTribot / adime-final]
    Q --> S[Parse response\nfor IMAGE markers\nimage_handler.py]
    R --> S
    S --> T[StreamingResponse\nSSE char-by-char]
    T --> U([Patient sees answer\nin real time])
    T --> V[Append to session memory\n_session_store]
```

### 2.2 — Patient Login & IC Verification

```mermaid
flowchart TD
    A([Patient opens app\npatient_app.html]) --> B{API key in URL\n?key=...}
    B -- Yes --> C[Show Connected badge\nSkip key input]
    B -- No --> D[Show key input field]
    C --> E[Patient types name]
    D --> E
    E --> F[POST /patient/login\nname lookup]
    F --> G{Match found?}
    G -- No match --> H([Show error\nCheck spelling or\ncontact clinic])
    G -- Multiple matches --> I[Show IC input\nfor disambiguation]
    G -- Single match --> I
    I --> J[Patient enters IC number\nauto-formatted YYMMDD-SS-XXXX]
    J --> K[POST /patient/login\nwith ic_number]
    K --> L{IC matches\nrecord?}
    L -- No --> M([Show error\nIC not matched])
    L -- Yes --> N[Load full patient profile\nfrom DB]
    N --> O[Transition to Dashboard]
    O --> P[Show patient sidebar\nconditions, meds,\ndiet, allergies]
    O --> Q[Open chat with\npersonalised greeting]
```

### 2.3 — Document Ingestion Pipeline

```mermaid
flowchart TD
    A([Admin uploads PDF/DOCX\nvia /portal/ or API]) --> B[SHA-256 hash\nfor deduplication]
    B --> C{Hash already\nin DB?}
    C -- Yes --> D([Skip — return status: skipped])
    C -- No --> E[Unstructured.io partition\nstrategy: fast]
    E --> F{Text\nextracted?}
    F -- No --> G[Retry with hi_res\nTesseract OCR\nlanguages: eng + msa]
    F -- Yes --> H[chunk_by_title\nmax 1500 chars\nmin 500 chars]
    G --> H
    H --> I[Strip NUL bytes\nfrom each chunk]
    I --> J[Embed all chunks\nbge-m3 + LoRA adapter\nCPU]
    J --> K[Batch insert into pgvector\nclient_id_knowledge collection\nbatch size 100]
    K --> L[Record metadata in PostgreSQL\ndocument_metadata table]
    L --> M([Return chunk_count\nand status: completed])

    subgraph Base Knowledge Build
    N([Admin runs build_base_db.py\nBASE_DOCS_DIR=...]) --> O[Scan directory\nskip ._ files]
    O --> P{File in\nfile_tracker.json?}
    P -- Up to date --> Q([Skip])
    P -- New or changed --> R[ProcessPoolExecutor\n4 parallel workers]
    R --> S[Same partition +\nchunk pipeline as above]
    S --> T[Embed + insert into\nbase_knowledge collection\nbatch size 500]
    T --> U[Update file_tracker.json]
    end
```

### 2.4 — Embedding Fine-Tuning Pipeline

```mermaid
flowchart TD
    A([pgvector base_knowledge\n35,000+ chunks]) --> B[generate_embedding_training_data.py\nfetch all chunks via psycopg2]
    B --> C[For each chunk:\ncall Ollama / GPT-4\ngenerate 2 questions]
    C --> D[Save as JSONL pairs\nanchor: question\npositive: chunk text]
    D --> E[~/data/embedding_train.jsonl\n~62,000 pairs]
    D --> F[~/data/embedding_val.jsonl\n~7,000 pairs]

    E --> G[finetune_embeddings.py]
    F --> G
    G --> H[Load BAAI/bge-m3\nbase model]
    H --> I[Attach LoRA adapter\nr=16, alpha=32\ntargets: query + value]
    I --> J[MultipleNegativesRankingLoss\nin-batch negatives\neffective batch 32]
    J --> K[Train 3 epochs\nbf16, RTX 3050\n~45-60 min]
    K --> L[Save adapter weights\n~/models/embedding_lora/]

    L --> M[Set EMBEDDING_ADAPTER_PATH\nin .env]
    M --> N[embeddings.py loads\nbase model + adapter on CPU]
    N --> O[Rebuild vector store\nbuild_base_db.py]
    O --> P([All future queries use\nfine-tuned embeddings])
```

### 2.5 — Full System Component Map

```mermaid
flowchart LR
    subgraph Clients
        PA([Patient App\npatient_app.html])
        CP([Client Portal\n/portal/])
        AD([Admin Panel\n/admin/])
        API([B2B API\nexternal integrations])
    end

    subgraph FastAPI [FastAPI — app.py :8000]
        WC[website_chat_router\n/chat/get_response]
        PR[patient endpoints\n/patient/login\n/patients/]
        DM[document endpoints\n/upload_documents/\n/documents/]
        CR[client_portal_router]
        AR[admin_router]
    end

    subgraph Auth
        DEP[dependencies.py\nget_api_client\nget_db]
    end

    subgraph RAG [RAG Pipeline]
        RAG1[rag.py\norchestration]
        RAG2[chain_factory.py\nLCEL chain + prompt]
        RAG3[vector_store.py\nMergedRetriever]
        RAG4[llm.py\nChatOpenAI / ChatOllama]
    end

    subgraph Embeddings
        EM[embeddings.py\nsingleton]
        BGE[BAAI/bge-m3\nbase model]
        LORA[LoRA adapter\n~/models/embedding_lora/]
    end

    subgraph Storage
        PG[(PostgreSQL\napi_clients\npatients\ndocument_metadata)]
        VEC[(pgvector\nbase_knowledge\nclient_id_knowledge)]
    end

    subgraph LLM
        GPT[GPT-4-turbo\nOpenAI API]
        OLL[Ollama\nnuTribot / adime-final]
    end

    PA --> WC
    PA --> PR
    CP --> CR
    AD --> AR
    API --> WC
    API --> DM

    WC --> DEP
    PR --> DEP
    DM --> DEP
    CR --> DEP
    AR --> DEP

    DEP --> PG
    WC --> RAG1
    RAG1 --> RAG2
    RAG1 --> RAG3
    RAG2 --> RAG4
    RAG3 --> EM
    EM --> BGE
    EM --> LORA
    RAG3 --> VEC
    RAG4 --> GPT
    RAG4 --> OLL
    PR --> PG
    DM --> PG
    DM --> VEC
```

---

## 3. High-Level Architecture Diagram

NutriChatbot is a multi-tenant B2B SaaS nutrition counselling chatbot built on a Retrieval-Augmented Generation (RAG) pipeline. Its core role is to act as an AI dietitian, guiding patients through the **ADIME nutrition care process** (Assessment → Diagnosis → Intervention → Monitoring & Evaluation) with specific awareness of the Malaysian multicultural food context.

Key design properties:

- **Multi-tenant**: Each B2B client gets an isolated knowledge base alongside a shared foundational knowledge base. A single API key identifies the tenant for every request.
- **Patient-aware**: Patients can log in with their name and IC number. Their full medical profile (conditions, medications, dietary restrictions, allergies, BMI) is automatically injected into every LLM prompt for personalised counselling.
- **Hybrid RAG**: Every query simultaneously retrieves from a shared `base_knowledge` collection (medical/nutrition guidelines) and the client's own `client_{id}_knowledge` collection, then merges and deduplicates.
- **Multilingual**: Embedding model (`BAAI/bge-m3`) natively handles both English and Bahasa Melayu documents and queries. OCR pipeline includes Malay language support.
- **Dual LLM backend**: Defaults to OpenAI `gpt-4-turbo` but can switch to a locally hosted LoRA fine-tuned model (via Ollama) by setting one environment variable.
- **Streaming**: Responses are streamed as Server-Sent Events (SSE) for real-time user experience.

---

## 2. High-Level Architecture Diagram

```
                         ┌─────────────────────────────────────────────────┐
                         │               CLIENT APPLICATIONS                │
                         │  Patient App (/)  │  B2B API  │  Admin / Portal  │
                         └──────────────────────┬──────────────────────────┘
                                                │  HTTPS  (X-API-Key header)
                                                ▼
                         ┌─────────────────────────────────────────────────┐
                         │           FastAPI  (app.py)   :8000              │
                         │  ┌──────────────┐ ┌──────────┐ ┌─────────────┐ │
                         │  │ /chat/*      │ │ /admin/* │ │ /portal/*   │ │
                         │  │ /patients/*  │ │ (HTML UI)│ │ (HTML UI)   │ │
                         │  └──────┬───────┘ └──────────┘ └─────────────┘ │
                         │  ┌──────▼────────────────────────────────────┐  │
                         │  │  dependencies.py  (API key → client)      │  │
                         │  └──────┬────────────────────────────────────┘  │
                         └─────────┼───────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │           rag.py                  │
                    │  1. identify_target_disease()     │
                    │     (skipped if patient_id given) │
                    │  2. build patient_context string  │
                    │  3. create_conversational_chain() │
                    │  4. chain.invoke()                │
                    │  5. parse_response_for_image()    │
                    └──────────────┬──────────────────┘
                                   │
       ┌───────────────────────────┼──────────────────────────────┐
       │                           │                              │
┌──────▼──────────┐   ┌────────────▼──────────────┐  ┌──────────▼──────────┐
│  vector_store   │   │     chain_factory.py        │  │   image_handler.py  │
│  MergedRetriever│   │  LCEL + ADIME prompt        │  │  [IMAGE:] parser    │
│  ┌───────────┐  │   │  + patient profile block    │  └─────────────────────┘
│  │base_know- │  │   │  + RunnableWithHistory      │
│  │  ledge    │  │   └────────────┬───────────────┘
│  ├───────────┤  │                │
│  │client_{id}│  │   ┌────────────▼──────────────┐
│  │_knowledge │  │   │          llm.py            │
│  └───────────┘  │   │  ChatOpenAI / ChatOllama   │
│  embeddings.py  │   └───────────────────────────┘
│  BAAI/bge-m3    │
│  + LoRA adapter │
└─────────────────┘
         │
┌────────▼──────────────────────────────────────────────────┐
│                  PostgreSQL + pgvector                      │
│  Tables: langchain_pg_collection, langchain_pg_embedding   │
│  Collections: base_knowledge, client_1_knowledge, …        │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│          PostgreSQL (relational, via SQLAlchemy)            │
│  Tables: api_clients, document_metadata, patients          │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Web framework | FastAPI | Latest via pip |
| ASGI server | Uvicorn + Gunicorn | `uvicorn.workers.UvicornWorker` in production |
| Language model (cloud) | OpenAI `gpt-4-turbo` | Configurable via `OPENAI_MODEL` |
| Language model (local) | Ollama + custom LoRA model | Toggled via `USE_OLLAMA=true` |
| Embedding model | `BAAI/bge-m3` | 570M params, 1024-dim, multilingual, runs on CPU |
| Embedding fine-tuning | PEFT + sentence-transformers 3.x | LoRA on bge-m3, RTX 3050 4GB |
| LLM orchestration | LangChain 0.1.x LCEL | `langchain==0.1.20`, `langchain-core==0.1.52` |
| Vector store | pgvector on PostgreSQL | `langchain-community` `PGVector` |
| Relational DB | PostgreSQL | SQLAlchemy ORM |
| Document parsing | Unstructured.io ≥ 0.11 | Supports PDF, DOCX, OCR fallback |
| OCR (Malay) | Tesseract + `tesseract-ocr-msa` | For scanned Bahasa Melayu PDFs |
| Password hashing | werkzeug PBKDF2 | `generate_password_hash` / `check_password_hash` |
| Session caching | Redis (optional) | In-memory dict fallback |
| Evaluation | RAGAS | faithfulness, answer_relevancy, context_precision, context_recall |
| Container | Docker | `python:3.11-slim` base |

---

## 4. Application Entry Point & Startup

**File:** `app.py`

On startup:

1. Loads environment variables from `.env` via `python-dotenv`.
2. Creates a FastAPI instance.
3. Mounts `/images` as a static file directory pointing to `data/images/`.
4. Registers a `startup_event` that calls `db.create_db_and_tables()` to ensure all relational tables exist (including the `patients` table).
5. Adds CORS middleware with `allow_origins=["*"]`.
6. Registers routers: `/admin`, `/portal`, `/chat`.
7. Defines document management REST endpoints directly on the app.
8. Serves `patient_app.html` at `GET /` and the legacy test UI at `GET /dev`.

**Route change (April 2026):** The root `/` now serves the production patient-facing app. The original developer test UI was moved to `/dev`. This was done because the patient app is the primary end-user interface and should occupy the canonical URL.

---

## 5. Routing & API Surface

### Chat API — `website_chat_router.py`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chat/get_response` | `X-API-Key` | Streaming SSE chat response |
| POST | `/chat/get_response_sync` | `X-API-Key` | Non-streaming chat response (used by the 4-minute keep-alive cron, §22) |

### WhatsApp Webhooks — `whatsapp_router.py` (mounted under `/chat`, §26)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chat/whatsapp` | Twilio signature (`X-Twilio-Signature`) | Twilio inbound webhook (form-encoded) |
| GET | `/chat/whatsapp/meta` | `hub.verify_token` vs `META_VERIFY_TOKEN` | Meta Cloud API verification handshake |
| POST | `/chat/whatsapp/meta` | Meta payload signature | Meta Cloud API inbound webhook (JSON) |

**Request body (`ChatRequest`):**
```json
{
  "question": "What should I eat for breakfast?",
  "session_id": "user-abc-session-1",
  "profile": { ... },
  "patient_id": 3
}
```

`patient_id` (added April 2026): When provided, the server auto-loads the patient's full medical record from the database and constructs the `profile` dict automatically. This removes the burden from the caller to manage profile data and ensures the profile is always authoritative and up-to-date from the DB.

`profile` (legacy): A manually-supplied profile dict. Still supported. When both `patient_id` and `profile` are provided, `patient_id` takes precedence.

### Patient API — `app.py`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/patient-login` | `X-API-Key` | Name-based patient lookup (step 1 of login) |
| POST | `/patient-verify` | `X-API-Key` | IC number verification (step 2 of login) |
| GET | `/patients/` | `X-API-Key` | List all patients for this client |
| GET | `/patients/{id}` | `X-API-Key` | Get a specific patient's full record |

### Document Management — `app.py`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/upload_documents/` | `X-API-Key` | Upload one or more PDF/DOCX files |
| GET | `/documents/` | `X-API-Key` | List all documents for this client |
| DELETE | `/documents/{id}` | `X-API-Key` | Delete a document from DB and vector store |

### Admin / Portal

Same as previous — see sections 16.2 and 16.3.

---

## 6. Authentication & Authorization

### 6.1 B2B API Key Authentication

All client-facing endpoints use `get_api_client()` as a FastAPI `Depends` injection (file: `dependencies.py`).

**Key format:** `nbk_live_{64 hex chars}` — generated by `secrets.token_hex(32)` prefixed with `nbk_live_`.

**Storage:** Only the werkzeug PBKDF2 hash is stored. The raw key is shown once at creation. Hash comparison is sequential (not indexed) to prevent timing-based enumeration.

### 6.2 Patient Authentication

Patients authenticate via a two-step UI flow (not a JWT/session token system — it is a stateless lookup on each chat request):

1. **Step 1 — Name lookup:** `POST /patient-login` with `{ name, ic_number? }`. Returns the matched patient record or a multi-match indicator.
2. **Step 2 — IC verification:** `POST /patient-verify` with `{ patient_id, ic_number }`. Confirms identity before granting access to the chat dashboard.

**Why IC number, not password?** Malaysian healthcare workflows use IC (Identity Card) number as the primary patient identifier. This removes the need for patients to manage a separate password, reducing friction for elderly or less tech-savvy users.

---

## 7. Patient Identity System

### 7.1 Patient Database Model

**File:** `database.py` — `Patient` SQLAlchemy model

```
patients table
├── id              Integer PK
├── client_id       Integer FK → api_clients.id (CASCADE DELETE)
├── name            String (NOT NULL)
├── ic_number       String (indexed) — Malaysian IC format: YYMMDD-SS-XXXX
├── age             Integer
├── gender          String — "Male" / "Female"
├── ethnicity       String — "Malay" / "Chinese" / "Indian"
├── weight_kg       Float
├── height_cm       Float
├── conditions      JSON  — list of condition strings
├── medications     JSON  — list of medication strings
├── dietary_restrictions  JSON — list of restriction strings
├── allergies       JSON  — list of allergen strings
├── notes           String — free-text clinical notes
├── username        String (UNIQUE, indexed)
└── hashed_password String — werkzeug PBKDF2
```

**Key design decisions:**

- `conditions`, `medications`, `dietary_restrictions`, `allergies` are stored as **JSON arrays** (not normalised relational tables). This avoids schema complexity for a field whose values vary widely per patient and change infrequently. The trade-off is no indexed querying on individual conditions, which is acceptable since the primary query pattern is "load all conditions for one patient", not "find all patients with condition X".

- `ic_number` is stored as a plain string but normalised on lookup (`get_patient_by_ic` strips dashes and spaces before comparing) to handle user input formatting inconsistencies.

- `client_id` FK with `CASCADE DELETE` ensures that deleting a B2B client automatically removes all their patient records, maintaining referential integrity without manual cleanup.

**CRUD functions added to `database.py`:**

| Function | Description |
|---|---|
| `add_patient(db, client_id, ...)` | Hashes password, inserts Patient row |
| `get_patient(db, patient_id)` | Lookup by PK |
| `get_patient_by_username(db, username)` | Exact match |
| `get_patient_by_ic(db, ic_number)` | Normalises IC, exact match |
| `get_patients_by_client(db, client_id)` | All patients for a tenant |
| `check_patient_login(db, username, password)` | Hash-verified login |
| `patient_to_profile_dict(patient)` | Converts ORM object to RAG profile dict |

The `patient_to_profile_dict` function uses the key `"condition"` (not `"conditions"`) to match the pre-existing schema expected by `rag.py`'s profile handling logic.

### 7.2 Patient Login & IC Verification Flow

**File:** `patient_app.html` (frontend) + `app.py` (backend)

```
Screen 1 (Login)
  └─ User enters name
  └─ POST /patient-login → DB lookup by name (exact → ILIKE fallback)
     ├─ Single match  → proceed to Screen 2
     ├─ Multiple matches → prompt for IC to narrow down
     └─ No match → error

Screen 2 (IC Verification)
  └─ User enters IC number (auto-formatted as YYMMDD-SS-XXXX)
  └─ POST /patient-verify → DB lookup by IC, confirms patient_id match
     ├─ Match → proceed to Screen 3
     └─ No match → error

Screen 3 (Dashboard + Chat)
  └─ Patient profile shown in sidebar (conditions, meds, diet, allergies)
  └─ All chat requests include patient_id in body
  └─ Server auto-loads profile from DB on each request
```

**Why two-step?** A single name lookup would fail for common Malaysian names (e.g., "Ahmad" appears frequently). IC number as the second factor provides unambiguous identity verification without requiring a traditional password.

### 7.3 Profile Injection into RAG

**File:** `rag.py`

When a patient is identified, the profile dict is converted to a structured `patient_context` string injected into the LLM system prompt:

```
Name: Ahmad Fadzillah bin Roslan
Age: 52
Gender: Male
Ethnicity: Malay
Weight: 88.0kg, Height: 168.0cm, BMI: 31.2
Conditions: Type 2 Diabetes, Hypertension
Medications: Metformin 500mg BD, Lisinopril 10mg OD, Aspirin 100mg OD
Dietary restrictions: Halal only, Low sodium, Low simple carbohydrates
Clinical notes: Office administrator, sedentary lifestyle. Eats Nasi Lemak...
```

This block is inserted into the `chain_factory.py` system prompt between the role definition and the ADIME framework instructions. The LLM is instructed to address the patient by name, tailor food suggestions to their ethnicity, and respect all restrictions without exception.

**Why inject into system prompt vs. human message?** System prompt injection means the profile context persists across the entire conversation and cannot be overridden by user messages. Injecting into the human message would require repeating it every turn and risks the model treating it as user input rather than clinical context.

### 7.4 PatientStore Abstraction

**File:** `patient_store.py`

The `PatientStore` ABC decouples the bot from any specific patient data backend. All code that reads or writes patient profiles goes through this interface.

```python
class PatientStore(ABC):
    def get_profile(self, patient_id: int) -> dict | None: ...
    def update_supplementary_fields(
        self, patient_id: int, updates: dict, source_session_id: str | None = None
    ) -> dict: ...
```

| Implementation | File | Status |
|---|---|---|
| `LocalPatientStore` | `local_patient_store.py` | Current default (dev/staging) — wraps SQLAlchemy ORM |
| `RemotePatientStore` | `remote_patient_store.py` | **Scaffold built 12 June 2026** — calls hospital REST API (placeholder contract, see below) |

**Swap point — `get_patient_store()` factory** (`patient_store.py`): both `website_chat_router.py` and `whatsapp_router.py` call `patient_store = get_patient_store()`. The factory returns `RemotePatientStore` if the `HOSPITAL_API_URL` env var is set, else `LocalPatientStore`. No env var is set today, so dev/staging behaviour is unchanged — flipping to the hospital backend in production is a single `.env` edit.

**`RemotePatientStore` placeholder REST contract** (flat JSON, not FHIR — adjust `_to_profile_dict()`, `_PATIENT_PATH`, `_SUPPLEMENTARY_PATH` once the real hospital schema is known):
- `GET {HOSPITAL_API_URL}/patients/{patient_id}` → 200 flat profile dict (same shape as `LocalPatientStore.get_profile()`) or 404
- `PATCH {HOSPITAL_API_URL}/patients/{patient_id}/supplementary` with `{"updates": {...}, "source_session_id": "..."}` → 200 `{"applied": {...}}` or 404
- Env vars: `HOSPITAL_API_URL`, `HOSPITAL_API_KEY` (Bearer token), `HOSPITAL_API_TIMEOUT_S` (default 10s)

**`mock_hospital_api.py`** — standalone FastAPI app implementing the contract above with an in-memory patient (seeded with patient 1's shape), used to test `RemotePatientStore` before the real hospital API exists. **`scripts/test_remote_patient_store.py`** spins this up on port 8500 and exercises `RemotePatientStore` end-to-end (get_profile found/404, update with allowed/rejected fields, persistence check) — all assertions pass.

**Known gap:** the *read* path (`_resolve_patient_profile` in website, `_process_and_reply` in WhatsApp) still builds the RAG profile via `db.patient_to_profile_dict(patient)` directly from the local DB, not via `patient_store.get_profile()`. Only the *write* path (`update_supplementary_fields`) is fully routed through `patient_store` so far. Full read-path swap-over is future work for when real hospital endpoints exist.

**`SUPPLEMENTARY_FIELDS` whitelist** (defined in `patient_store.py`): an explicit set of every DB column the extractor is allowed to write. Any key not in this set is silently rejected by `update_supplementary_fields`. This prevents the extractor from ever touching clinical fields (`conditions`, `medications`, `allergies`, etc.) that are owned by the hospital system.

Current whitelist: `fluid_intake_ml`, `alcohol_per_week`, `supplements`, `religion`, `tobacco_status`, `meals_per_day`, `snacks_per_day`, `processed_food_freq`, `fast_food_freq`, `self_prepared_freq`, `caffeine_mg_per_day`, `sugar_drinks_ml`, `activity_freq`, `activity_minutes`, `activity_intensity`, `food_avoidance`, `nutrition_knowledge`, `readiness_to_change`, `sodium_awareness`, `fat_intake_level`, `fat_sources`, `medication_compliance`, `activity_types`.

**Provenance:** Every write through `update_supplementary_fields` records metadata in the `extractor_metadata` JSON column: `{field: {confidence, last_updated, source_session_id}}`. This creates an audit trail of what the bot inferred and from which session.

---

### 7.5 Profile Extractor — Dynamic Data Collection

**File:** `extractor.py`  
**Schema version:** v2.0-cardiac | **Active fields:** 13 | **Languages:** English + Bahasa Malaysia

The extractor is a passive data collection layer that runs silently on every patient message. It analyses what the patient says and fills in supplementary profile fields that the hospital system does not supply — things like how much water they drink, whether they take their medication regularly, or what types of cooking oil they use. Over several conversations, the patient profile becomes progressively richer without ever requiring the patient to fill in a form.

**Design guarantees:**
- **Conservative** — only extracts what is explicitly stated; never infers or assumes
- **Additive** — only fills fields that are currently empty (`None`, `[]`, `""`); never overwrites
- **Whitelist-constrained** — all writes go through `SUPPLEMENTARY_FIELDS`; clinical fields (`conditions`, `medications`, etc.) cannot be touched regardless of what the LLM returns
- **Fault-tolerant** — any error (Ollama unreachable, bad JSON, validation failure) returns `{}` and logs; the user-facing response is never affected
- **Zero user-facing latency** — runs as an `asyncio.create_task()` concurrently with the streaming response; the patient sees no delay

#### How it fits into the chat request flow

```
POST /chat/get_response (patient_id=4, question="I fry with palm oil every day lah")
    │
    ├─ asyncio.create_task(_run_extractor_background(...))   ← dispatched immediately
    │      runs concurrently, patient never waits for this
    │
    └─ StreamingResponse(stream_rag_response(...))           ← patient sees answer now
           │
           └─ [~2-5s later, in background]
                  extract_from_message(message, current_profile)
                  → {"fat_intake_level": "high", "fat_sources": ["palm oil"]}
                  patient_store.update_supplementary_fields(patient_id=4, updates=...)
                  → Profile updated silently; next request will include fat context
```

The extractor task is fire-and-forget from the user's perspective. Its results accumulate across sessions — each conversation fills in a few more fields until the profile reaches the depth needed for fully personalised advice.

#### Full extraction pipeline

```
Patient message (any language)
    │
    ▼
_build_field_descriptions()
    ← Formats all 13 EXTRACTOR_FIELDS into a structured list for the prompt
    ← Each field includes: name, type hint, guidance with BM ↔ EN mappings
    │
    ▼
_build_known_summary(current_profile)
    ← Lists already-filled fields so the LLM skips them
    ← Example: "  tobacco_status: Never smoked" → LLM won't re-extract this
    │
    ▼
EXTRACTION_PROMPT.format(field_descriptions, known, message)
    ← Single structured prompt:
       - Role: clinical data extractor
       - Language: "patient may write in English, Bahasa Malaysia, or a mix (rojak)"
       - Critical rules: only explicit, no inference, allowed_values only
       - What's already known: filled fields summary
       - The patient's message
    │
    ▼
call_ollama_extractor(prompt)
    ← POST to qwen2.5:32b at OLLAMA_BASE_URL/api/generate
    ← temperature=0.0 (deterministic — medical data must not vary between calls)
    ← num_predict=250 (caps output; forces compact JSON, not paragraphs)
    ← timeout=30s
    │
    ▼
_strip_json_response(raw_text)
    ← Removes ```json ... ``` fences and leading/trailing whitespace
    ← LLMs often wrap JSON in markdown even when instructed not to
    │
    ▼
json.loads(cleaned)
    ← Parses the JSON dict; returns {} on any decode error (logged)
    │
    ▼
_validate_extraction(extracted_dict)
    ← Per-field validation — each field has its own validator:
       • Integer fields: range check (e.g., 0 < fluid_intake_ml < 10000)
       • allowed_values fields: exact string match against an enum
       • List fields: all elements must be non-empty strings
       • String fields: non-empty, length limit
    ← Unknown or invalid fields dropped silently
    │
    ▼
_filter_already_filled(validated, current_profile)
    ← Drops any field that already has a non-null, non-empty value in the profile
    ← This is the "additive-only" guarantee — extractor never overwrites
    │
    ▼
return new_fields dict
    │
    ▼
patient_store.update_supplementary_fields(patient_id, new_fields, session_id)
    ← SUPPLEMENTARY_FIELDS whitelist check (second line of defence)
    ← setattr() applies each value to the Patient ORM object
    ← extractor_metadata[field] = {last_updated, source_session_id}  ← provenance
    ← session.commit()
```

#### Bahasa Malaysia support

The extraction prompt explicitly states that the patient may write in English, Bahasa Malaysia, or a mix. The guidance for each field includes BM-to-EN mappings so qwen2.5:32b can correctly normalise values regardless of input language:

| BM patient says | Extracted as |
|---|---|
| `"Saya tidak pernah merokok"` | `tobacco_status: "Never smoked"` |
| `"Saya goreng dengan minyak sawit setiap hari"` | `fat_intake_level: "high"`, `fat_sources: ["palm oil"]` |
| `"Kadang-kadang saya terlupa ambil ubat"` | `medication_compliance: "variable"` |
| `"Saya minum 6 gelas air sehari"` | `fluid_intake_ml: 1500` |
| `"Saya berjoging 3 kali seminggu, 30 minit"` | `activity_freq: "3 times a week"`, `activity_minutes: 30`, `activity_types: ["jogging"]` |

#### EXTRACTOR_FIELDS — v2 (13 fields, cardiac focus)

**Tier 1 — Critical (must collect for safe cardiac advice):**

| Field | eNCPT | Type | Allowed Values / Range |
|---|---|---|---|
| `fluid_intake_ml` | FH-1.2.1.1.1 | integer (mL/day) | `0 < value < 10000` |
| `alcohol_per_week` | FH-1.4.1.1 | integer (drinks/wk) | `0 ≤ value < 200` |
| `tobacco_status` | CH-1.1.10 | string | `Never smoked` · `Current smoker` · `Former smoker` |
| `fat_intake_level` | FH-1.5.1.1 | string | `low` · `moderate` · `high` |
| `sodium_awareness` | FH-1.5.6.1 | string | `low_awareness_high_intake` · `moderate` · `actively_restricting` |
| `religion` | CH-3.1.7 | string | free text (`len < 100`) |
| `supplements` | FH-3.2.1 | list of strings | non-empty elements |

**Tier 2 — Important (significantly improves personalisation):**

| Field | eNCPT | Type | Allowed Values / Range |
|---|---|---|---|
| `medication_compliance` | FH-3.1.1.1 | string | `good` · `variable` · `poor` |
| `fat_sources` | FH-1.5.1.2 | list of strings | raw food names (lowercased) |
| `activity_freq` | FH-7.3.1 | string | free text (`len < 100`), e.g. `"3 times a week"` |
| `activity_minutes` | FH-7.3.2 | integer (min/session) | `0 < value < 300` |
| `activity_types` | FH-7.3.1.1 | list of strings | activity names (lowercased) |
| `activity_intensity` | FH-7.3.3 | string | `light` · `moderate` · `vigorous` |

#### Provenance metadata

Every field written by the extractor is recorded in the `extractor_metadata` JSON column:

```json
{
  "fat_intake_level": {
    "last_updated": "2026-05-14T09:23:11+00:00",
    "source_session_id": "uuid-abc-123"
  },
  "medication_compliance": {
    "last_updated": "2026-05-14T09:23:11+00:00",
    "source_session_id": "uuid-abc-123"
  }
}
```

This creates a full audit trail of what the bot inferred, from which session, and when. It also powers the `_build_known_summary()` function — before each extraction, the extractor checks what is already filled and excludes those fields from the prompt so the LLM doesn't re-extract stale data.

#### Key functions

| Function | Description |
|---|---|
| `extract_from_message(message, current_profile)` | Main entry point. Returns `{}` on any error — never raises. |
| `call_ollama_extractor(prompt)` | POST to `OLLAMA_BASE_URL/api/generate`; `temperature=0.0`; `num_predict=250`; `timeout=30s` |
| `_build_field_descriptions()` | Formats `EXTRACTOR_FIELDS` into a structured list for the prompt, including BM guidance |
| `_build_known_summary(profile)` | Lists already-filled supplementary fields so the LLM skips re-extraction |
| `_strip_json_response(text)` | Removes ` ```json ``` ` fences and whitespace from LLM output |
| `_validate_field(key, value)` | Per-field validator returning `(valid: bool, cleaned_value)` |
| `_validate_extraction(extracted)` | Applies `_validate_field` to all extracted keys; silently drops invalid entries |
| `_filter_already_filled(extracted, profile)` | Drops fields that already have a non-null, non-empty value |

#### Why qwen2.5:32b, not CLaRa-7B?

CLaRa-7B is optimised for compressed-context retrieval — it excels at reading a passage and generating domain-specific answers. qwen2.5:32b is a larger general-purpose instruction model that follows structured output formats (JSON) far more reliably. The extractor's job is a structured extraction task, not a retrieval task. The extraction call is capped at 250 tokens output and runs once per message asynchronously, so the extra latency (qwen2.5:32b is ~3-5× slower than CLaRa) is never user-facing.

#### Demo

A standalone demo script is provided at `scripts/demo_extractor.py`. It runs the full extraction pipeline against a real patient record and shows the before/after profile state. Requires Ollama reachable at `OLLAMA_BASE_URL`:

```bash
python scripts/demo_extractor.py
python scripts/demo_extractor.py --patient-id 4   # default: Hafizuddin (dyslipidaemia + obesity)
python scripts/demo_extractor.py --patient-id 7   # Rajendran (post-CABG, L3)
python scripts/demo_extractor.py --reset          # clear supplementary fields before demo
```

---

### 7.6 Nutrition Assessment Priority List — eNCPT v2 Cardiac Schema

**Files:** `data/encpt/encpt_curated.json` (machine-readable), `data/encpt/encpt_curated.md` (dietitian review doc)
**Version:** v2.0-cardiac | **Total fields:** 34 | **Languages:** EN + Bahasa Malaysia

The eNCPT (electronic Nutrition Care Process Terminology) schema defines what supplementary patient data the chatbot collects during conversation. Every field maps to an eNCPT 2020 code for EHR integration. The v2 schema was specialised for cardiac patients per dietitian consultation in May 2026.

**Schema generation workflow:**
```bash
# Edit the schema definition:
vim data/encpt/build_curated_schema.py

# Regenerate the JSON and human-readable markdown:
python data/encpt/build_curated_schema.py
python data/encpt/json_to_md.py data/encpt/encpt_curated.json data/encpt/encpt_curated.md

# Send encpt_curated.md to the supervising dietitian for review.
```

**Priority tiers:**

| Tier | Description | Field count | Bot behaviour |
|---|---|---|---|
| **Tier 1 — Critical** | Must collect for safe cardiac dietary advice | 7 | Do not give nutritional recommendations without these |
| **Tier 2 — Important** | Significantly improves personalisation | 17 | Collect during the first few sessions |
| **Tier 3 — Nice to Have** | Adds context for long-term care | 10 | Collect opportunistically during conversation |

**Tier 1 — Critical (7 fields):**

| eNCPT Code | Field | DB Column | Relevant For |
|---|---|---|---|
| FH-1.2.1.1.1 | Total fluid intake (mL/day) | `fluid_intake_ml` | Heart Failure, CKD, Hypertension |
| FH-1.4.1.1 | Alcohol intake (drinks/week) | `alcohol_per_week` | All patients |
| CH-1.1.10 | Tobacco use | `tobacco_status` | Cardiac, HTN, Dyslipidaemia |
| FH-1.5.1.1 🆕 | Total fat intake (qualitative: low/moderate/high) | `fat_intake_level` | Cardiac, Dyslipidaemia |
| FH-1.5.6.1 ↑ | Sodium intake / awareness | `sodium_awareness` | Cardiac, HTN, Heart Failure, CKD |
| FH-1.6 | Food allergies and intolerances | `extractor_food_allergies` *(pending migration)* | All patients |
| CH-3.1.7 | Religion (affects diet) | `religion` | All patients |

🆕 New in v2. ↑ Promoted from Tier 2 in v2 (critical for cardiac).

**Tier 2 — Important (17 fields):**

| eNCPT Code | Field | DB Column | Relevant For |
|---|---|---|---|
| FH-3.1.1.1 🆕 | Medication compliance (good/variable/poor) | `medication_compliance` | Cardiac, HTN, Heart Failure |
| FH-1.5.1.2 🆕 | Fat type sources (raw food sources) | `fat_sources` | Cardiac, Dyslipidaemia |
| FH-7.3.1 | Physical activity frequency | `activity_freq` | All |
| FH-7.3.2 | Physical activity duration (minutes) | `activity_minutes` | All |
| FH-7.3.1.1 🆕 | Type of physical activity | `activity_types` | Cardiac, Heart Failure |
| FH-7.3.3 | Physical activity intensity (light/moderate/vigorous) | `activity_intensity` | Cardiac, Heart Failure |
| FH-1.4.3.1 | Caffeine intake (mg/day) | `caffeine_mg_per_day` | Cardiac, HTN, Atrial Fibrillation |
| FH-1.2.2.3.1.1 | Meals per day | `meals_per_day` | Diabetes, HTN |
| FH-1.2.2.3.1.2 | Snacks per day | `snacks_per_day` | Diabetes, Obesity |
| FH-1.2.2.2.5 | Processed food intake frequency | `processed_food_freq` | Cardiac, HTN, Dyslipidaemia, Obesity |
| FH-1.2.2.2.6 | Fast food / takeaway frequency | `fast_food_freq` | Cardiac, HTN, Dyslipidaemia, Obesity, Diabetes |
| FH-1.2.2.2.7 | Self-prepared food frequency | `self_prepared_freq` | All |
| FH-1.2.1.1.1.3 | Sugar-sweetened beverage intake (mL/day) | `sugar_drinks_ml` | Diabetes, Obesity, Cardiac |
| FH-5.2.1 | Food avoidance (voluntary) | `food_avoidance` | All |
| FH-5.4.1 | Cultural/religious eating practices | *(derived from `religion`)* | All |
| FH-4.1.3 | Nutrition knowledge (1–5 scale) | `nutrition_knowledge` | All |
| FH-4.2.8 | Readiness to change | `readiness_to_change` | All |

**Tier 3 — Nice to Have (10 fields):**

| eNCPT Code | Field | Relevant For | Note |
|---|---|---|---|
| FH-3.2.1 ↓ | Vitamin/mineral supplement intake | All | `supplements` column; demoted from T1 for cardiac |
| FH-6.2.1 | Food availability | All | |
| FH-1.4.1.4 | Alcohol pattern on drinking days | Liver, HTN, Cardiac | |
| FH-6.2.3 | Access to food prep equipment | All | |
| FH-5.4.2 | Eating environment (alone/family/etc.) | All | |
| CH-3.1.9 | Daily stress level (1–10) | Cardiac, HTN | |
| CH-3.1.6 | Occupation | All | |
| CH-3.1.4 | Social and medical support | All | |
| FH-1.5.4.5 | Fibre estimated intake | Diabetes, Dyslipidaemia, Cardiac | |
| FH-8.1 | Nutrition quality of life (1–5) | All | |

↓ Demoted from Tier 1 in v2 (less critical for cardiac).

**v2 changes from v1 (per dietitian, May 2026):**
- **New fields:** `fat_intake_level` (→ T1), `medication_compliance` (→ T2), `fat_sources` (→ T2), `activity_types` (→ T2)
- **Promoted:** `sodium_awareness` T2 → T1 (direct driver of hypertension and fluid retention)
- **Demoted:** `supplements` T1 → T3 (lower priority for cardiac focus specifically)

**Personalization levels** (from dietitian, May 2026) — stored in `personalization_level` column:

| Level | Patient Profile | Content Scope |
|---|---|---|
| L0 | No risk, no history, no functional limits | Full spectrum incl. vigorous activity and performance goals |
| L1 | Emerging/moderate risk (early HTN, elevated BMI), no functional limits | Structured, safety-aware; moderation and do/don't boundaries |
| L2 | Established conditions, physical limitations, higher CV risk | Low-intensity, symptom monitoring, strict stop conditions |
| L3 | High clinical risk, recent cardiac events, disability | Medical oversight only; emergency education; minimal activity guidance |

Mock patient assignments: P1 (Ahmad) = L2, P2 (Lim) = L2, P3 (Kavitha) = L1, P4 (Hafizuddin) = L1, P5 (Tan) = L2, P6 (Siti Hajar) = L1, P7 (Nurul) = L0, P8 (Rajendran) = L3.

New in May 2026: **Siti Hajar binti Mohd Nasir** (id=12, `sitihajar.mnasir`) — female, age 50, stable IHD (single-vessel LAD disease), Hypertension, Hypercholesterolaemia, L1. Referred for cardiac nutrition counselling post-diagnosis. Home-cooked Malay food (frequent santan dishes). Added to validate the female cardiac L1 pathway.

---

## 8. RAG Pipeline — Core Chat Flow

**File:** `rag.py`

`get_rag_response(question, client_id, chat_session_id, profile=None)` orchestrates the chat response. Two pipelines are available, selected by environment flags:

### Option A — LangChain LCEL Chain (fallback, `USE_CLARA=false`)

Standard chain: `MergedRetriever` → `ChatPromptTemplate` → `ChatOllama`/`ChatOpenAI`. See §8.2–8.4 for details.

### Option B — CLaRa Hybrid (production, `USE_CLARA=true USE_OLLAMA=true`)

Three-step pipeline bypassing LangChain:

```
1. get_food_context(question)          — ChatOllama: extract food-relevant query terms
2. call_clara_compress(chunks, ...)    — CLaRa /compress: produce 300–500 token clinical digest
3. _build_qwen_prompt(...)             — Build prompt with patient context + digest
4. call_ollama_generate(prompt)        — Ollama qwen2.5:32b: generate final patient response
```

`get_food_context()` uses `get_llm()` (ChatOllama) with `timeout=90s`. On timeout/error it returns `""` gracefully — the pipeline continues with a bare query. `call_clara_compress()` has a `timeout=120s`; `call_ollama_generate()` has `timeout=180s`.

**Conversational style (patient-self mode, added May 2026):** When `is_patient_self=True`, `_build_qwen_prompt()` injects a "Conversation Style" block enforcing a strict 3-part structure:
1. One short direct answer (2–4 sentences)
2. One practical tip or example
3. One follow-up question to gather specifics

Hard cap: 100 words, no bullet points, no numbered lists. This prevents the bot from returning comprehensive health articles in response to simple questions.

`get_rag_response()` then orchestrates four additional steps:

### 8.1 Disease Identification

If no `profile` is passed, `identify_target_disease(question)` sends a zero-shot LLM prompt extracting the primary health condition from the user's message (e.g., `"hypertension"`). If a `profile` is passed, this step is skipped and the disease context is built directly from the profile's `condition` list.

### 8.2 Conversational Chain Construction

**File:** `chain_factory.py`

`create_conversational_chain(client_id, target_disease, patient_context="")` builds a stateful LangChain LCEL chain:

```
RunnablePassthrough.assign(context = retriever)
| ChatPromptTemplate([system_with_patient_block, chat_history, human])
| LLM
| StrOutputParser()
```

Wrapped in `RunnableWithMessageHistory` for per-session memory.

### 8.3 Retriever — Hybrid Multi-Tenant Vector Search

**File:** `vector_store.py`

`MergedRetriever` calls both `base_knowledge` and `client_{id}_knowledge` pgvector collections (top-5 each), merges, and deduplicates by `page_content`. Cosine similarity search using normalized embeddings.

### 8.4 LLM Configuration

**File:** `llm.py`

Two distinct LLM roles in the current production setup:

**Orchestration LLM (`get_llm()`)** — used for small auxiliary tasks: `identify_target_disease()`, `get_food_context()`, the extractor.
- `USE_OLLAMA=true`: `ChatOllama(model="qwen2.5:32b", temperature=0.3, num_predict=512, timeout=90)`
- `USE_OLLAMA=false`: `ChatOpenAI(model="gpt-4-turbo", temperature=0.3, max_tokens=512)`

`timeout=90` (added May 2026): Prevents indefinite hangs when Ollama is slow/unresponsive. `get_direct_llm_response()` wraps all calls in try/except — returns `""` on failure rather than raising.

**Generation LLM (`call_ollama_generate()`)** — used by Option B to produce the final patient-facing response.
- `POST OLLAMA_BASE_URL/api/generate`, model=qwen2.5:32b, temperature=0.5, num_predict=800, timeout=180s
- Larger token budget (800 vs 512) — sufficient for a short conversational response with follow-up question.

**Legacy Option A LLM** — used only when `USE_CLARA=false`:
- `ChatOpenAI(model="gpt-4-turbo", temperature=0.5, max_tokens=1500)` or ChatOllama equivalent
- Fed through `chain_factory.py` LCEL chain

### 8.5 Fallback Mechanism

If the RAG answer contains `"i don't know"`, `"i am not sure"`, or `"i cannot answer"`, or is empty, the question is re-issued directly to the LLM without retrieval context. This handles questions that fall outside the knowledge base without returning an unhelpful non-answer.

### 8.6 Image Injection

**File:** `image_handler.py`

Post-processes LLM output for `[IMAGE: <query>]` markers, matches against `data/image_annotations.csv` by keyword intersection, and returns the best-matching image filename.

---

## 9. Embedding Model

### 9.1 Base Model: BAAI/bge-m3

**File:** `embeddings.py`

```python
HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
```

**Model specifications:**

| Property | Value |
|---|---|
| Parameters | 570M |
| Output dimension | 1024 |
| Context window | 8,192 tokens |
| Languages | 100+ (including Bahasa Melayu) |
| Architecture | XLM-RoBERTa encoder |
| MTEB score | 54.9 (multilingual average) |

**Why bge-m3 over the previous bge-small-en-v1.5?**

The original `bge-small-en-v1.5` (33M params, 384-dim, English-only) was chosen for its small footprint. It became inadequate when:

1. A second document folder containing Bahasa Melayu PDFs was ingested. English-only models tokenise Malay text poorly and produce degraded embeddings.
2. Malaysian patient names, local food terms (Nasi Lemak, Rendang, Teh Tarik), and clinical notes contain extensive code-switching between English and Malay that the small model failed to encode meaningfully.

`bge-m3` was selected over other multilingual alternatives (e.g., `multilingual-e5-large`, `paraphrase-multilingual-mpnet`) because:
- It is the highest-scoring publicly available multilingual model on MTEB as of early 2026.
- It supports 8,192-token context (vs. 512 for most competitors), crucial for long clinical notes and multi-page medical guidelines.
- It is published by BAAI (Beijing Academy of AI) with a permissive license.
- Trade-off accepted: 2.3GB disk / ~1.5GB RAM vs. 130MB for bge-small. This is acceptable because the model runs on CPU as a singleton loaded once at startup.

**normalize_embeddings=True:** L2-normalises all vectors to unit length. This converts cosine similarity search into a simple dot product, which pgvector computes faster. All embeddings in the vector store were re-generated after this model change.

### 9.2 LoRA Adapter Inference

When `EMBEDDING_ADAPTER_PATH` is set and the directory exists, `get_embedding_function()` calls `_load_lora_embedding()` instead of the base HuggingFaceEmbeddings:

```python
base_hf_model = AutoModel.from_pretrained(base_model_name)
peft_model = PeftModel.from_pretrained(base_hf_model, adapter_dir)
```

Pooling mode is read from `nutribot_adapter_config.json` inside the adapter directory (`"mean"` for bge-m3, `"lasttoken"` for gte-Qwen2). If loading fails for any reason, the function falls back to the base model with a warning — no crash.

**Why fallback instead of hard fail?** The embedding adapter is an optional improvement, not a core dependency. A failed adapter load should not take down the production server.

---

## 10. Database Layer

### 10.1 Relational Database (SQLAlchemy)

**File:** `database.py`

Connection URL read from `DATABASE_URL`, defaulting to `postgresql://postgres:postgres@localhost:5432/nutribot`.

**Tables:**

**`api_clients`** — B2B tenants
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | Used as `client_id` throughout |
| `client_name` | String UNIQUE | |
| `hashed_api_key` | String UNIQUE | werkzeug PBKDF2 of `nbk_live_{hex}` |
| `patients` | relationship | → Patient rows (cascade delete) |

**`document_metadata`** — Tracks uploaded documents per client
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `client_id` | Integer FK → `api_clients.id` | CASCADE DELETE |
| `filename` | String | |
| `file_hash` | String | SHA-256 hex, for deduplication |
| `upload_date` | DateTime | UTC |
| `file_size` | Integer | Bytes |
| `chunk_count` | Integer | pgvector chunks created |
| `status` | String | `pending` / `completed` / `failed` |

**`patients`** — Patient medical records (added April 2026)

See Section 7.1 for full schema.

### 10.2 Vector Store (pgvector)

PostgreSQL with `pgvector` extension. LangChain manages two tables:

**`langchain_pg_collection`** — Named collections (one per client + shared base)

**`langchain_pg_embedding`** — Chunk rows
| Column | Type | Notes |
|---|---|---|
| `uuid` | UUID PK | |
| `collection_id` | UUID FK | |
| `embedding` | vector(1024) | 1024-dim for bge-m3 (was 384 for bge-small) |
| `document` | Text | Raw chunk text |
| `cmetadata` | JSONB | Includes `source`, `title`, `file_hash` |

**Dimension change:** After switching from `bge-small-en-v1.5` (384-dim) to `bge-m3` (1024-dim), the entire vector store was rebuilt. All existing embeddings were deleted and regenerated. The two source document directories were re-ingested:
```bash
BASE_DOCS_DIR=/home/han/documents_to_ingest python build_base_db.py
BASE_DOCS_DIR=/home/han/documents_to_ingest_new python build_base_db.py
```

---

## 11. Document Ingestion Pipelines

### 11.1 Base Knowledge Build (`build_base_db.py`)

Standalone script that populates the shared `base_knowledge` pgvector collection.

**Configuration:**
- `BASE_DOCS_DIR`: Source directory for documents (env var, defaults to `data/base_docs/`)
- `FILE_TRACKER_PATH`: `data/file_tracker.json` — stores `{filename: mtime}` for incremental runs
- `MAX_WORKERS`: `min(cpu_count, 4)` — parallel PDF parsing via `ProcessPoolExecutor`
- `DB_BATCH_SIZE`: 500 chunks per pgvector insertion batch

**Multilingual OCR support (added April 2026):**

```python
elements = partition(filename=filepath, strategy="fast", languages=["eng", "msa"])
if not elements:
    elements = partition(filename=filepath, strategy="hi_res", languages=["eng", "msa"])
```

`languages=["eng", "msa"]`: `msa` is the ISO 639-2 code for Bahasa Melayu, used by Tesseract. This was added when a folder of Malay-language nutrition guidelines was ingested. Without it, Tesseract defaulted to English-only OCR and produced garbled text for Malay characters.

**NUL byte sanitisation (added April 2026):**

```python
content = str(chunk).replace("\x00", "").strip()
if not content:
    continue
```

Some PDFs from the second document folder contained binary corruption that Unstructured extracted as null bytes (`\x00`). PostgreSQL rejects string literals containing null bytes, raising `ValueError: A string literal cannot contain NUL (0x00) characters`. The strip is applied before every insertion.

**Chunking parameters:**
- `max_characters=1500`: Maximum chunk size. Chosen to fit within the embedding model's effective context window while remaining large enough to contain complete nutritional recommendations.
- `combine_text_under_n_chars=500`: Prevents very short fragments (e.g., standalone table headers) from becoming useless isolated chunks.

### 11.2 Client Document Ingestion (`process_client_docs.py`)

Called within `POST /upload_documents/`. SHA-256 deduplication, same chunking parameters as base knowledge, inserts into `client_{id}_knowledge` in batches of 100.

### 11.3 Document Deletion (`document_manager.py`)

Raw psycopg2 DELETE filtered by `cmetadata->>'file_hash'` — targeted chunk deletion without loading data into memory.

---

## 12. Multi-Tenancy Model

Each B2B client (`ApiClient`) gets:
- **Isolated pgvector collection:** `client_{id}_knowledge`
- **Isolated patient records:** `patients` rows filtered by `client_id`
- **Shared base knowledge:** All clients share `base_knowledge`

The `client_id` propagates from the API key through every layer:
```
website_chat_router → rag.get_rag_response(client_id)
                    → chain_factory.create_conversational_chain(client_id)
                      → vector_store.get_retriever(client_id)
```

Patient records are also scoped: `GET /patients/` and `GET /patients/{id}` both enforce `patient.client_id == client.id`, preventing cross-tenant access.

---

## 13. Conversation Memory

**Status (12 June 2026): persisted to Postgres.** Conversation history survives restarts and is shared across all entry points (website chat, WhatsApp, MCP).

**Table:** `chat_messages` (`id, session_id, patient_id, role, content, created_at`) — created by `scripts/migrate_chat_history.py` (auto-creates the table, no `ALTER` needed). CRUD helpers in `database.py`: `add_chat_message()`, `get_chat_history()`, `clear_chat_history()`.

**Legacy LangChain path (`chain_factory.py`):** `DBChatMessageHistory` (a `BaseChatMessageHistory` subclass backed by `chat_messages`) replaces the old in-memory `InMemoryChatMessageHistory`. `RunnableWithMessageHistory` reads/writes via this class automatically — no change to the chain wiring itself.

**Active Option B path (`rag.get_rag_response`):**
- `_load_history_text()` loads the last 12 messages for the session and renders them as a `## Conversation So Far` block injected into the Qwen prompt.
- `_persist_turn()` saves the new user/assistant exchange after generation completes.
- Same wiring is applied to the CLaRa-primary and agent-tool paths.
- `get_rag_response()` takes an optional `patient_id` so rows can be filtered/attributed per patient (passed through from `website_chat_router.py`, `whatsapp_router.py`, and `mcp_server.py`).
- `session_id == "keepalive"` (used by the 4-minute Cloudflare keep-alive cron, §22) is excluded from history load/persist so it doesn't pollute the table.

**WhatsApp sessions** reuse this same table with `session_id = f"whatsapp-{patient_id}"` (§26), so a patient's WhatsApp and website conversations are continuous if both surface the same `session_id` convention is followed.

**Verified:** a second turn referencing "what we just discussed" correctly pulled context from turn 1, surviving a full `systemctl restart nutribot`.

---

## 14. Persona & Prompt Engineering

**File:** `chain_factory.py` — `get_system_template(target_disease, patient_context="")`

The system prompt structure (in order):

1. **Role definition** — AI Nutrition Assistant acting as a professional dietitian
2. **Patient profile block** (injected when `patient_context` is non-empty):
   ```
   **Current Patient Profile:**
   Name: ...  Age: ...  Ethnicity: ...  BMI: ...
   Conditions: ...  Medications: ...  Dietary restrictions: ...
   ```
3. **Core persona rules** — Professional, empathetic, collaborative ("we", "let's")
4. **Open-ended questioning rules** — Explicit bad/good question examples, anti-looping rules
5. **Malaysian multicultural food context** — Per-ethnicity food references (Malay/Chinese/Indian), mamak culture, communal dining
6. **ADIME framework** — Assessment → Diagnosis → Intervention → Monitoring & Evaluation
7. **Image display instructions** — Food-to-filename mapping for `[IMAGE:]` markers
8. **RAG context** — `{context}` placeholder filled at invocation with retrieved chunks

`{target_disease}` parameterises the focus throughout the prompt.

---

## 15. Streaming Response Delivery

**File:** `website_chat_router.py`

`StreamingResponse` with `media_type="text/event-stream"`. The async generator `stream_rag_response` calls `rag.get_rag_response()` synchronously, then yields the full answer string character-by-character with a 10ms delay.

**Note:** This is post-hoc streaming simulation — the LLM generates the full response before streaming begins. True token streaming would require `chain.astream()`.

---

## 16. UI Layers

### 16.1 Patient-Facing App (`patient_app.html`)

**Added April 2026. Served at `GET /`.**

Self-contained single-page application — no CDN dependencies, no build step. All CSS, JS, and HTML in one file.

**Design decisions:**

- **No CDN dependencies**: The app must function on clinic intranets with restricted external access. Inline everything.
- **URL param API key (`?key=`)**: Clinics can distribute pre-authenticated URLs to patients (e.g., via QR code) without requiring patients to type an API key manually. The login screen shows a "Connected to clinic" badge when a key is present.
- **IC auto-formatting**: The `fmtIC()` JS function formats input as `YYMMDD-SS-XXXX` as the user types, preventing manual format errors.

**Added June 2026 — "This Week" tab:** Screen 3 now has a `Chat` / `This Week` tab switcher in the chat header. The "This Week" tab fetches `/content/patient-feed/{patient_id}` and renders the patient's personalised weekly Exercise/Knowledge/Activity (EKA) content as styled cards. See §25.8 for details.

**Three screens:**

**Screen 1 — Login:**
- Name input field
- "Connected to clinic" badge if `?key=` is in URL
- No password required at this step (patients often forget passwords)

**Screen 2 — IC Verification:**
- IC number input with auto-format
- Verify / Back buttons
- On success, transitions to Screen 3

**Screen 3 — Dashboard + Chat:**
- Dark green sidebar (`--g900:#0d3d24`) with patient profile pills (conditions, medications, dietary restrictions, allergies)
- Chat area with streaming SSE response rendering
- Mobile: sidebar slides in from left via `.sbtog` button + dark overlay mask
- Session ID generated client-side as a random UUID per page load

**Colour palette rationale:**
- `--g900:#0d3d24` / `--g700:#1a6b45`: Deep green evokes health, clinical professionalism, and Malaysian nature imagery (consistent with national branding conventions)
- `--warm:#fafaf8`: Off-white reduces eye strain in clinical reading contexts
- `--amber:#f59e0b`: High-contrast accent for interactive elements (accessibility)

### 16.2 Admin Dashboard

`GET /admin/create-api-key` — HTML page for creating B2B API keys and listing clients. Admin password checked via `ADMIN_PASSWORD` env var.

### 16.3 Client Portal

`GET /portal/` — Multi-page portal for B2B clients to manage documents, with embedded test chat. Session stored in `localStorage` via 64-char hex token.

---

## 17. Embedding Fine-Tuning Pipeline

This pipeline adapts the embedding model to the medical nutrition domain by training on (query, relevant_passage) pairs derived from the actual ingested documents.

### 17.1 Training Data Generation

**File:** `generate_embedding_training_data.py`

Pulls all chunks from the pgvector `base_knowledge` collection and uses an LLM to generate 2 realistic questions per chunk — questions a patient or dietitian might ask whose answer is contained in that chunk.

**Output:**
- `~/data/embedding_train.jsonl` — 90% of pairs (anchor query, positive passage)
- `~/data/embedding_val.jsonl` — 10% of pairs
- ~69,000 total pairs from ~35,000 chunks × 2 questions each

**Provider options:**

| Provider | `--provider` | Cost | Speed | Quality |
|---|---|---|---|---|
| OpenAI GPT-4-turbo | `openai` | ~$34 for full dataset | Fast (batched) | Highest |
| Local Ollama | `ollama` | Free | ~3-5s/chunk | Sufficient |

**Why Ollama over OpenAI for this task?** OpenAI quota was exhausted ($0 credit). Beyond cost, the quality difference between GPT-4-generated and Ollama-generated training *questions* is marginal — the training signal comes from the passage content, not the question sophistication. The questions only need to be plausible, not medically perfect.

**`--resume` flag:** Appends to existing output files and skips already-processed chunks (estimated by counting existing pairs / QUERIES_PER_CHUNK). Allows interrupted runs to continue without restarting.

### 17.2 LoRA Fine-Tuning (`finetune_embeddings.py`)

**Model profiles:**

| Profile | Base model | Params | Architecture | VRAM usage | Est. time (RTX 3050) |
|---|---|---|---|---|---|
| `bge-m3` (default) | BAAI/bge-m3 | 570M | Encoder (XLM-RoBERTa) | ~2.0 GB | ~45–60 min |
| `gte` | Alibaba-NLP/gte-Qwen2-1.5B-instruct | 1.5B | Decoder (Qwen2) | ~2.5 GB | ~40 hrs |

**Why bge-m3 is the practical choice:**
- The gte-Qwen2-1.5B model trained at 12.5s/step (decoder architecture processes all prior positions at each token, inherently slower). At that rate, 3 epochs = ~40 hours on an RTX 3050. 
- bge-m3 (encoder, bidirectional attention) trains at ~0.25s/step — roughly 50× faster — bringing training to under an hour.
- bge-m3 is already in production: the fine-tuned adapter loads directly without requiring a vector store rebuild (same model, different weights). Actually a vector store rebuild is still required since embeddings change, but no model architecture change is needed.
- The MTEB gap (bge-m3 54.9 vs gte-Qwen2 65.4) is on generic English benchmarks. For medical Malay/English, bge-m3's multilingual pre-training and fine-tuning on scientific text gives it a stronger domain starting point.

### 17.3 Hyperparameter Decisions

**LoRA configuration:**

| Parameter | Value | Rationale |
|---|---|---|
| `r` (rank) | 16 | Higher rank = more capacity to adapt to medical domain. Rank 8 is the community default for NLP tasks; rank 16 is chosen here because the domain shift (general → medical nutrition) is substantial and the 570M base model has sufficient capacity. Memory cost is minimal (~60MB vs ~30MB for rank 8). |
| `lora_alpha` | 32 | Conventionally set to `2 × r`. Acts as a scaling factor for LoRA updates; `alpha/r = 2` means LoRA updates are scaled to have meaningful magnitude without dominating base weights. |
| `lora_dropout` | 0.05 | Light regularisation to prevent overfitting on the ~69K training pairs. Higher dropout (0.1+) is unnecessary — the training data is diverse enough. |
| `target_modules` | `["query", "value"]` | For bge-m3 (XLM-RoBERTa): Q and V projections in self-attention. These control how the model attends to and combines information. Fine-tuning Q+V (not K) is the standard recommendation for encoder fine-tuning — K shapes the key space which is less domain-specific. |

**Training configuration:**

| Parameter | Value | Rationale |
|---|---|---|
| `batch_size` | 8 | Reduced from initial 16 to avoid OOM on 4GB VRAM. The double-load problem (Transformer wrapper loads model again before swap) consumes extra VRAM during setup. |
| `grad_accumulation` | 4 | Effective batch = 32. `MultipleNegativesRankingLoss` (in-batch negatives) benefits strongly from large effective batches — more negatives per anchor = stronger contrastive signal. |
| `learning_rate` | 2e-4 | Standard for LoRA fine-tuning. Lower than typical full fine-tuning (1e-5 to 5e-5) because LoRA updates are small; too low and the adapter barely learns, too high and it overshoots the base model's geometry. |
| `warmup_ratio` | 0.1 | 10% of steps used for LR warmup. Prevents large gradient steps at the start when the adapter weights are randomly initialised. |
| `MAX_SEQ_LEN` | 256 | Reduced from 512. For retrieval fine-tuning, most meaningful query-passage pairs are under 256 tokens. The reduction halves activation memory with negligible quality impact for this use case. |
| `bf16=True` | — | BF16 (Brain Float 16) used instead of FP16. FP16 training uses a `GradScaler` that fails with already-FP16 LoRA parameters (raises `ValueError: Attempting to unscale FP16 gradients`). BF16 has the same memory footprint but does not require gradient scaling, bypassing this conflict entirely. RTX 3050 (Ampere architecture) supports BF16 natively. |

**Loss function:** `MultipleNegativesRankingLoss` (MNRL) — treats all other passages in the same batch as negatives for each anchor. No explicit negative mining required. Effective batch size of 32 provides 31 negatives per anchor, which is sufficient for domain adaptation. The loss approximates the InfoNCE objective used in CLIP and SimCSE.

**Memory fixes applied:**
1. `base_hf_model.enable_input_require_grads()` instead of `prepare_model_for_kbit_training()` — the latter casts all parameters to FP32 (requires ~6GB for 1.5B params), causing immediate OOM.
2. `del word_embedding_model.auto_model` + `gc.collect()` + `torch.cuda.empty_cache()` immediately after replacing the Transformer wrapper's internal model — prevents the duplicate model load from occupying VRAM throughout training.
3. `PYTORCH_ALLOC_CONF=expandable_segments:True` — allows the CUDA allocator to reuse fragmented memory blocks, reducing allocation failures from fragmentation.

---

## 18. LLM Fine-Tuning Pipeline

The system includes a complete pipeline for fine-tuning a local LLM to serve as a drop-in replacement for GPT-4-turbo.

### 18.1 Training Data Generation

**File:** `generate_training_data.py`

Generates synthetic multi-turn ADIME conversations using GPT-4o. Covers 9 health conditions × 12 Malaysian patient personas. Output: `data/train.jsonl` / `data/val.jsonl` in ShareGPT format.

### 18.2 LoRA Fine-Tuning (Ollama/Unsloth)

**File:** `colab_finetune.ipynb` / `Modelfile`

Fine-tunes a Gemma-3-4B base model on the synthetic conversations using Unsloth + TRL on Google Colab. Exports as GGUF (`Q4_K_M` quantisation) for Ollama inference.

Enable with: `USE_OLLAMA=true`, `OLLAMA_MODEL=nutribot-lora`

---

## 19. Evaluation Framework

**File:** `eval_ragas.py`

RAGAS evaluation over a ground-truth question set:

| Metric | Measures |
|---|---|
| `faithfulness` | Is the answer grounded in retrieved context? (Hallucination detection) |
| `answer_relevancy` | Does the answer address the question? |
| `context_precision` | Are retrieved chunks relevant? (Retrieval precision) |
| `context_recall` | Do chunks cover the ground truth? (Retrieval recall) |

```bash
python eval_ragas.py --limit 5          # smoke test
python eval_ragas.py --category "Hypertension"
python eval_ragas.py --out results.json
```

---

## 20. Testing Strategy

### Unit Tests

- **`test_db.py`** — SQLite in-memory: API client lifecycle, document metadata CRUD
- **`test_api.py`** — TestClient with `app.dependency_overrides[get_db]`: health check, auth rejection

### Integration Tests

- **`test_bot_accuracy.py`** — Live API, answer quality evaluation
- **`test_bot_culture.py`** — Malaysian food scenario handling

**`conftest.py`** sets `DATABASE_URL=sqlite:///./data/test.db` before any imports.

---

## 21. Deployment

### Development

```bash
uvicorn app:app --reload --port 8000
```

### Production

```bash
gunicorn -w 1 -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:8000
```

Single worker required (in-memory session store, chat history).

### Post-Fine-Tuning Deployment Checklist

After completing embedding fine-tuning:

1. Add to `.env`: `EMBEDDING_ADAPTER_PATH=~/models/embedding_lora`
2. Rebuild vector store (required — embeddings change):
   ```bash
   docker exec pgvector-nutribot psql -U postgres -d nutribot \
     -c "DELETE FROM langchain_pg_collection WHERE name='base_knowledge';"
   BASE_DOCS_DIR=/home/han/documents_to_ingest python build_base_db.py
   BASE_DOCS_DIR=/home/han/documents_to_ingest_new python build_base_db.py
   ```
3. Restart server
4. Verify: `python -c "from embeddings import get_embedding_function; ef=get_embedding_function(); print(len(ef.embed_query('test')))"`
5. Run: `python test_bot_accuracy.py && python test_bot_culture.py`

---

## 22. Environment Variables Reference

| Variable | Default | Required | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | — | Yes (if not Ollama) | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4-turbo` | No | OpenAI model name |
| `USE_OLLAMA` | `false` | No | Use local Ollama LLM instead |
| `OLLAMA_MODEL` | `nutribot-lora` | No | Ollama model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | No | Ollama server URL |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | No | HuggingFace embedding model |
| `EMBEDDING_ADAPTER_PATH` | — | No | Path to LoRA adapter dir; activates fine-tuned embeddings |
| `FINETUNE_BASE_MODEL` | `Alibaba-NLP/gte-Qwen2-1.5B-instruct` | No | Override base model for `finetune_embeddings.py` |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/nutribot` | Yes (prod) | SQLAlchemy relational DB URL |
| `PGVECTOR_URL` | Falls back to `DATABASE_URL` | Yes (prod) | PostgreSQL URL with pgvector |
| `BASE_DOCS_DIR` | `data/base_docs/` | No | Source PDFs for base knowledge build |
| `PERSISTENT_DISK_PATH` | `./data` | No | Root data directory |
| `ADMIN_PASSWORD` | — | Yes (prod) | Admin panel password |
| `REDIS_URL` | — | No | Redis URL for optional session caching |
| `PORT` | `8000` | No | Server port |

---

## 23. Data Flow: End-to-End Request Trace

A single chat request from a logged-in patient (patient_id provided):

```
1. Patient sends:
   POST /chat/get_response
   Headers: X-API-Key: nbk_live_abc123...
   Body: {
     "question": "What can I eat for breakfast?",
     "session_id": "uuid-xyz",
     "patient_id": 1
   }

2. FastAPI → get_api_client():
   - Hash-checks API key → ApiClient(id=2, client_name="test1")

3. website_chat_router.py:
   - patient_id=1 provided, profile=None
   - db.get_patient(session, 1) → Patient(Ahmad Fadzillah, T2DM, Halal, ...)
   - db.patient_to_profile_dict(patient) → profile dict
   - Returns StreamingResponse(stream_rag_response(..., profile=profile))

4. rag.get_rag_response(question, client_id=2, session_id, profile):
   - profile provided → skip identify_target_disease()
   - target_disease = "Conditions: Type 2 Diabetes, Hypertension. Medications: Metformin..."
   - patient_context = "Name: Ahmad Fadzillah\nAge: 52\nEthnicity: Malay\nBMI: 31.2\n..."

5. chain_factory.create_conversational_chain(client_id=2, target_disease, patient_context):
   - get_system_template() builds prompt with patient block injected
   - get_retriever("2") → MergedRetriever

6. vector_store.MergedRetriever._get_relevant_documents("What can I eat for breakfast?"):
   - embeddings.py: encodes query → 1024-dim bge-m3 vector
     (or fine-tuned adapter vector if EMBEDDING_ADAPTER_PATH set)
   - PGVector cosine search: base_knowledge → top 5 chunks
   - PGVector cosine search: client_2_knowledge → top 5 chunks
   - Merge + deduplicate → ~8 Document objects

7. LCEL chain execution:
   - context = concatenated chunk texts
   - chat_history = prior turns for "uuid-xyz"
   - Prompt = system(with Ahmad's profile) + history + "What can I eat..."
   - ChatOpenAI(gpt-4-turbo) → response mentioning Ahmad by name,
     Halal options, low-GI foods, no high-sugar Teh Tarik, etc.

8. parse_response_for_image() → {"answer": "...", "image_url": "rice_portions.png"}

9. stream_rag_response: yields answer char-by-char, 10ms delay

10. _session_store["uuid-xyz"]: new turn appended for next request
```

---

## 24. Module Reference Table

| Module | Role | Key Functions/Classes |
|---|---|---|
| `app.py` | FastAPI app, router registration, patient endpoints | `startup_event`, `patient_login`, `patient_verify`, `list_patients` |
| `website_chat_router.py` | Streaming chat endpoint, patient_id resolution | `get_chat_response`, `stream_rag_response` |
| `patient_app.html` | Production patient-facing SPA (Login → IC Verify → Chat) | — |
| `admin_router.py` | Admin HTML panel for API key management | `create_api_key`, `list_clients` |
| `client_portal_router.py` | B2B client portal for document management + test chat | `authenticate`, `upload_documents` |
| `rag.py` | RAG orchestration, patient context building | `get_rag_response`, `identify_target_disease` |
| `chain_factory.py` | LCEL chain, ADIME prompt with patient block, session memory | `create_conversational_chain`, `get_system_template` |
| `vector_store.py` | Hybrid multi-tenant retriever | `MergedRetriever`, `get_retriever` |
| `embeddings.py` | Singleton embedding model, LoRA adapter loading | `get_embedding_function`, `_load_lora_embedding` |
| `llm.py` | LLM factory (OpenAI / Ollama) | `get_llm`, `get_direct_llm_response` |
| `database.py` | SQLAlchemy ORM models + CRUD | `ApiClient`, `DocumentMetadata`, `Patient`, `patient_to_profile_dict` |
| `patient_store.py` | PatientStore ABC + `SUPPLEMENTARY_FIELDS` whitelist + factory | `PatientStore`, `SUPPLEMENTARY_FIELDS`, `get_patient_store` |
| `local_patient_store.py` | LocalPatientStore (dev/staging) — wraps SQLAlchemy | `LocalPatientStore` |
| `remote_patient_store.py` | RemotePatientStore (prod scaffold) — calls hospital REST API | `RemotePatientStore` |
| `mock_hospital_api.py` | Standalone mock of the hospital API for testing `RemotePatientStore` | `app` |
| `whatsapp_router.py` | WhatsApp inbound webhooks (Twilio + Meta), mounted under `/chat` (§26) | `whatsapp_webhook`, `whatsapp_meta_verify`, `whatsapp_meta_webhook`, `_process_and_reply` |
| `extractor.py` | Passively extracts supplementary fields from patient messages via qwen2.5:32b | `extract_from_message`, `call_ollama_extractor`, `_validate_extraction`, `_filter_already_filled` |
| `dependencies.py` | FastAPI dependency injection | `get_db`, `get_api_client` |
| `document_manager.py` | Vector store document deletion | `delete_document_from_vectorstore` |
| `process_client_docs.py` | Per-client document ingestion pipeline | `process_client_document`, `calculate_file_hash` |
| `build_base_db.py` | Shared base knowledge ingestion (Malay OCR, NUL sanitisation) | `build_base_database`, `process_single_file` |
| `image_handler.py` | `[IMAGE:]` marker parsing, CSV annotation lookup | `parse_response_for_image`, `find_image_url` |
| `seed_patients.py` | Seeds 8 demo Malaysian patients (idempotent) | `main` |
| `generate_embedding_training_data.py` | Generates (query, passage) pairs from pgvector chunks via LLM | `main`, `fetch_all_chunks`, `_ollama_generate` |
| `finetune_embeddings.py` | LoRA fine-tuning of bge-m3 / gte-Qwen2 on RTX 3050 | `run_training`, `build_dataset` |
| `generate_training_data.py` | Synthetic ADIME conversation generation for LLM fine-tuning | `generate_conversation` |
| `eval_ragas.py` | RAGAS RAG quality evaluation | `run_evaluation` |
| `colab_finetune.ipynb` | Gemma-3-4B LoRA fine-tuning notebook (Unsloth/TRL) | — |
| `Modelfile` | Ollama model definition for local LLM | — |
| `cache.py` | Optional Redis cache wrapper | `get_from_cache`, `set_in_cache` |
| `conftest.py` | pytest configuration (SQLite in-memory override) | — |
| `test_db.py` | Unit tests for database.py | — |
| `test_api.py` | Unit tests for FastAPI routes | — |
| `test_bot_accuracy.py` | Integration test: answer quality | — |
| `test_bot_culture.py` | Integration test: Malaysian culture handling | — |
| `create_api_key.py` | CLI script to generate B2B API keys | — |
| `content_api_router.py` | REST API for E/K/A weekly content (`/content/*`, X-API-Key auth) | `_serialize_material`, `patient_feed`, `weekly_feed`, `approve_material` |
| `scripts/generate_content.py` | Legacy day-offset content generation (43 niche cases, day 3/5/7/14/21/30) | `generate_content`, `conditions_to_groups`, `CONDITION_MAP` |
| `scripts/content_scheduler.py` | Daily cron: matches due patients (by `first_chat_at` + day_offset) to active legacy materials | `main` |
| `scripts/generate_weekly_eka.py` | Weekly Exercise/Knowledge/Activity content generation (4-week rotating templates) | `generate_weekly_eka`, `build_eka_cases`, `_generate_exercise/_knowledge/_activity` |
| `scripts/weekly_eka_scheduler.py` | Monday cron: expires old EKA materials, generates current week's E/K/A | `run`, `_cleanup`, `_week_already_generated` |
| `scripts/migrate_eka_columns.py` | Adds `content_type`/`week_number`/`expires_at` to `content_materials`; makes `day_offset` nullable | `migrate` |
| `scripts/migrate_content_delivery_log.py` | Makes `content_delivery_log.day_offset` nullable (for EKA deliveries) | `migrate` |
| `whatsapp.py` | WhatsApp content delivery (Twilio/Meta), formats legacy tips and EKA E/K/A messages | `send_message`, `format_tips_message`, `format_eka_message` |
| `scripts/migrate_chat_history.py` | Creates `chat_messages` table (conversation history persistence, §13) | `migrate` |
| `scripts/migrate_whatsapp_columns.py` | Adds `phone_number` / `whatsapp_opted_out` columns to `patients` | `migrate` |
| `scripts/test_remote_patient_store.py` | E2E test: `RemotePatientStore` against `mock_hospital_api.py` (§7.4) | `main` |

---

## 25. Content Drip Pipeline — Weekly EKA Content

**Added June 2026.** Extends the original day-offset content drip (May 2026) with a second, parallel pipeline that delivers a rotating weekly programme of **Exercise (E)**, **Knowledge (K)**, and **Activity (A)** content, matched to each patient's condition group and personalization level (L0–L3).

### 25.1 Two-Pipeline Model

Both pipelines share the same `content_materials` / `content_delivery_log` tables, distinguished by the `content_type` column:

| | Legacy day-offset pipeline (May 2026) | Weekly EKA pipeline (June 2026) |
|---|---|---|
| **Generator** | `scripts/generate_content.py` | `scripts/generate_weekly_eka.py` |
| **Scheduler** | `scripts/content_scheduler.py` (daily cron) | `scripts/weekly_eka_scheduler.py` (Monday cron) |
| **`content_type`** | `NULL` | `"E"` \| `"K"` \| `"A"` |
| **`day_offset`** | `3, 5, 7, 14, 21, 30` (from `first_chat_at`) | `NULL` |
| **`week_number`** | `NULL` | ISO week number |
| **`raw_tips` shape** | `list[{tip_number, tip, source_hint}]` | structured `dict` (schema differs per E/K/A) |
| **`expires_at`** | `NULL` (never expires) | `created_at + 14 days` |
| **Niche cases** | 43 (7 condition groups × day offsets) | 21/week (7 condition groups × E/K/A), rotating over a 4-week template cycle |
| **Delivery trigger** | One-off, tied to `first_chat_at` per patient | Recurring, same content for all patients in a condition group each week |

Both pipelines are dispatched through the same `ContentDeliveryLog` table and the same `send_patient_content` MCP tool / WhatsApp formatter, which branch on `material.content_type` to pick the correct rendering path (see §25.7).

### 25.2 Data Model Changes

**File:** `database.py` — `ContentMaterial` / `ContentDeliveryLog` (§10, `content_materials` / `content_delivery_log` tables)

New/changed columns (applied via `scripts/migrate_eka_columns.py` and `scripts/migrate_content_delivery_log.py`, both idempotent):

```
content_materials
├── content_type   VARCHAR(1)  NULL   — "E" | "K" | "A" | NULL (legacy)
├── week_number    INTEGER     NULL   — ISO week number (EKA only)
├── expires_at     TIMESTAMP   NULL   — created_at + 14 days (EKA only); NULL = never expires
└── day_offset     INTEGER     NULL   — now nullable (was NOT NULL; EKA rows have no day offset)

content_delivery_log
└── day_offset     INTEGER     NULL   — now nullable (EKA deliveries log day_offset=NULL)
```

**Key functions added to `database.py`:**

| Function | Description |
|---|---|
| `upsert_eka_material(db, condition_group, condition_tags, content_type, week_number, topic, title, raw_content, force=False)` | Idempotent insert keyed on `(condition_group, content_type, week_number, topic)`; `force=True` overwrites |
| `cleanup_expired_eka_materials(db)` | Deletes EKA rows where `expires_at < now`; returns count deleted |
| `get_materials_by_filters(db, content_type=, week_number=, condition_group=, is_active=, include_expired=False, ...)` | General-purpose filtered query, excludes expired EKA rows by default |
| `get_weekly_feed_for_conditions(db, condition_groups, week_number, content_type=None, is_active=True)` | Returns this week's E/K/A materials for the given condition groups |

`EKA_EXPIRY_DAYS = 14` — chosen so that each Monday's scheduler run cleans up content from two weeks prior, keeping at most ~2 weeks of EKA materials live at once.

### 25.3 Weekly Generation (`generate_weekly_eka.py`)

**`_TEMPLATES`** is a nested dict: `condition_group → content_type ("E"/"K"/"A") → 4 topic-template tuples` (one per 4-week rotation slot). Covers the same 7 condition groups as the legacy pipeline: **T2DM, HTN, CKD, Cardiac, PCOS, Dyslipidaemia, General**.

```
build_eka_cases(iso_week):
    rotation = ((iso_week - 1) % 4) + 1        # 1-4, cycles every 4 weeks
    → 7 groups × 3 types = 21 cases for this week,
      each picking the rotation-th template tuple
```

**Per-case generation pipeline:**

```
niche case (group, content_type, week_number, topic, title, rag_query, prompt_topic)
    │
    ▼
_retrieve_chunks(rag_query, client_id)
    ← PGVector similarity_search on base_knowledge (top 8) + client_{id}_knowledge (top 3, deduped)
    ← shared with generate_content.py's retrieval helper
    │
    ▼
_GENERATORS[content_type](niche, chunks)   — one of:
    _generate_exercise()   → Ollama prompt includes _PERSONALIZATION_GUIDANCE (L0-L3 rules)
    _generate_knowledge()
    _generate_activity()
    │
    ▼
_call_and_parse(prompt, max_tokens)
    ← call_ollama_generate() via llm.py
    ← strips ```json fences, json.loads()
    ← on failure: {"raw_output": "...", "parse_error": true}
    │
    ▼
upsert_eka_material(db, ..., raw_content=content, force=force)
    ← is_active=False, expires_at=created_at+14 days
```

**Content JSON schemas (stored in `raw_tips`):**

- **Exercise (E):** `{exercise_type, duration_min, frequency_per_week, intensity, warmup:[...], main_activity:[...], cooldown:[...], level_modifications:{L0,L1,L2,L3}, safety_stop_signs:[...], equipment_needed:[...], malaysian_context}`
  - `level_modifications` is the bridge to the personalization system (§7.6) — each patient sees the modification matching their `personalization_level`.
- **Knowledge (K):** `{topic_summary, learning_points:[{point, explanation, why_it_matters}] × 6, key_takeaway, local_context}`
- **Activity (A):** `{task_name, description, instructions:[...], tracking_method, weekly_goal, micro_actions:[...] (Mon-Weekend), self_monitoring_prompts:[...], success_looks_like}`

**Excel export:** `materials/eka_week{N}_{date}.xlsx` — one sheet per type (Exercise/Knowledge/Activity, colour-coded), one row per generated field per item, with a "Status" column for the dev team's review notes. Generated automatically at the end of every non-dry-run generation.

**CLI:**
```bash
python scripts/generate_weekly_eka.py                          # current ISO week, all 21 items
python scripts/generate_weekly_eka.py --week 24                 # specific week
python scripts/generate_weekly_eka.py --group CKD --type K      # single item (fast test)
python scripts/generate_weekly_eka.py --dry-run                  # no LLM call, no DB write
python scripts/generate_weekly_eka.py --force                    # overwrite existing rows for that week
```

### 25.4 Scheduler (`weekly_eka_scheduler.py`)

Cron entry point, runs every Monday at 06:00:

```
0 6 * * 1 /home/han/miniconda3/bin/python /mnt/ext/bare_NutriChatbot/scripts/weekly_eka_scheduler.py
```

**Each run:**

1. **Cleanup** — `cleanup_expired_eka_materials()` deletes EKA rows with `expires_at < now` (i.e. materials generated 2 weeks ago).
2. **Idempotency check** — `_week_already_generated(iso_week)`: if any EKA material already exists for the current ISO week, skip (unless `--force`).
3. **Generate** — calls `generate_weekly_eka()` for all 21 items, saved with `is_active=False`.
4. Prints a reminder: approve via `POST /content/materials/{id}/approve` (requires `X-Admin-Password`).

**Expiry lifecycle example:**
```
Mon week 22: cleanup (nothing old)        → generate week 22 (expires end of week 23)
Mon week 23: cleanup (nothing old yet)    → generate week 23 (expires end of week 24)
Mon week 24: cleanup DELETES week 22      → generate week 24
```

```bash
python scripts/weekly_eka_scheduler.py              # normal run
python scripts/weekly_eka_scheduler.py --dry-run     # show what would happen, no writes
python scripts/weekly_eka_scheduler.py --force       # regenerate current week even if it exists
python scripts/weekly_eka_scheduler.py --week 22     # backfill a specific week
```

### 25.5 Content API (`content_api_router.py`)

Mounted in `app.py` at prefix `/content` (tags: "Content Library"), authenticated via `X-API-Key` (same as `/chat`).

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/content/materials` | API key | List materials, filterable by `content_type`, `week_number`, `condition_group`, `is_active`, `include_expired` |
| GET | `/content/materials/{id}` | API key | Single material with full structured `content` |
| GET | `/content/weekly-feed?conditions=T2DM,HTN` | API key | This week's E+K+A for given condition groups |
| GET | `/content/patient-feed/{patient_id}` | API key | This week's feed matched to a specific patient (see below) |
| POST | `/content/materials/{id}/approve` | API key + `X-Admin-Password` | Sets `is_active=True` |
| POST | `/content/materials/{id}/unapprove` | API key + `X-Admin-Password` | Sets `is_active=False` |
| POST | `/content/generate-weekly` | API key + `X-Admin-Password` | Background-triggers `generate_weekly_eka()` for current/specified week |
| GET | `/content/summary` | API key | Per-type counts (total/active/pending) for a given week — dashboard stats |

**`GET /content/patient-feed/{patient_id}`** is the endpoint consumed by `patient_app.html` (§25.8):

```
patient_feed(patient_id):
    patient = db.get_patient(patient_id)            # 404 if missing, 403 if wrong client
    groups  = conditions_to_groups(patient.conditions)   # from scripts/generate_content.py
    materials = get_weekly_feed_for_conditions(groups, week_number=current_iso_week, is_active=True)
    → {
        week_number, patient_id, patient_name, condition_groups,
        personalization_level: patient.personalization_level,
        feed: {E: [...], K: [...], A: [...]},
        total
      }
```

`_serialize_material()` is the shared serializer used by every endpoint above:
```
{id, content_type, content_type_label, condition_group, condition_tags,
 week_number, day_offset, topic, title, is_active,
 content (= raw_tips), created_at, expires_at, is_expired}
```

### 25.6 Dev Review & Approval Workflow

```
weekly_eka_scheduler.py (Mon 06:00)
    → 21 ContentMaterial rows, is_active=False, expires_at=+14 days
    → materials/eka_week{N}_{date}.xlsx  (3 sheets: Exercise / Knowledge / Activity)
        ↓
Dev team reviews Excel, flags issues in materials/eka_dietitian_review_flags.md
        ↓
POST /content/materials/{id}/approve  (X-Admin-Password)
        ↓
Material now appears in /content/weekly-feed, /content/patient-feed/{id},
and becomes eligible for WhatsApp delivery via send_patient_content
```

`materials/eka_dietitian_review_flags.md` tracks individual items pending supervising-dietitian sign-off before approval (e.g. an item recommending lentils to a CKD patient — flagged for potassium/phosphorus review).

### 25.7 WhatsApp Delivery

**File:** `whatsapp.py`

`format_eka_message(content_type, patient_first_name, title, content, week_number=None, personalization_level=None)` dispatches on `content_type`:

- **E** → `_format_exercise_message()`: title, `{exercise_type} • {duration_min} min • {frequency_per_week}x/week • {intensity} intensity`, Warm-up/Main activity/Cool-down lists, `_For you:_ {level_modifications[personalization_level]}` (personalised per patient), `⚠️ Stop and rest if you feel:` (safety_stop_signs), 🇲🇾 malaysian_context
- **K** → `_format_knowledge_message()`: topic_summary, numbered learning_points with explanation + "Why it matters", 💡 key_takeaway, 🇲🇾 local_context
- **A** → `_format_activity_message()`: task_name + description, numbered instructions, weekly_goal, Mon–Weekend micro_actions, 📝 tracking_method, ✅ success_looks_like

If `content` is not a dict or has `parse_error: true`, a fallback "we hit a hiccup" message is sent instead (the patient is never shown raw JSON or an error).

**File:** `mcp_server.py` — `_send_patient_content()` (MCP tool `send_patient_content`)

When `channel="whatsapp"`, branches on `material.content_type`:
```python
if material.content_type:        # EKA — E/K/A
    body = wa.format_eka_message(content_type=..., content=material.raw_tips,
                                  week_number=..., personalization_level=patient.personalization_level)
else:                              # legacy day-offset nutrition tips
    body = wa.format_tips_message(patient_first_name=..., title=..., tips=material.raw_tips, day_offset=...)
```

This required `content_delivery_log.day_offset` to become nullable (§25.2), since `_send_patient_content` logs a `ContentDeliveryLog` row with `day_offset=material.day_offset`, which is `None` for EKA materials. Patient phone numbers are stored in `patients.phone_number` (set via the `set_patient_phone` MCP tool).

### 25.8 Patient App — "This Week" Tab

**File:** `patient_app.html` (Screen 3 — Dashboard + Chat)

A `Chat` / `This Week` tab switcher (`#tab-chat` / `#tab-week`) was added to the chat header. Selecting "This Week":

1. Hides the chat message list and input bar; shows a new `#wf` panel.
2. On first activation (`wf.dataset.loaded` not set), calls `loadWeeklyFeed()`:
   ```javascript
   GET /content/patient-feed/{patient_id}   (X-API-Key header)
   → { feed: {E:[...], K:[...], A:[...]}, personalization_level, ... }
   ```
3. Renders each material as a card via `renderE()` / `renderK()` / `renderA()`:
   - **Exercise cards** (`.wf-card`): badge "Exercise · Week N", title, type/duration/frequency/intensity meta line, Warm-up/Main Activity/Cool-down sections, a `For you:` line picked from `level_modifications[personalization_level]`, "Stop & rest if you feel" safety signs, 🇲🇾 Malaysian context
   - **Knowledge cards** (`.wf-card.tk`, blue accent): badge "Knowledge · Week N", topic summary, numbered learning points with "Why it matters" sub-text, 💡 key takeaway, 🇲🇾 local context
   - **Activity cards** (`.wf-card.ta`, amber accent): badge "Activity · Week N", task name + description, "How to do it" instructions, 🎯 weekly goal, "Daily Plan" micro-actions, 📝 tracking method, ✅ success criteria
   - Materials with `content.parse_error` are silently skipped (not rendered)
4. If the feed is empty: "No content available for this week yet. Check back soon!"

`switchTab()` / `loadWeeklyFeed()` / `wfList()` / `renderE/K/A()` are reset (cache cleared) on `goDash()` and `signOut()` so a new login always re-fetches the feed.

No backend changes were required for this UI — it consumes the existing `/content/patient-feed/{patient_id}` endpoint from §25.5.

---

## 26. WhatsApp Inbound Integration

**File:** `whatsapp_router.py`, mounted under `/chat`. **Added 12 June 2026.** Lets a patient have the *full* RAG chat conversation over WhatsApp, not just receive scheduled content (§25.7 covers outbound delivery only).

**Auth model:** no `X-API-Key` — these are public provider webhooks, authenticated by provider-specific signatures instead:
- `POST /chat/whatsapp` (Twilio) — validates `X-Twilio-Signature` via `twilio.request_validator.RequestValidator`. Skipped with a warning if `TWILIO_AUTH_TOKEN` is unset.
- `GET /chat/whatsapp/meta` (Meta Cloud API) — verification handshake, checks `hub.verify_token` against `META_VERIFY_TOKEN`.
- `POST /chat/whatsapp/meta` (Meta Cloud API) — JSON inbound webhook.

**Patient resolution:** both providers resolve the sender via `database.get_patient_by_phone()` / `normalise_phone_number()` (strips `whatsapp:` prefix, spaces, dashes; ensures a `+` prefix, e.g. `+60123456789`). Phone numbers are linked to patients via the `set_patient_phone` MCP tool, stored in `patients.phone_number`.

**Opt-out:** replying `STOP` / `BERHENTI` sets `Patient.whatsapp_opted_out = true`; `START` / `MULA` clears it (column added via `scripts/migrate_whatsapp_columns.py`). Opt-out only gates *scheduled* content (`_send_patient_content` in `mcp_server.py` checks the flag) — direct chat replies always work, since a patient messaging in is implicit consent for that conversation.

**Message processing (`_process_and_reply`, runs as a `BackgroundTask`):**
1. Calls `rag.get_rag_response()` with `session_id=f"whatsapp-{patient_id}"` — this is the same `chat_messages` table as the website (§13), so conversation history carries over per patient regardless of channel.
2. Runs the profile extractor (§7.5) in the background on the inbound message, same as the website path.
3. Truncates the reply to 1500 chars (WhatsApp message limit) and sends via `whatsapp.send_message()`.
4. Twilio webhook replies immediately with empty TwiML (200 OK); the actual RAG reply is sent async via the WhatsApp REST API a few seconds later.

**Still pending for go-live:** set `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` (or `META_WHATSAPP_TOKEN` / `META_WHATSAPP_PHONE_ID` / `META_VERIFY_TOKEN`) in `.env`, register the webhook URL with the provider (`https://nutribot.computationalrd.com/chat/whatsapp`), and link patient phone numbers via `set_patient_phone`.
