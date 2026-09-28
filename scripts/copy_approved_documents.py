"""
Copy files approved in the (human-reviewed) triage manifest from documents/ into
documents_clean/, ahead of running build_base_db.py.

What this does:
  - Reads the manifest CSV (see triage_documents.py), copies every row with
    action == "include" from --documents-dir into --clean-dir
  - Never deletes or overwrites anything in --clean-dir
  - For a copied file whose reason flagged it as a possible newer edition of an
    existing file, prints a reminder to manually check/remove the old one —
    that decision is never made automatically

What this does NOT do:
  - Run ingestion (build_base_db.py) — that's a separate, later step
  - Touch any row whose action isn't exactly "include"
"""
import argparse
import csv
import os
import shutil
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DOCUMENTS_DIR = "/home/han/Desktop/projects/documents"
DEFAULT_CLEAN_DIR = "/home/han/Desktop/projects/documents_clean"
DEFAULT_MANIFEST = os.path.join(_PROJECT_ROOT, "documents_triage_manifest.csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--documents-dir", default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--clean-dir", default=DEFAULT_CLEAN_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.manifest, newline="") as f:
        rows = list(csv.DictReader(f))

    approved = [r for r in rows if r["action"] == "include"]
    print(f"{len(approved)} of {len(rows)} manifest rows marked 'include'")

    copied = 0
    total_mb = 0.0
    edition_reminders = []

    for row in approved:
        src = os.path.join(args.documents_dir, row["filename"])
        dst = os.path.join(args.clean_dir, row["filename"])

        if not os.path.exists(src):
            print(f"  SKIP (source missing): {row['filename']}")
            continue
        if os.path.exists(dst):
            print(f"  SKIP (already in documents_clean): {row['filename']}")
            continue

        if not args.dry_run:
            shutil.copy2(src, dst)
        copied += 1
        total_mb += float(row.get("size_mb") or 0)
        print(f"  {'Would copy' if args.dry_run else 'Copied'}: {row['filename']}")

        if row["reason"].startswith("possible_newer_edition"):
            old_hint = row["reason"].split(":", 1)[1]
            edition_reminders.append((row["filename"], old_hint))

    print(f"\n{'Would copy' if args.dry_run else 'Copied'} {copied} files "
          f"({total_mb:.1f} MB) into {args.clean_dir}")

    if edition_reminders:
        print("\nManual follow-up — these were flagged as possible newer editions of "
              "an existing documents_clean file. The old file was NOT removed "
              "automatically; check both and remove the stale one by hand if the "
              "new one supersedes it:")
        for filename, old_hint in edition_reminders:
            print(f"  {filename}  (possible edition of: {old_hint})")


if __name__ == "__main__":
    main()
