import os
import random
import pandas as pd
from typing import List, Dict
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    context_precision,
    faithfulness,
    answer_relevancy,
)

from dotenv import load_dotenv

# Load env vars
load_dotenv()

# --- Configuration ---
DATA_DIR = "./documents_to_ingest" # Pointing to the actual PDF location
OUTPUT_FILE = "rag_evaluation_report.csv"
NUM_TEST_SAMPLES = 20
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Ensure API keys are set (User responsibility, but good to check)
if not os.getenv("OPENAI_API_KEY"):
    print("⚠️ WARNING: OPENAI_API_KEY not found in environment variables. Evaluation may fail.")

# --- 1. Data Ingestion ---
def load_and_split_documents(directory: str) -> List:
    """
    Loads all PDF files from the directory and splits them into chunks.
    Skips files that cause errors.
    """
    print(f"📂 Loading PDFs from {directory}...")
    
    all_documents = []
    pdf_files = [f for f in os.listdir(directory) if f.lower().endswith('.pdf')]
    
    for pdf_file in pdf_files:
        file_path = os.path.join(directory, pdf_file)
        try:
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            all_documents.extend(docs)
            # print(f"  ✅ Loaded {pdf_file}")
        except Exception as e:
            print(f"  ❌ Failed to load {pdf_file}: {e}")
            
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )
    chunks = text_splitter.split_documents(all_documents)
    print(f"✅ Loaded {len(all_documents)} documents and split into {len(chunks)} chunks.")
    return chunks

# --- 2. Synthetic "Golden Dataset" Generation ---
def generate_test_set(chunks: List, num_samples: int) -> List[Dict]:
    """
    Selects random chunks and uses an LLM to generate Question-Answer pairs.
    """
    print(f"🧪 Generating {num_samples} synthetic test samples...")
    
    # Select random chunks
    selected_chunks = random.sample(chunks, min(num_samples, len(chunks)))
    
    # Initialize LLM for generation (Using OpenAI as requested)
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)
    
    test_set = []
    
    for i, chunk in enumerate(selected_chunks):
        context = chunk.page_content
        
        # Prompt to generate a question and answer based ONLY on the context
        prompt = f"""
        You are a strict teacher creating a test.
        Based ONLY on the following text context, generate a specific question and the correct answer.
        
        Context:
        {context}
        
        Format your response exactly as:
        QUESTION: <question>
        ANSWER: <answer>
        """
        
        try:
            response = llm([HumanMessage(content=prompt)])
            content = response.content
            
            # Parse the response
            if "QUESTION:" in content and "ANSWER:" in content:
                parts = content.split("ANSWER:")
                question = parts[0].replace("QUESTION:", "").strip()
                ground_truth = parts[1].strip()
                
                test_set.append({
                    "question": question,
                    "ground_truth": ground_truth,
                    "context": context # Keep track of the source context
                })
                print(f"  [{i+1}/{num_samples}] Generated Q: {question[:50]}...")
            else:
                print(f"  [{i+1}/{num_samples}] ⚠️ Failed to parse LLM response. Skipping.")
                
        except Exception as e:
            print(f"  [{i+1}/{num_samples}] ❌ Error generating sample: {e}")
            
    return test_set

# --- 3. Evaluation Loop ---
# Import the actual chatbot function
try:
    from rag import get_rag_response
    from chain_factory import create_conversational_chain
    # We need to access the chain directly to get source documents, 
    # as get_rag_response might not return them in the format we need.
    USING_REAL_BOT = True
    print("✅ Successfully imported chatbot modules.")
except ImportError as e:
    print(f"⚠️ Could not import actual chatbot. Using placeholder. Error: {e}")
    USING_REAL_BOT = False
except Exception as e:
    print(f"⚠️ Unexpected error importing chatbot: {e}")
    USING_REAL_BOT = False

