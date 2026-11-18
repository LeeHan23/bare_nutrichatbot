"""
Add (or refresh) one clinical-review tab on eval.computationalrd.com holding
every case a fine-tune candidate FAILED in a given eval run.

Writes only judges[<key>] in data/judge_calibration_cases.json, leaving the
four judge-calibration tabs alone. Reviews live in eval_review_store under
"<key>:<case id>", so re-running this (e.g. once a same-day baseline lands)
keeps every review already submitted. Needs `sudo systemctl restart eval`,
since eval_api.py loads the cases file at import.

    .venv/bin/python scripts/add_finetune_review_tab.py \
        --key v3_review --title "Fine-tune v3 failures (2026-10-21)" \
        --candidate eval/results/rag_candidate_v3_2026-10-21.json \
        --runs "Baseline 10-18=eval/results/rag.json" \
               "v3 10-19=eval/results/rag_candidate_v3.json" \
               "v3 10-21=eval/results/rag_candidate_v3_2026-10-21.json"
"""
import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "scripts"))

import build_judge_calibration_app as b  # noqa: E402  (also puts eval/ on sys.path)

CASES_PATH = os.path.join(_PROJECT_ROOT, "data", "judge_calibration_cases.json")
TERMS_VERDICTS = ["ACCEPTABLE", "NEEDS FIX"]


def primary_check(case: dict, failures: list):
    """The judge whose check failed; else the first one the case has; else None
    (required-terms-only cases)."""
    present = [f for f in b.JUDGE_CONFIG if case.get(f)]
    for field in present:
        if any(x.startswith(b.JUDGE_CONFIG[field]["failure_prefix"]) for x in failures):
            return field
    return present[0] if present else None


def build_tab(key, title, candidate, runs, ids=None):
    cand = b.index_by_id(b.load_results([candidate])[0])
    labels = [label for label, _ in runs]
    indexed = [b.index_by_id(r) for r in b.load_results([path for _, path in runs])]
    cases_out = []
    for case in b.test_rag.CASES:
        entry = cand.get(case["id"])
        if not entry or entry["passed"] or (ids and case["id"] not in ids):
            continue
        failures = entry.get("failures", [])
        field = primary_check(case, failures)
        if field:
            claim = b.claim_section(case, field)
            options = b.JUDGE_CONFIG[field]["verdict_options"]
            reason = next((x.split("GEval judge: ", 1)[-1] for x in failures
                           if x.startswith(b.JUDGE_CONFIG[field]["failure_prefix"])), None)
        else:
            claim = {"kind": "terms"}
            options = TERMS_VERDICTS
            reason = None
        consistency = b.consistency_for(case["id"], indexed)
        cases_out.append({
            "id": case["id"],
            "desc": case["desc"],
            "tags": case.get("tags", []),
            "patient": b.patient_line(case),
            "question": b.question_text(case),
            "claim": claim,
            "verdict_options": options,
            "consistency": consistency,
            "classification": b.classify(consistency),
            "judge_verdict": "FAIL",
            "judge_reason": reason or "; ".join(failures),
            "answer": entry["answer"],
            "reviews": [],
        })
    intro = (f"Every case the fine-tuned candidate failed in {os.path.basename(candidate)}. "
             f"Dots, left to right: {', '.join(labels)}. "
             "Please judge whether the answer is clinically acceptable for this patient, "
             "say whether you agree with the automated FAIL, and note what the answer should say instead.")
    return {"key": key, "title": title, "verdict_options": TERMS_VERDICTS,
            "has_reasoning": True, "intro": intro, "cases": cases_out}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--runs", nargs="+", required=True, help='"label=path" in display order')
    p.add_argument("--ids", type=int, nargs="+", help="only these failed case ids")
    args = p.parse_args()
    runs = [tuple(r.split("=", 1)) for r in args.runs]
    assert all(len(r) == 2 for r in runs), "--runs entries must be label=path"

    tab = build_tab(args.key, args.title, args.candidate, runs, args.ids)
    with open(CASES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data["judges"][args.key] = tab
    with open(CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"{args.key}: {len(tab['cases'])} cases -> {CASES_PATH}: {[c['id'] for c in tab['cases']]}")


if __name__ == "__main__":
    main()
