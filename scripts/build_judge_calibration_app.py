"""
Generate the seed data + self-contained HTML for the multi-judge calibration
web app (an Artifact with the `artifact` capability — the page republishes
itself with updated review data on every submission).

Covers all 4 LLM judges in eval/test_rag.py:
  - judge_myth_handling()    (myth_check)
  - judge_stance()           (contraindication_check)
  - judge_personalization()  (personalization_check — no reasoning text,
    unlike the others; the page says so explicitly)
  - judge_scope_adherence()  (scope_check — non-nutrition Component questions;
    9 of the 10 Components have no grounded retrieval content, so this judge
    verifies the prompt's Component Scope block is actually doing its job)

For each judge: pulls candidate cases from CASES, computes PASS/FAIL
consistency across the given result JSONs (same code+question, different
generation each run — flip-flopping cases are the most diagnostic), and
selects ~10: up to 2 consistent-pass, up to 2 consistent-fail, the rest
flip-flop (or the whole pool if it's small, e.g. personalization's 11).

Also imports any already-filled reviews from eval/judge_calibration.md
(the hand-built myth sheet) as the page's first review entries.
"""
import argparse
import json
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "eval"))

import test_rag  # noqa: E402
import taxonomy  # noqa: E402

DEFAULT_RESULTS = [
    "eval/results/rag_post_merge.json",
    "eval/results/rag_structured_lookup.json",
    "eval/results/rag_full_with_structured_cases.json",
    "eval/results/rag_scope.json",
]
DEFAULT_MYTH_MD = "eval/judge_calibration.md"
DEFAULT_AI_PRELIMINARY = "eval/ai_preliminary_reviews.json"
DEFAULT_OUT = "eval/judge_calibration_app.html"

JUDGE_CONFIG = {
    "myth_check": {
        "key": "myth",
        "title": "Myth Handling",
        "verdict_options": ["REFUTE", "HEDGE", "ACCEPT"],
        "failure_prefix": "Myth handling (",
        "rubric": test_rag._MYTH_HANDLING_DESCRIPTIONS,
    },
    "contraindication_check": {
        "key": "stance",
        "title": "Contraindication Stance",
        "verdict_options": ["RESTRICT", "PERMIT", "MODERATE"],
        "failure_prefix": "Contraindication (",
        "rubric": test_rag._STANCE_DESCRIPTIONS,
    },
    "personalization_check": {
        "key": "personalization",
        "title": "Personalization Framing",
        "verdict_options": ["PASS", "FAIL"],
        "failure_prefix": "Personalization:",
        "rubric": None,
    },
    "scope_check": {
        "key": "scope",
        "title": "Component Scope Adherence",
        "verdict_options": ["GENERAL_EDUCATION", "DEFERRED", "OVERSTEPPED"],
        "failure_prefix": "Scope adherence (",
        "rubric": test_rag._SCOPE_VERDICT_DESCRIPTIONS,
    },
}


def load_results(paths: list) -> list:
    out = []
    for p in paths:
        full = os.path.join(_PROJECT_ROOT, p) if not os.path.isabs(p) else p
        with open(full) as f:
            out.append(json.load(f))
    return out


def index_by_id(result_json: dict) -> dict:
    return {c["id"]: c for c in result_json.get("cases", [])}


def candidates_for(check_field: str) -> list:
    return [c for c in test_rag.CASES if c.get(check_field)]


def consistency_for(case_id: int, indexed_list: list) -> list:
    out = []
    for idx in indexed_list:
        c = idx.get(case_id)
        out.append("N/A" if c is None else ("PASS" if c["passed"] else "FAIL"))
    return out


def classify(consistency: list) -> str:
    real = [c for c in consistency if c != "N/A"]
    if not real:
        return "no_data"
    if all(c == "PASS" for c in real):
        return "consistent_pass"
    if all(c == "FAIL" for c in real):
        return "consistent_fail"
    return "flipflop"


