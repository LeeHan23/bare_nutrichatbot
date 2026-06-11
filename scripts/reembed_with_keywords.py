"""
Re-embed existing chunks with prepended keyword context (Option A + B).

What this does:
  1. Reads chunks from existing PGVector collection (`base_knowledge`)
  2. For each chunk, looks up its source document's keywords
  3. Prepends a topic/keyword prefix to the chunk text
  4. Re-embeds with the existing bge-m3 + LoRA model
  5. Writes to a NEW collection (`base_knowledge_v2`) with enriched metadata

What this does NOT do:
  - Re-parse PDFs (the chunks already passed junk-filter cleanup)
  - Re-chunk text (chunking is fine; only the embedding context changes)
  - Touch the existing `base_knowledge` collection (safety: A/B test then swap)

Usage:
  python scripts/reembed_with_keywords.py \\
    --mapping data/encpt/doc_keyword_mapping.json \\
    --source-collection base_knowledge \\
    --target-collection base_knowledge_v2 \\
    [--client-id 4]   # restrict to one tenant if multi-tenant
    [--dry-run]       # show plan without writing
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator

# Add the bot codebase to path so we can import its helpers
sys.path.insert(0, '/mnt/ext/bare_NutriChatbot')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv('/mnt/ext/bare_NutriChatbot/.env')

from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.documents import Document

# Import the project's embedding model loader so we use the exact same
# bge-m3 + LoRA adapter as production.
from embeddings import get_embedding_function as get_embedding_model

PGVECTOR_URL = os.getenv("PGVECTOR_URL")
if not PGVECTOR_URL:
    raise SystemExit("PGVECTOR_URL not set in .env")


def load_mapping(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    return data["documents"]


def filename_fallback_keywords(filename: str) -> dict:
    """For documents not in the curated mapping, derive topic hints from filename."""
    stem = Path(filename).stem
    parts = [p for p in stem.replace("-", " ").replace("_", " ").split() if len(p) > 2]
    return {
        "keywords": parts[:8],
        "topic_summary": f"Document: {stem}",
        "primary_topics": parts[:3],
        "language": "en",
        "note": "auto-derived from filename"
    }


def build_keyword_prefix(doc_info: dict, lang: str = "en") -> str:
    """Construct the keyword/topic prefix to prepend to chunk text."""
    topics = ", ".join(doc_info["primary_topics"])
    keywords = "; ".join(doc_info["keywords"][:10])  # cap to keep prefix manageable
    summary = doc_info.get("topic_summary", "")

    if lang == "ms":
        return (
            f"[Topik: {topics}]\n"
            f"[Kata kunci dokumen: {keywords}]\n"
            f"[Ringkasan: {summary}]\n\n"
        )
    return (
        f"[Topics: {topics}]\n"
        f"[Document focus: {keywords}]\n"
        f"[Summary: {summary}]\n\n"
    )


def iter_chunks_from_source(
    engine, source_collection: str, client_id: int | None = None,
    batch_size: int = 200,
) -> Iterator[dict]:
    """Stream chunks from the existing PGVector collection."""
    Session = sessionmaker(bind=engine)
    session = Session()

    base_sql = """
        SELECT e.uuid, e.document, e.cmetadata
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :collection
    """
    params = {"collection": source_collection}
    if client_id is not None:
        base_sql += " AND (e.cmetadata->>'client_id')::int = :client_id"
        params["client_id"] = client_id
    base_sql += " ORDER BY e.uuid"

    rows = session.execute(text(base_sql), params).fetchall()
    session.close()
    print(f"  Fetched {len(rows):,} rows into memory")

    for row in rows:
        yield {
            "id": str(row.uuid),
            "text": row.document or "",
            "metadata": row.cmetadata or {},
        }


def count_chunks(engine, source_collection: str, client_id: int | None = None) -> int:
    Session = sessionmaker(bind=engine)
    session = Session()
    sql = """
        SELECT COUNT(*) FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :collection
    """
    params = {"collection": source_collection}
    if client_id is not None:
        sql += " AND (e.cmetadata->>'client_id')::int = :client_id"
        params["client_id"] = client_id
    n = session.execute(text(sql), params).scalar()
    session.close()
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", required=True, help="Path to doc_keyword_mapping.json")
    parser.add_argument("--source-collection", default="base_knowledge")
    parser.add_argument("--target-collection", default="base_knowledge_v2")
    parser.add_argument("--client-id", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Documents per add_documents() call")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing")
    args = parser.parse_args()

    print(f"Loading mapping from {args.mapping}")
    mapping = load_mapping(args.mapping)
    print(f"  {len(mapping)} documents mapped\n")

    print(f"Connecting to {PGVECTOR_URL.split('@')[-1]}")
    engine = create_engine(PGVECTOR_URL)

    total = count_chunks(engine, args.source_collection, args.client_id)
    print(f"Source collection '{args.source_collection}': {total:,} chunks\n")

    if args.dry_run:
        print("DRY RUN — counting per-document distribution...")
        Session = sessionmaker(bind=engine)
        session = Session()
        sql = """
            SELECT e.cmetadata->>'source' as source, COUNT(*)
            FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE c.name = :collection
            GROUP BY source
            ORDER BY COUNT(*) DESC
            LIMIT 30
        """
        for row in session.execute(text(sql), {"collection": args.source_collection}):
            src = row.source or "(no source)"
            mapped = "✓" if any(src.endswith(k) or k.endswith(src or '') for k in mapping) else "✗"
            print(f"  {mapped}  {row.count:>5}  {src}")
        session.close()
        return

    # Build the embedding model (same as production)
    print("Loading bge-m3 + LoRA embedding model...")
    embed_model = get_embedding_model()

    # Initialize the target PGVector collection
    target_store = PGVector(
        collection_name=args.target_collection,
        connection_string=PGVECTOR_URL,
        embedding_function=embed_model,
    )
    print(f"Target collection '{args.target_collection}' ready\n")

    # Stats
    stats = {
        "processed": 0,
        "mapped": 0,
        "fallback": 0,
        "skipped": 0,
        "batches": 0,
    }
    batch_buffer = []
    t0 = time.time()

    def flush_batch():
        if not batch_buffer:
            return
        target_store.add_documents(batch_buffer)
        stats["batches"] += 1
        batch_buffer.clear()

    for chunk in iter_chunks_from_source(
        engine, args.source_collection, args.client_id
    ):
        stats["processed"] += 1
        meta = chunk["metadata"] or {}

        # Identify source document
        source_filename = (
            meta.get("source") or meta.get("filename") or meta.get("source_file")
            or ""
        )
        # If full path, take basename
        source_filename = Path(source_filename).name if source_filename else ""

        doc_info = mapping.get(source_filename)
        if doc_info:
            stats["mapped"] += 1
        elif source_filename:
            doc_info = filename_fallback_keywords(source_filename)
            stats["fallback"] += 1
        else:
            stats["skipped"] += 1
            continue

        lang = doc_info.get("language", "en")
        prefix = build_keyword_prefix(doc_info, lang)
        enriched_text = prefix + chunk["text"]

        # Enriched metadata for filtering
        new_meta = dict(meta)
        new_meta["doc_keywords"] = doc_info["keywords"]
        new_meta["doc_topics"] = doc_info["primary_topics"]
        new_meta["doc_language"] = lang
        new_meta["reembed_version"] = "v2-keyword-prefix"

        batch_buffer.append(Document(page_content=enriched_text, metadata=new_meta))

        if len(batch_buffer) >= args.batch_size:
            flush_batch()
            elapsed = time.time() - t0
            rate = stats["processed"] / elapsed
            eta = (total - stats["processed"]) / rate if rate > 0 else 0
            print(f"  {stats['processed']:>6}/{total} chunks  "
                  f"({rate:.1f} chunks/s, ETA {eta/60:.1f} min)  "
                  f"mapped={stats['mapped']} fallback={stats['fallback']}")

    flush_batch()
    elapsed = time.time() - t0

    print(f"\n✅ Done in {elapsed/60:.1f} min")
    for k, v in stats.items():
        print(f"  {k:>10}: {v:,}")


if __name__ == "__main__":
    main()
