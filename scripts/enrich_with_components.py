"""
Tag existing chunks in a PGVector collection with a MyHeartCoach Component
(see taxonomy.py) via doc_components metadata — same JSONB-merge pattern as
enrich_v1_with_keywords.py, no embedding/chunk changes.

One-time backfill for the current corpus (100% nutrition-sourced today):

    python scripts/enrich_with_components.py --component nutrition --dry-run
    python scripts/enrich_with_components.py --component nutrition

Only rows without an existing doc_components key are touched (idempotent,
re-runnable, and safe to run again after step 4 starts stamping new ingests
directly). To scope a future non-nutrition document set instead of the
whole collection, add --source-like (SQL LIKE against cmetadata->>'source'):

    python scripts/enrich_with_components.py --component exercise --source-like '%aha_exercise_guide.pdf'

To ADD a second component onto chunks that are already tagged (e.g. a
document that's both nutrition and blood_pressure content), use --additive
— this appends/dedups into the existing doc_components array instead of
only touching untagged rows:

    python scripts/enrich_with_components.py --component blood_pressure \\
        --source-like 'CPG Management of Hypertension.pdf' --additive --dry-run
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

from taxonomy import COMPONENTS

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

PGVECTOR_URL = os.getenv("PGVECTOR_URL")
if not PGVECTOR_URL:
    raise SystemExit("PGVECTOR_URL not set")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", required=True, choices=COMPONENTS)
    parser.add_argument("--collection", default="base_knowledge")
    parser.add_argument(
        "--source-like",
        default=None,
        help="SQL LIKE pattern against cmetadata->>'source'. Omit to target the whole collection.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--additive",
        action="store_true",
        help="Append this component onto chunks that already have a doc_components array "
             "(deduped), instead of only touching untagged rows.",
    )
    args = parser.parse_args()

    engine = create_engine(PGVECTOR_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    collection_uuid = session.execute(
        text("SELECT uuid FROM langchain_pg_collection WHERE name = :name"),
        {"name": args.collection},
    ).scalar()
    if not collection_uuid:
        raise SystemExit(f"Collection '{args.collection}' not found")
    print(f"Collection '{args.collection}' uuid: {collection_uuid}")
    print(f"Component: {args.component} | source_like: {args.source_like or '(all untagged rows)'}\n")

    where = "collection_id = :coll"
    if not args.additive:
        where += " AND NOT (cmetadata ? 'doc_components')"
    params = {"coll": collection_uuid}
    if args.source_like:
        where += " AND cmetadata->>'source' LIKE :src"
        params["src"] = args.source_like

    t0 = time.time()
    if args.dry_run:
        n = session.execute(text(f"SELECT COUNT(*) FROM langchain_pg_embedding WHERE {where}"), params).scalar()
        verb = "add" if args.additive else "tag"
        print(f"Would {verb} {n:,} chunks with doc_components += [\"{args.component}\"]")
    elif args.additive:
        # Dedup-append: union the existing doc_components array (or [] if absent) with
        # the new component, so re-running is a no-op and existing tags (e.g. nutrition)
        # survive.
        result = session.execute(
            text(
                f"""
                UPDATE langchain_pg_embedding
                SET cmetadata = jsonb_set(
                    cmetadata::jsonb,
                    '{{doc_components}}',
                    (
                        SELECT jsonb_agg(DISTINCT elem)
                        FROM jsonb_array_elements(
                            COALESCE(cmetadata->'doc_components', '[]'::jsonb)
                            || jsonb_build_array(CAST(:component AS text))
                        ) AS elem
                    )
                )
                WHERE {where}
                """
            ),
            {**params, "component": args.component},
        )
        session.commit()
        print(f"Added \"{args.component}\" to doc_components on {result.rowcount:,} chunks")
    else:
        patch = json.dumps({"doc_components": [args.component]})
        result = session.execute(
            text(
                f"UPDATE langchain_pg_embedding SET cmetadata = cmetadata::jsonb || CAST(:patch AS jsonb) WHERE {where}"
            ),
            {**params, "patch": patch},
        )
        session.commit()
        print(f"Tagged {result.rowcount:,} chunks with doc_components=[\"{args.component}\"]")

    print(f"Elapsed: {time.time() - t0:.1f}s")
    session.close()


if __name__ == "__main__":
    main()