def select_cases(candidates: list, indexed_list: list, sample_size: int, force_ids: set = frozenset()) -> list:
    scored = []
    for case in candidates:
        cons = consistency_for(case["id"], indexed_list)
        scored.append((case, cons, classify(cons)))

    if sample_size <= 0 or sample_size >= len(scored):
        return scored

    # Cases that already have an imported review (e.g. from
    # judge_calibration.md) must survive sampling — dropping them would
    # silently discard a reviewer's existing work.
    forced = [item for item in scored if item[0]["id"] in force_ids]

    by_class = {"consistent_pass": [], "consistent_fail": [], "flipflop": [], "no_data": []}
    for item in scored:
        if item[0]["id"] in force_ids:
            continue
        by_class[item[2]].append(item)

    n_pass = min(2, len(by_class["consistent_pass"]))
    n_fail = min(2, len(by_class["consistent_fail"]))
    pass_pool = by_class["consistent_pass"][n_pass:]
    fail_pool = by_class["consistent_fail"][n_fail:]
    selected = forced + by_class["consistent_pass"][:n_pass] + by_class["consistent_fail"][:n_fail]

    n_flip = sample_size - len(selected)
    flip_pool = by_class["flipflop"]
    flip_selected = flip_pool[:max(n_flip, 0)]

    # Bilingual nudge: prefer at least one bilingual flip-flop case if one
    # exists and wasn't already picked (matches the myth sheet's manual
    # selection — the design doc specifically flags judge accuracy on BM
    # answers as a concern worth covering).
    has_bilingual = any("bilingual" in item[0].get("tags", []) for item in flip_selected)
    if not has_bilingual:
        bilingual_candidate = next(
            (item for item in flip_pool[n_flip:] if "bilingual" in item[0].get("tags", [])),
            None,
        )
        if bilingual_candidate and flip_selected:
            flip_selected[-1] = bilingual_candidate

    selected += flip_selected

    # Backfill: a freshly-added judge (only one result file covers it yet)
    # has no flip-flop data at all — without this, the sample would silently
    # shrink to just the 2+2 pass/fail cap instead of using the requested
    # sample_size. Pull more from the pass/fail pools instead, alternating
    # so one class doesn't dominate.
    remaining = sample_size - len(selected)
    backfill_pools = [pass_pool, fail_pool]
    i = 0
    while remaining > 0 and (backfill_pools[0] or backfill_pools[1]):
        pool = backfill_pools[i % 2]
        i += 1
        if pool:
            selected.append(pool.pop(0))
            remaining -= 1

    selected.sort(key=lambda item: item[0]["id"])
    return selected


def _most_recent_entry(case_id: int, indexed_list: list):
    """Scans backwards for the most recent result file that actually
    contains this case — not just indexed_list[-1], since a result file may
    cover only a subset of cases (e.g. a --tag-filtered run)."""
    for idx in reversed(indexed_list):
        if case_id in idx:
            return idx[case_id]
    return None


def representative_verdict(case_id: int, check_field: str, indexed_list: list):
    """Uses the most recent result file that contains this case."""
    prefix = JUDGE_CONFIG[check_field]["failure_prefix"]
    entry = _most_recent_entry(case_id, indexed_list)
    if entry is None:
        return None, None
    if entry["passed"]:
        return "PASS", None
    for f in entry.get("failures", []):
        if f.startswith(prefix):
            if "GEval judge: " in f:
                return "FAIL", f.split("GEval judge: ", 1)[1]
            return "FAIL", f
    return "FAIL", None


def patient_line(case: dict) -> str:
    try:
        profile = test_rag.load_profile(case["patient_id"], case.get("profile_overrides"))
        if not profile:
            raise ValueError("no profile")
        conditions = ", ".join(profile.get("condition", [])) or "no significant conditions"
        level = profile.get("personalization_level")
        level_str = f", {level}" if level else ""
        return f"P{case['patient_id']} — {conditions}{level_str}"
    except Exception as e:
        print(f"[build_judge_calibration_app] patient_line fallback for case {case['id']}: {e}", file=sys.stderr)
        return f"P{case['patient_id']}"


