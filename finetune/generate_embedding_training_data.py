"""
generate_embedding_training_data.py

Pulls all chunks from the pgvector base_knowledge collection and uses an LLM
to generate realistic medical/nutrition questions for each chunk. Outputs
(anchor_query, positive_document) pairs in JSONL format for SentenceTransformer
fine-tuning.

Output files (written to ~/data/ to avoid filling /mnt/ssd):
  ~/data/embedding_train.jsonl   — 90% of pairs
  ~/data/embedding_val.jsonl     — 10% of pairs

Providers:
  --provider openai   Use OpenAI GPT-4 (requires OPENAI_API_KEY + quota)
  --provider ollama   Use local Ollama model (free, default: granite4)

Usage:
    python generate_embedding_training_data.py --provider ollama
    python generate_embedding_training_data.py --provider ollama --ollama-model nutribot
    python generate_embedding_training_data.py --provider openai --limit 200
    python generate_embedding_training_data.py --batch 5   # chunks per LLM call
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error

from dotenv import load_dotenv

load_dotenv()

import psycopg2

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)
COLLECTION_NAME = "base_knowledge"
OUTPUT_DIR = os.path.expanduser("~/data")
TRAIN_FILE = os.path.join(OUTPUT_DIR, "embedding_train.jsonl")
VAL_FILE = os.path.join(OUTPUT_DIR, "embedding_val.jsonl")
VAL_SPLIT = 0.10
GPT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4-turbo")
DEFAULT_OLLAMA_MODEL = "granite4"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
QUERIES_PER_CHUNK = 2
BATCH_SIZE = 5  # smaller default — Ollama handles one chunk at a time better

SYSTEM_PROMPT = (
    "You are a medical nutrition expert building a retrieval training dataset. "
    "Given a text passage, generate realistic questions whose answer is in that passage. "
    "Output exactly {n} questions, one per line, no numbering or bullet points. "
    "Vary phrasing: some patient-level ('Can I eat...?'), some clinical ('What is the recommended...'). "
    "Include Malay questions where the passage discusses Malaysian food. "
    "Do NOT repeat wording from the passage verbatim."
)


def get_db_connection():
    url = PGVECTOR_URL
    if "+psycopg2" in url:
        url = url.replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(url)


def fetch_all_chunks(limit: int | None = None) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.uuid, e.document, e.cmetadata
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON c.uuid = e.collection_id
        WHERE c.name = %s
          AND length(e.document) > 100
        ORDER BY e.uuid
    """, (COLLECTION_NAME,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    chunks = [{"id": str(r[0]), "text": r[1], "meta": r[2]} for r in rows]
    if limit:
        chunks = chunks[:limit]
    return chunks


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------
def _openai_generate(chunks: list[dict]) -> list[list[str]]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    parts = [f"--- PASSAGE {i+1} ---\n{c['text'][:1200]}" for i, c in enumerate(chunks)]
    prompt = (
        f"For each of the {len(chunks)} passages below, generate {QUERIES_PER_CHUNK} questions "
        f"whose answer is in that passage.\n"
        f"Format: {len(chunks)} groups separated by '===', each with {QUERIES_PER_CHUNK} questions.\n\n"
        + "\n\n".join(parts)
    )
    resp = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(n=QUERIES_PER_CHUNK)},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=QUERIES_PER_CHUNK * len(chunks) * 80,
    )
    raw = resp.choices[0].message.content.strip()
    groups = raw.split("===")
    result = []
    for group in groups[: len(chunks)]:
        lines = [ln.strip().lstrip("0123456789.-) ") for ln in group.strip().splitlines() if ln.strip()]
        result.append([ln for ln in lines if len(ln) > 10][:QUERIES_PER_CHUNK])
    while len(result) < len(chunks):
        result.append([])
    return result


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------
def _ollama_chat(model: str, system: str, user: str) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 300},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"].strip()


