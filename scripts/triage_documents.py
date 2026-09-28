"""
Triage /home/han/Desktop/projects/documents against the existing documents_clean
corpus before merging: dedup (internal + cross-dir, by MD5) and keyword-filter
down to the cardiac/metabolic-relevant subset.

What this does:
  - Flags internal duplicates within documents/ (same content, different filename)
  - Flags exact duplicates of files already in documents_clean/
  - Flags likely different-edition pairs of a few known titles for human review
  - Classifies the rest as include / exclude by filename keyword signal
  - Writes one CSV manifest for a human to review/edit before anything is copied

What this does NOT do:
  - Copy any files (see copy_approved_documents.py)
  - Touch documents_clean/ or documents/ in any way
  - Auto-resolve edition pairs or keyword-ambiguous files — those are left for
    a human to decide by editing the output CSV's `action` column
"""
import argparse
import csv
import hashlib
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DOCUMENTS_DIR = "/home/han/Desktop/projects/documents"
DEFAULT_CLEAN_DIR = "/home/han/Desktop/projects/documents_clean"
DEFAULT_OUT = os.path.join(_PROJECT_ROOT, "documents_triage_manifest.csv")

# Extensions out of scope this round (structured data / images) — never text-ingestible
# via the PDF/docx pipeline, so they're excluded outright rather than sent through
# keyword triage.
OUT_OF_SCOPE_EXTS = {".xlsx", ".xls", ".pptx", ".jpg", ".jpeg", ".png"}

# Already tracked byte-identical elsewhere in this repo (data/encpt/) — not new content.
KNOWN_REPO_DUPES = {"709438925-eNCPT-2020-lengkap.txt"}

# Org-prefix alone (this corpus's whole naming convention — MOH CPG, AND, ASPEN,
# ESPEN...) is NOT a topic signal — a "CPG Management of Multiple Sclerosis" is
# just as much a "cpg" match as a CKD one. These only elevate an otherwise-unmatched
# file to review_manually, they never auto-include by themselves.
ORG_PREFIX_PATTERNS = ["cpg", "mnt", "and", "eal", "aspen", "espen"]

# Condition keywords are what actually drives auto-include.
INCLUDE_PATTERNS = [
    "ckd", "renal", "kidney", "dialysis", "nephro",
    "dyslipid", "lipid", "cholesterol",
    "diabe", "dm2", "t2dm", "glycemic", "glycaemic",
    "obes", "weight",
    "hypertens", "blood pressure", "hipertensi",
    "heart fail", "cardiac", "cvd", "cardiovascular",
]

EXCLUDE_PATTERNS = [
    "paediat", "pediat", "child", "infant", "neonat", "kids", "cerebral palsy",
    "oncol", "cancer", "kanser", "carcinoma",
    "hepat", "liver", "cirrhosis", "gastro",
    "eating disorder", "anorexia", "bulimia",
    "sport", "athlet",
    "hiv", "aids",
    "wound", "pressure ulcer", "perioperative",
    "lecture", "slide",
    "copd", "pulmonary", "respiratory", "pneumonia",
    "parkinson", "arthrit", "gout", "rheumat",
    "cystic fibrosis",
    "ibs", "irritable bowel", "bowel", "ileostom", "stoma", "ostomy", "fodmap",
    "pancrea", "transplant", "thalassem",
    "bipolar", "dementia", "depressive", "schizophrenia", "psychiat",
]

# Known same-guideline-different-edition title fragments (not byte-identical, so MD5
# dedup won't catch these) — surfaced for a human "keep old / take new edition" call.
EDITION_FRAGMENTS = [
    "malaysia dietary guideline",
    "management of obesity",
    "management of hypertension",
    "ischaemic stroke",
]

# "and"/"eal" are org-acronym prefixes (Academy of Nutrition and Dietetics / Evidence
# Analysis Library) in this corpus's naming convention, always at the start of the
# filename — but as plain substrings they also match the English word "and" (e.g.
# "Children and Adolescents") and "eal" inside "Nasopharyngeal". Restrict these two
# to a filename-start match so they only fire on the real acronym.
PREFIX_ONLY_PATTERNS = {"and", "eal"}


def compute_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(directory: str) -> list:
    return sorted(
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")
    )