def get_bot_prediction(question: str):
    """
    Wraps the chatbot to return answer and retrieved contexts.
    """
    if USING_REAL_BOT:
        # We create a fresh chain to ensure we get source docs
        # Using a dummy client_id/disease for evaluation context
        qa_chain = create_conversational_chain(client_id=999, target_disease="General Health")
        
        response = qa_chain({"question": question, "chat_history": []})
        
        answer = response.get("answer", "")
        source_docs = response.get("source_documents", [])
        contexts = [doc.page_content for doc in source_docs]
        
        return answer, contexts
    else:
        # Placeholder for testing if imports fail
        return "This is a predicted answer.", ["This is a retrieved context."]

def run_evaluation_loop(test_set: List[Dict]) -> pd.DataFrame:
    """
    Runs the test set through the chatbot and prepares data for RAGAS.
    """
    print("🤖 Running evaluation loop on chatbot...")
    
    data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": []
    }
    
    for item in test_set:
        question = item["question"]
        ground_truth = item["ground_truth"]
        
        # Get prediction
        predicted_answer, retrieved_contexts = get_bot_prediction(question)
        
        data["question"].append(question)
        data["answer"].append(predicted_answer)
        data["contexts"].append(retrieved_contexts)
        data["ground_truth"].append(ground_truth)
        
    return pd.DataFrame(data)

# --- 1.5 Vector Store Ingestion ---
try:
    from langchain_community.vectorstores import Chroma
    from vector_store import BASE_INDEX_DIR, EMBEDDING_MODEL
except ImportError:
    # Fallback if vector_store.py imports fail
    BASE_INDEX_DIR = "./data/vectorstore_base"
    EMBEDDING_MODEL = "text-embedding-3-small"
    print("⚠️ Could not import vector_store config. Using defaults.")

def ingest_to_vector_store(chunks: List):
    """
    Ingests the chunks into the Chroma vector store.
    """
    print(f"💾 Ingesting {len(chunks)} chunks into vector store at {BASE_INDEX_DIR}...")
    
    embedding_function = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    
    db = Chroma(
        persist_directory=BASE_INDEX_DIR,
        embedding_function=embedding_function,
        collection_name="base_knowledge"
    )
    
    # Add documents in batches to avoid hitting Chroma's max batch size
    BATCH_SIZE = 5000
    total_chunks = len(chunks)
    
    for i in range(0, total_chunks, BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        print(f"  ↳ Ingesting batch {i//BATCH_SIZE + 1}/{(total_chunks + BATCH_SIZE - 1)//BATCH_SIZE} ({len(batch)} chunks)...")
        db.add_documents(batch)
        
    db.persist()
    print("✅ Ingestion complete and persisted.")

# --- 4. Scoring (The "Orthodox" Proof) ---
def score_with_ragas(df: pd.DataFrame):
    """
    Calculates RAGAS metrics.
    """
    print("📊 Calculating RAGAS metrics (Context Precision, Faithfulness, Answer Relevancy)...")
    
    # Convert to Hugging Face Dataset
    dataset = Dataset.from_pandas(df)
    
    # Run evaluation
    gpt4_llm = ChatOpenAI(model_name="gpt-4", temperature=0)
    
    # Use the SAME embedding model as the vector store for RAGAS
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    
    results = evaluate(
        dataset=dataset,
        metrics=[
            context_precision,
            faithfulness,
            answer_relevancy,
        ],
        llm=gpt4_llm, 
        embeddings=embeddings
    )
    
    print("\n📈 --- Evaluation Results ---")
    print(results)
    
    # Add scores back to DataFrame for detailed analysis
    result_df = results.to_pandas()
    return result_df

# --- Main Execution ---
if __name__ == "__main__":
    # 1. Load & Split
    chunks = load_and_split_documents(DATA_DIR)
    
    if not chunks:
        print("❌ No documents found. Exiting.")
        exit()
        
    # 1.5 Ingest (CRITICAL STEP ADDED)
    ingest_to_vector_store(chunks)
        
    # 2. Generate Test Set
    test_set = generate_test_set(chunks, NUM_TEST_SAMPLES)
    
    # 3. Run Bot
    eval_df = run_evaluation_loop(test_set)
    
    # 4. Score
    final_results = score_with_ragas(eval_df)
    
    # 5. Save
    final_results.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Evaluation complete! Results saved to {OUTPUT_FILE}")