def _ollama_generate(chunks: list[dict], model: str) -> list[list[str]]:
    result = []
    for chunk in chunks:
        user_msg = (
            f"Passage:\n{chunk['text'][:1500]}\n\n"
            f"Generate {QUERIES_PER_CHUNK} questions whose answer is in this passage. "
            f"Output only the questions, one per line."
        )
        try:
            raw = _ollama_chat(model, SYSTEM_PROMPT.format(n=QUERIES_PER_CHUNK), user_msg)
            lines = [ln.strip().lstrip("0123456789.-) ") for ln in raw.splitlines() if ln.strip()]
            questions = [ln for ln in lines if len(ln) > 10][:QUERIES_PER_CHUNK]
            result.append(questions)
        except Exception as e:
            print(f"\n    Ollama error: {e}")
            result.append([])
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def generate_questions_for_batch(chunks, provider: str, ollama_model: str) -> list[list[str]]:
    try:
        if provider == "openai":
            return _openai_generate(chunks)
        else:
            return _ollama_generate(chunks, ollama_model)
    except Exception as e:
        print(f"\n    LLM error: {e}")
        return [[] for _ in chunks]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["openai", "ollama"], default="ollama",
                        help="LLM provider (default: ollama)")
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL,
                        help=f"Ollama model name (default: {DEFAULT_OLLAMA_MODEL})")
    parser.add_argument("--limit", type=int, default=None, help="Max chunks to process")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Chunks per LLM call")
    parser.add_argument("--resume", action="store_true",
                        help="Append to existing output files instead of overwriting")
    args = parser.parse_args()

    if args.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set")

    if args.provider == "ollama":
        try:
            urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        except Exception:
            sys.exit(f"Ollama not reachable at {OLLAMA_URL} — is it running?")
        print(f"Using Ollama model: {args.ollama_model}")
    else:
        print(f"Using OpenAI model: {GPT_MODEL}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Fetching chunks from pgvector collection '{COLLECTION_NAME}'...")
    chunks = fetch_all_chunks(args.limit)
    print(f"Found {len(chunks)} chunks.")

    # Resume: skip already-processed chunks by counting existing pairs
    start_chunk = 0
    if args.resume and os.path.exists(TRAIN_FILE):
        with open(TRAIN_FILE) as f:
            existing = sum(1 for _ in f)
        # Rough estimate: existing pairs / QUERIES_PER_CHUNK = processed chunks
        start_chunk = existing // QUERIES_PER_CHUNK
        print(f"Resuming from chunk ~{start_chunk} ({existing} existing train pairs)")
        chunks = chunks[start_chunk:]

    pairs: list[dict] = []
    total_batches = (len(chunks) + args.batch - 1) // args.batch

    for batch_idx in range(0, len(chunks), args.batch):
        batch = chunks[batch_idx: batch_idx + args.batch]
        bn = batch_idx // args.batch + 1
        print(f"  Batch {bn}/{total_batches} ({start_chunk + batch_idx + len(batch)}/{start_chunk + len(chunks)} chunks)...",
              end=" ", flush=True)

        questions_per_chunk = generate_questions_for_batch(batch, args.provider, args.ollama_model)

        added = 0
        for chunk, questions in zip(batch, questions_per_chunk):
            for q in questions:
                pairs.append({"anchor": q, "positive": chunk["text"]})
                added += 1
        print(f"+{added} pairs")

    print(f"\nNew pairs this run: {len(pairs)}")
    if not pairs:
        sys.exit("No pairs generated.")

    random.shuffle(pairs)
    split = max(1, int(len(pairs) * VAL_SPLIT))
    val_pairs, train_pairs = pairs[:split], pairs[split:]

    mode = "a" if args.resume else "w"

    def write_jsonl(path, records, mode):
        with open(path, mode, encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_jsonl(TRAIN_FILE, train_pairs, mode)
    write_jsonl(VAL_FILE, val_pairs, mode)

    print(f"Train: {len(train_pairs)} pairs → {TRAIN_FILE}")
    print(f"Val:   {len(val_pairs)} pairs → {VAL_FILE}")
    print("Done.")


if __name__ == "__main__":
    main()