def classify_filename(filename: str) -> tuple:
    """Pure function: filename -> (action, reason). Assumes the file already
    survived extension-scope and dedup checks."""
    lower = filename.lower()

    for fragment in EDITION_FRAGMENTS:
        if fragment in lower:
            return "review_edition", f"possible_newer_edition:{fragment}"

    for pat in EXCLUDE_PATTERNS:
        if pat in lower:
            return "skip_out_of_scope_topic", f"hard_exclude:{pat}"

    for pat in INCLUDE_PATTERNS:
        if pat in lower:
            return "include", f"condition_match:{pat}"

    for pat in ORG_PREFIX_PATTERNS:
        if pat in PREFIX_ONLY_PATTERNS:
            matched = any(lower.startswith(pat + sep) for sep in (" ", "_", "-"))
        else:
            matched = pat in lower
        if matched:
            return "review_manually", f"org_prefix_no_topic_match:{pat}"

    return "review_manually", "no_keyword_signal"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents-dir", default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--clean-dir", default=DEFAULT_CLEAN_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--self-test", action="store_true", help="run assert-based checks and exit")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test OK")
        return

    documents_files = list_files(args.documents_dir)
    clean_files = list_files(args.clean_dir)
    print(f"documents/: {len(documents_files)} files, documents_clean/: {len(clean_files)} files")

    clean_hashes = {
        compute_md5(os.path.join(args.clean_dir, f)): f for f in clean_files
    }

    rows = []
    seen_hash_kept = {}  # md5 -> filename already kept as the canonical copy in documents/

    for filename in documents_files:
        path = os.path.join(args.documents_dir, filename)
        ext = os.path.splitext(filename)[1].lower()

        if filename in KNOWN_REPO_DUPES:
            rows.append((filename, "", 0.0, "skip_already_in_repo", "duplicate_of_repo_file"))
            continue
        if ext in OUT_OF_SCOPE_EXTS:
            rows.append((filename, "", 0.0, "skip_out_of_scope_ext", f"extension:{ext}"))
            continue

        size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
        md5 = compute_md5(path)

        if md5 in seen_hash_kept:
            rows.append((filename, md5, size_mb, "skip_internal_dup",
                         f"internal_duplicate_of:{seen_hash_kept[md5]}"))
            continue

        if md5 in clean_hashes:
            rows.append((filename, md5, size_mb, "skip_cross_dup",
                         f"exact_duplicate_of:{clean_hashes[md5]}"))
            seen_hash_kept[md5] = filename
            continue

        seen_hash_kept[md5] = filename
        action, reason = classify_filename(filename)
        rows.append((filename, md5, size_mb, action, reason))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "md5", "size_mb", "action", "reason"])
        writer.writerows(rows)

    counts = {}
    for row in rows:
        counts[row[3]] = counts.get(row[3], 0) + 1
    print(f"\nWrote {len(rows)} rows to {args.out}")
    for action, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {action:<25} {n}")
    print("\nReview rows with action 'review_manually' / 'review_edition' and edit "
          "the CSV's action column (to 'include' or 'skip') before running "
          "copy_approved_documents.py.")


def _self_test():
    assert classify_filename("CPG MOH - Management of Dyslipidemia 2017.pdf")[0] == "include"
    assert classify_filename("ESPGHAN paediatric parenteral nutrition - Lipids.pdf")[0] == "skip_out_of_scope_topic"
    assert classify_filename("Malaysia Dietary Guideline 2020.pdf")[0] == "review_edition"
    assert classify_filename("Some Random Slide Deck.pdf")[0] == "skip_out_of_scope_topic"
    assert classify_filename("Totally Unrelated Title.pdf")[0] == "review_manually"
    # exclude wins even when an include keyword is also present
    assert classify_filename("ESPEN CKD in Paediatric Patients.pdf")[0] == "skip_out_of_scope_topic"
    # "and"/"eal" only match as a filename-start org prefix, not as substrings
    assert classify_filename("QR - Nasopharyngeal Carcinoma.pdf")[0] == "skip_out_of_scope_topic"
    # org prefix alone (no condition keyword) is a review call, not auto-include
    assert classify_filename("AND - Multiple Sclerosis Guideline.pdf")[0] == "review_manually"
    assert classify_filename("CPG Management of Multiple Sclerosis 2015.pdf")[0] == "review_manually"
    # condition keyword always auto-includes, org prefix or not
    assert classify_filename("AND - Dyslipidaemia Guideline.pdf")[0] == "include"
    assert classify_filename("EAL Renal Nutrition Recommendations.pdf")[0] == "include"


if __name__ == "__main__":
    main()