def claim_section(case: dict, check_field: str) -> dict:
    if check_field == "myth_check":
        mc = case["myth_check"]
        return {
            "kind": "myth",
            "claim": mc["claim"],
            "must_escalate": mc.get("must_escalate", False),
        }
    if check_field == "contraindication_check":
        cc = case["contraindication_check"]
        acceptable = cc.get("acceptable_stances", ["restrict"])
        rubric = JUDGE_CONFIG[check_field]["rubric"]
        return {
            "kind": "stance",
            "food": cc["food"],
            "condition": cc["condition"],
            "acceptable_stances": [s.upper() for s in acceptable],
            "acceptable_desc": [
                {"stance": s.upper(), "desc": rubric.get(s.upper(), "")} for s in acceptable
            ],
        }
    if check_field == "personalization_check":
        pc = case["personalization_check"]
        level = "L3" if pc is True else pc.get("level", "L3")
        return {
            "kind": "personalization",
            "level": level,
            "expected_framing": test_rag._LEVEL_EXPECTATION[level],
        }
    sc = case["scope_check"]
    scope = taxonomy.COMPONENT_SCOPE[sc["component"]]
    return {
        "kind": "scope",
        "component": sc["component"],
        "component_label": taxonomy.COMPONENT_LABELS.get(sc["component"], sc["component"]),
        "expected": sc["expected"],
        "in_scope": scope["in_scope"],
        "out_of_scope": scope["out_of_scope"],
    }


def question_text(case: dict) -> str:
    parts = []
    for turn in case.get("prior_turns", []):
        parts.append(f"[{turn['role']}] {turn['content']}")
    parts.append(f"[patient] {case.get('question', '')}")
    return "\n".join(parts)


_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|.*\|\s*([A-Za-z]+)\s*\|\s*([A-Za-z]+)?\s*\|\s*(.*?)\s*\|\s*$")


