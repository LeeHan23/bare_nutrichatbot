"""
compare_eval_runs.py

Compares two eval/test_rag.py (or test_extractor.py) --out results JSON
files -- typically a pre-fine-tune baseline and a post-fine-tune candidate
-- and reports per-case regressions/improvements, per-tag pass rates, and a
PROMOTE / DO NOT PROMOTE verdict.

This is the eval-side half of Part C's "gate the fine-tune with eval, both
ways" step (see docs/eval_and_roadmap.md): before merging a new LoRA adapter
into the production Ollama model, run the same expanded eval suite against
both the baseline and the fine-tuned candidate, then use this script to
decide whether the adapter actually helped its targeted failure categories
without breaking anything else. A candidate is only promotion-worthy if it
introduces zero regressions AND fixes at least one prior failure.

Usage:
    python eval/test_rag.py --out eval/results/rag_baseline.json
    # ... swap in the fine-tuned adapter, restart Ollama ...
    python eval/test_rag.py --out eval/results/rag_candidate.json
    python scripts/compare_eval_runs.py \\
        --baseline eval/results/rag_baseline.json \\
        --candidate eval/results/rag_candidate.json

Exit code is 0 if the candidate is promotion-worthy, 1 otherwise -- so this
can gate a CI/deploy step directly.
"""
import argparse
import json


def load_cases(path: str) -> dict:
    """Returns {case_id: case_dict}."""
    with open(path) as f:
        data = json.load(f)
    return {c["id"]: c for c in data.get("cases", [])}


def tag_pass_rate(cases: dict) -> dict:
    breakdown = {}
    for case in cases.values():
        tags = case.get("tags") or ["untagged"]
        passed = case.get("passed", False)
        for tag in tags:
            entry = breakdown.setdefault(tag, {"passed": 0, "total": 0})
            entry["total"] += 1
            if passed:
                entry["passed"] += 1
    return breakdown


def compare(baseline: dict, candidate: dict) -> dict:
    """Pure comparison logic, separated from CLI/printing so it's testable
    without needing real result files."""
    common_ids = sorted(set(baseline) & set(candidate))
    only_baseline = sorted(set(baseline) - set(candidate))
    only_candidate = sorted(set(candidate) - set(baseline))

    regressions = []   # passed -> failed
    improvements = []  # failed -> passed

    for cid in common_ids:
        b, c = baseline[cid], candidate[cid]
        if b.get("passed") and not c.get("passed"):
            regressions.append({"id": cid, "desc": b.get("desc", ""), "failures": c.get("failures", [])})
        elif not b.get("passed") and c.get("passed"):
            improvements.append({"id": cid, "desc": b.get("desc", "")})

    verdict_ok = bool(improvements) and not regressions

    return {
        "common_ids": common_ids,
        "only_baseline": only_baseline,
        "only_candidate": only_candidate,
        "regressions": regressions,
        "improvements": improvements,
        "verdict_ok": verdict_ok,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compare two eval result JSONs (baseline vs. candidate) to gate a fine-tune promotion"
    )
    parser.add_argument("--baseline", required=True, help="Path to the baseline (pre-fine-tune) results JSON")
    parser.add_argument("--candidate", required=True, help="Path to the candidate (post-fine-tune) results JSON")
    args = parser.parse_args()

    baseline = load_cases(args.baseline)
    candidate = load_cases(args.candidate)
    result = compare(baseline, candidate)

    print("=" * 70)
    print(f"EVAL COMPARISON: {args.baseline}  ->  {args.candidate}")
    print("=" * 70)
    print(f"Cases compared: {len(result['common_ids'])}", end="")
    if result["only_baseline"] or result["only_candidate"]:
        print(
            f"  (baseline-only: {len(result['only_baseline'])}, "
            f"candidate-only: {len(result['only_candidate'])} -- skipped in the diff below)"
        )
    else:
        print()

    print(f"\nRegressions (passed -> failed): {len(result['regressions'])}")
    for r in result["regressions"]:
        print(f"  [{r['id']:02d}] {r['desc']}")
        for f in r["failures"]:
            print(f"       - {f}")

    print(f"\nImprovements (failed -> passed): {len(result['improvements'])}")
    for i in result["improvements"]:
        print(f"  [{i['id']:02d}] {i['desc']}")

    print("\nPer-tag pass rate (baseline -> candidate):")
    b_tags = tag_pass_rate(baseline)
    c_tags = tag_pass_rate(candidate)
    for tag in sorted(set(b_tags) | set(c_tags)):
        bp = b_tags.get(tag, {"passed": 0, "total": 0})
        cp = c_tags.get(tag, {"passed": 0, "total": 0})
        print(f"  {tag:<20} {bp['passed']:>2}/{bp['total']:<3}  ->  {cp['passed']:>2}/{cp['total']:<3}")

    print("\n" + "=" * 70)
    if result["regressions"]:
        print(f"VERDICT: DO NOT PROMOTE -- {len(result['regressions'])} regression(s) introduced.")
    elif not result["improvements"]:
        print("VERDICT: DO NOT PROMOTE -- no improvements over baseline (nothing gained).")
    else:
        print(f"VERDICT: PROMOTE -- {len(result['improvements'])} improvement(s), 0 regressions.")
    print("=" * 70)

    return 0 if result["verdict_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
