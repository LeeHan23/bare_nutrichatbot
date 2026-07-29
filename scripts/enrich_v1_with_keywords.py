"""
Add curated keyword metadata to existing chunks in base_knowledge.

What this does:
  - Reads doc_keyword_mapping.json
  - For each mapped document, finds its chunks in langchain_pg_embedding
  - Merges keywords/topics/summary/language into the chunk's cmetadata JSON
  - UPDATEs in place — no embedding changes, no chunk changes

What this does NOT do:
  - Touch embeddings
  - Touch chunks for documents not in the mapping (left untouched)
  - Create a new collection (everything stays in base_knowledge)
"""
import argparse
import json
import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

PGVECTOR_URL = os.getenv("PGVECTOR_URL")
if not PGVECTOR_URL:
    raise SystemExit("PGVECTOR_URL not set")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--collection", default="base_knowledge")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.mapping) as f:
        mapping = json.load(f)["documents"]
    print(f"Loaded {len(mapping)} mapped documents")

    engine = create_engine(PGVECTOR_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Get collection UUID
    collection_uuid = session.execute(
        text("SELECT uuid FROM langchain_pg_collection WHERE name = :name"),
        {"name": args.collection},
    ).scalar()
    if not collection_uuid:
        raise SystemExit(f"Collection '{args.collection}' not found")
    print(f"Collection '{args.collection}' uuid: {collection_uuid}\n")

    # For each mapped document, run an UPDATE that merges keyword fields into cmetadata
    total_updated = 0
    t0 = time.time()
    for filename, doc_info in mapping.items():
        new_meta_patch = {
            "doc_keywords": doc_info["keywords"],
            "doc_topics": doc_info["primary_topics"],
            "doc_topic_summary": doc_info.get("topic_summary", ""),
            "doc_language": doc_info.get("language", "en"),
            "keyword_enrichment_version": "v1-metadata-only",
        }

        # JSONB || merges and overwrites overlapping keys
        # cmetadata is JSONB in PGVector; cast to be safe
        update_sql = text("""
            UPDATE langchain_pg_embedding
            SET cmetadata = cmetadata::jsonb || CAST(:patch AS jsonb)
            WHERE collection_id = :coll
              AND (
                  cmetadata->>'source' = :fname
                  OR cmetadata->>'source' LIKE :fname_like
                  OR cmetadata->>'filename' = :fname
              )
        """)

        params = {
            "patch": json.dumps(new_meta_patch),
            "coll": collection_uuid,
            "fname": filename,
            "fname_like": f"%/{filename}",
        }

        if args.dry_run:
            count_sql = text("""
                SELECT COUNT(*) FROM langchain_pg_embedding
                WHERE collection_id = :coll
                  AND (
                      cmetadata->>'source' = :fname
                      OR cmetadata->>'source' LIKE :fname_like
                      OR cmetadata->>'filename' = :fname
                  )
            """)
            n = session.execute(count_sql, {
                "coll": collection_uuid,
                "fname": filename,
                "fname_like": f"%/{filename}",
            }).scalar()
            print(f"  Would update {n:>5} chunks  -  {filename[:75]}")
            total_updated += n
        else:
            result = session.execute(update_sql, params)
            n = result.rowcount
            print(f"  Updated   {n:>5} chunks  -  {filename[:75]}")
            total_updated += n
            session.commit()

    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"{'DRY RUN — ' if args.dry_run else ''}Total chunks {'matched' if args.dry_run else 'updated'}: {total_updated:,}")
    print(f"Elapsed: {elapsed:.1f}s")

    if not args.dry_run:
        # Spot-check one chunk to confirm the merge worked
        sample = session.execute(text("""
            SELECT cmetadata FROM langchain_pg_embedding
            WHERE collection_id = :coll
              AND cmetadata ? 'doc_keywords'
            LIMIT 1
        """), {"coll": collection_uuid}).scalar()
        if sample:
            print(f"\nSample enriched chunk metadata:")
            print(json.dumps(sample, indent=2, ensure_ascii=False)[:600])

    session.close()


if __name__ == "__main__":
    main()