def parse_existing_myth_reviews(md_path: str) -> dict:
    """Parses eval/judge_calibration.md's '## Case N — ...' blocks for
    already-filled '**Your verdict**: X  **Agree with judge?**: Y  **Notes**: Z'
    lines. Blank fields (just underscores) are skipped."""
    full = os.path.join(_PROJECT_ROOT, md_path) if not os.path.isabs(md_path) else md_path
    if not os.path.exists(full):
        return {}
    text = open(full).read()
    reviews = {}
    # re.split with a capturing group interleaves [preamble, id, body, id, body, ...]
    parts = re.split(r"^## Case (\d+)", text, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        case_id = int(parts[i])
        body = parts[i + 1]
        m = re.search(
            r"\*\*Your verdict\*\*:\s*_*([A-Za-z]*)_*\s*"
            r"\*\*Agree with judge\?\*\*:\s*_*([A-Za-z]*)_*\s*"
            r"\*\*Notes\*\*:\s*_*(.*?)_*\s*$",
            body,
            re.MULTILINE,
        )
        if m and m.group(1).strip():
            reviews.setdefault(case_id, []).append({
                "reviewer": "imported from judge_calibration.md",
                "verdict": m.group(1).strip().upper(),
                "agree": m.group(2).strip().upper() or None,
                "notes": m.group(3).strip().rstrip("_").strip(),
            })
    return reviews


def parse_ai_preliminary_reviews(json_path: str) -> dict:
    """Parses eval/ai_preliminary_reviews.json — preliminary AI reads flagged
    for team verification (NOT a clinical sign-off), keyed by case id.
    Same {case_id: [review, ...]} shape as parse_existing_myth_reviews."""
    full = os.path.join(_PROJECT_ROOT, json_path) if not os.path.isabs(json_path) else json_path
    if not os.path.exists(full):
        return {}
    with open(full, encoding="utf-8") as f:
        data = json.load(f)
    reviews = {}
    for case_id_str, r in data.get("reviews", {}).items():
        reviews.setdefault(int(case_id_str), []).append({
            "reviewer": "Claude (preliminary AI read — needs team verification)",
            "verdict": r["verdict"],
            "agree": r.get("agree"),
            "notes": r.get("notes", ""),
        })
    return reviews


def merge_review_sources(*sources: dict) -> dict:
    """Combines several {case_id: [review, ...]} dicts into one, preserving
    all reviews per case rather than one source overwriting another."""
    merged = {}
    for source in sources:
        for case_id, reviews in source.items():
            merged.setdefault(case_id, []).extend(reviews)
    return merged


def build_judge_data(check_field: str, indexed_list: list, sample_size: int, imported_reviews: dict) -> dict:
    cfg = JUDGE_CONFIG[check_field]
    candidates = candidates_for(check_field)
    # Small pools (e.g. personalization's 11 cases) aren't worth sampling
    # down — use the whole pool rather than arbitrarily dropping a fifth of it.
    effective_sample_size = 0 if len(candidates) <= sample_size + 1 else sample_size
    force_ids = {case["id"] for case in candidates if case["id"] in imported_reviews}
    selected = select_cases(candidates, indexed_list, effective_sample_size, force_ids)

    cases_out = []
    for case, consistency, cls in selected:
        verdict, reason = representative_verdict(case["id"], check_field, indexed_list)
        reviews = list(imported_reviews.get(case["id"], []))
        cases_out.append({
            "id": case["id"],
            "desc": case["desc"],
            "tags": case.get("tags", []),
            "patient": patient_line(case),
            "question": question_text(case),
            "claim": claim_section(case, check_field),
            "consistency": consistency,
            "classification": cls,
            "judge_verdict": verdict,
            "judge_reason": reason,
            "answer": test_rag_answer_for(case["id"], indexed_list),
            "reviews": reviews,
        })

    return {
        "key": cfg["key"],
        "title": cfg["title"],
        "verdict_options": cfg["verdict_options"],
        "has_reasoning": check_field != "personalization_check",
        "cases": cases_out,
    }


def test_rag_answer_for(case_id: int, indexed_list: list) -> str:
    entry = _most_recent_entry(case_id, indexed_list)
    return entry["answer"] if entry else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", nargs="+", default=DEFAULT_RESULTS)
    parser.add_argument("--myth-md", default=DEFAULT_MYTH_MD)
    parser.add_argument("--ai-preliminary", default=DEFAULT_AI_PRELIMINARY)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--out-data", default=None, help="optional: also write the seed JSON standalone")
    args = parser.parse_args()

    indexed_list = [index_by_id(r) for r in load_results(args.results)]
    myth_md_reviews = parse_existing_myth_reviews(args.myth_md)
    ai_reviews = parse_ai_preliminary_reviews(args.ai_preliminary)
    imported_reviews = merge_review_sources(myth_md_reviews, ai_reviews)
    print(f"Imported {sum(len(v) for v in myth_md_reviews.values())} review(s) from {args.myth_md}: {list(myth_md_reviews.keys())}")
    print(f"Imported {sum(len(v) for v in ai_reviews.values())} AI-preliminary review(s) from {args.ai_preliminary}: {list(ai_reviews.keys())}")

    judges = {}
    for check_field in JUDGE_CONFIG:
        data = build_judge_data(check_field, indexed_list, args.sample_size, imported_reviews)
        judges[data["key"]] = data
        print(f"{check_field}: {len(data['cases'])} cases selected "
              f"({sum(1 for c in data['cases'] if c['classification']=='consistent_pass')} consistent-pass, "
              f"{sum(1 for c in data['cases'] if c['classification']=='consistent_fail')} consistent-fail, "
              f"{sum(1 for c in data['cases'] if c['classification']=='flipflop')} flip-flop)")

    seed = {"judges": judges}

    if args.out_data:
        with open(args.out_data, "w") as f:
            json.dump(seed, f, indent=2, ensure_ascii=False)
        print(f"Wrote seed data to {args.out_data}")

    # Print to stdout too so the caller can pipe/embed it
    print("---SEED_JSON_START---")
    print(json.dumps(seed, ensure_ascii=False))
    print("---SEED_JSON_END---")


if __name__ == "__main__":
    main()
