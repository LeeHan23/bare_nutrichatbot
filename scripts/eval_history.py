"""
eval_history.py

Appends a summary row (date, git commit, passed/failed counts, per-tag
category breakdown) to a JSONL history log, given a results JSON file
produced by `eval/test_rag.py --out ...` or `eval/test_extractor.py --out ...`.

Why this exists: those scripts' --out flag overwrites a single results file
each run (eval/results/rag.json, eval/results/extractor.json) with no
history, so there's no way to tell whether a CLaRa/Qwen model update or a
prompt change made answer quality better or worse over time. This script
turns each run into one more row in an append-only log instead.

Usage:
    python eval/test_rag.py --out eval/results/rag.json
    python scripts/eval_history.py --results eval/results/rag.json --suite rag

    python eval/test_extractor.py --out eval/results/extractor.json
    python scripts/eval_history.py --results eval/results/extractor.json --suite extractor

    # Custom history file location (default: <results_dir>/<suite>_history.jsonl)
    python scripts/eval_history.py --results eval/results/rag.json --suite rag \\
        --history eval/results/rag_history.jsonl
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone


def get_git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def category_breakdown(cases: list) -> dict:
    """Pass/fail counts per tag, across all cases (a case may have multiple tags)."""
    breakdown = {}
    for case in cases:
        tags = case.get("tags") or ["untagged"]
        passed = case.get("passed", False)
        for tag in tags:
            entry = breakdown.setdefault(tag, {"passed": 0, "failed": 0})
            entry["passed" if passed else "failed"] += 1
    return breakdown


def main():
    parser = argparse.ArgumentParser(
        description="Append an eval run's summary to a JSONL history log"
    )
    parser.add_argument("--results", required=True, help="Path to the results JSON produced by --out")
    parser.add_argument("--suite", required=True, help="Suite name, e.g. rag / extractor")
    parser.add_argument(
        "--history",
        default=None,
        help="Path to the JSONL history log (default: <results_dir>/<suite>_history.jsonl)",
    )
    args = parser.parse_args()

    with open(args.results) as f:
        data = json.load(f)

    summary = data.get("summary", {})
    cases = data.get("cases", [])

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "suite": args.suite,
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "total": summary.get("total"),
        "category_breakdown": category_breakdown(cases),
    }

    history_path = args.history or os.path.join(
        os.path.dirname(args.results) or ".", f"{args.suite}_history.jsonl"
    )
    with open(history_path, "a") as f:
        f.write(json.dumps(row) + "\n")

    print(
        f"Appended {args.suite} run ({row['passed']}/{row['total']} passed, "
        f"commit {row['git_commit']}) to {history_path}"
    )


if __name__ == "__main__":
    main()
