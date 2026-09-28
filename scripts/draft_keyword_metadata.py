"""
LLM-assisted first draft of doc_keyword_mapping.json entries for newly-ingested
documents_clean/ files (and any pre-existing orphans never mapped).

What this does:
  - Diffs filenames on disk in documents_clean/ against keys already in
    data/encpt/doc_keyword_mapping.json
  - For each unmapped file, pulls its already-ingested chunk text straight from
    Postgres (base_knowledge) — no re-parsing of the PDF/docx needed, the
    ingestion that already ran did that work
  - Asks Qwen (llm.call_ollama_generate) to draft keywords/topic_summary/
    primary_topics/language as strict JSON, steering primary_topics toward the
    vocabulary vector_store.TOPIC_HINTS already recognizes so new entries
    actually engage TopicBoostedRetriever's boosting
  - Writes drafts to doc_keyword_mapping.draft.json — a human reviews/edits
    this before it's merged into the real mapping file

What this does NOT do:
  - Touch doc_keyword_mapping.json itself
  - Touch Postgres (read-only)
"""
import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from sqlalchemy import create_engine, text

DEFAULT_CLEAN_DIR = "/home/han/Desktop/projects/documents_clean"
DEFAULT_MAPPING = os.path.join(_PROJECT_ROOT, "data", "encpt", "doc_keyword_mapping.json")
DEFAULT_OUT = os.path.join(_PROJECT_ROOT, "data", "encpt", "doc_keyword_mapping.draft.json")
EXCERPT_CHARS = 3000

PROMPT_TEMPLATE = """You are drafting search metadata for a clinical nutrition document
used in a cardiac-patient chatbot's retrieval system.

Filename: {filename}

Excerpt from the document:
---
{excerpt}
---

Preferred topic vocabulary (reuse these exact strings in primary_topics whenever they
fit — this vocabulary is what the retrieval system's topic-boost already recognizes):
{topic_vocab}

Return ONLY strict JSON, no markdown fences, no commentary, matching exactly this schema:
{{"keywords": ["...", "..."], "topic_summary": "one sentence", "primary_topics": ["...", "..."], "language": "en"}}

- keywords: 5-12 short search terms/phrases from the document (English; also include Malay
  terms if the document is in Malay)
- topic_summary: one plain sentence summarizing what the document covers
- primary_topics: 2-5 topics, preferring the vocabulary list above; add a new topic string
  only if nothing in the list fits
- language: "en" or "ms" based on the excerpt's primary language
"""


def get_topic_vocabulary() -> list:
    import vector_store
    all_topics = set()
    for topics in vector_store.TOPIC_HINTS.values():
        all_topics.update(topics)
    return sorted(all_topics)


def get_unmapped_filenames(clean_dir: str, mapping_path: str) -> list:
    with open(mapping_path) as f:
        mapped = set(json.load(f)["documents"].keys())
    on_disk = {f for f in os.listdir(clean_dir) if os.path.isfile(os.path.join(clean_dir, f)) and not f.startswith(".")}
    return sorted(on_disk - mapped)


def get_chunk_excerpt(conn, filename: str, max_chars: int) -> str:
    rows = conn.execute(
        text("""
            SELECT e.document FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE c.name = 'base_knowledge' AND e.cmetadata->>'source' = :fname
            ORDER BY e.uuid
            LIMIT 10
        """),
        {"fname": filename},
    ).fetchall()
    text_parts = []
    total = 0
    for (doc,) in rows:
        text_parts.append(doc)
        total += len(doc)
        if total >= max_chars:
            break
    return "\n\n".join(text_parts)[:max_chars]


def extract_json(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(raw[start:end + 1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-dir", default=DEFAULT_CLEAN_DIR)
    parser.add_argument("--mapping", default=DEFAULT_MAPPING)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="only process the first N unmapped files")
    args = parser.parse_args()

    from llm import call_ollama_generate

    unmapped = get_unmapped_filenames(args.clean_dir, args.mapping)
    if args.limit:
        unmapped = unmapped[:args.limit]
    print(f"{len(unmapped)} unmapped files to draft metadata for")

    topic_vocab = get_topic_vocabulary()
    topic_vocab_str = ", ".join(topic_vocab)

    pgvector_url = os.environ["PGVECTOR_URL"]
    engine = create_engine(pgvector_url)

    drafts = {}
    failures = []

    with engine.connect() as conn:
        for i, filename in enumerate(unmapped, 1):
            excerpt = get_chunk_excerpt(conn, filename, EXCERPT_CHARS)
            if not excerpt.strip():
                print(f"  [{i}/{len(unmapped)}] SKIP (no ingested chunks found): {filename}")
                failures.append((filename, "no_chunks_in_db"))
                continue

            prompt = PROMPT_TEMPLATE.format(filename=filename, excerpt=excerpt, topic_vocab=topic_vocab_str)
            try:
                raw = call_ollama_generate(prompt, max_tokens=500)
                parsed = extract_json(raw)
                for key in ("keywords", "topic_summary", "primary_topics", "language"):
                    if key not in parsed:
                        raise ValueError(f"missing key '{key}' in LLM response")
                drafts[filename] = parsed
                print(f"  [{i}/{len(unmapped)}] OK: {filename}")
            except Exception as e:
                print(f"  [{i}/{len(unmapped)}] FAILED ({e}): {filename}")
                failures.append((filename, str(e)))

    out = {
        "version": "1.0-draft",
        "based_on": "LLM-drafted (scripts/draft_keyword_metadata.py) — NOT reviewed, do not merge as-is",
        "languages": ["en", "ms"],
        "documents": drafts,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(drafts)} drafted entries to {args.out}")
    if failures:
        print(f"\n{len(failures)} file(s) failed and need manual entries instead:")
        for filename, reason in failures:
            print(f"  {filename}: {reason}")
    print("\nReview the draft file before merging into data/encpt/doc_keyword_mapping.json.")


if __name__ == "__main__":
    main()
