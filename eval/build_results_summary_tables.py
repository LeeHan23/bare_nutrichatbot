"""Regenerate the side-by-side ground-truth/tested-answer sections (§4 RAG,
§5 extractor) of eval/results/EVAL_RESULTS_SUMMARY.md from the CASES
definitions in test_rag.py / test_extractor.py + the latest result JSONs.
No hand-typed rows.

Usage:
    python eval/build_results_summary_tables.py
"""
import ast
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_cases(path, stop_marker):
    src = open(path).read()
    start = src.index("CASES = [")
    end = src.index(stop_marker, start)
    mod = ast.parse(src[start:end])
    return ast.literal_eval(mod.body[0].value)


def last_run_meta(history_path):
    last = json.loads(open(history_path).readlines()[-1])
    return last["timestamp"][:10], last["git_commit"]


def cell(text, limit=600):
    if text is None:
        return ""
    text = str(text).replace("\n", " ").replace("|", "\\|").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def rag_ground_truth(case):
    parts = []
    cc = case.get("contraindication_check")
    if cc:
        stances = "/".join(s.upper() for s in cc["acceptable_stances"])
        parts.append(f"Stance must be {stances} for {cc['food']} given {cc['condition']}.")
    mc = case.get("myth_check")
    if mc:
        esc = " + must escalate to doctor/care team" if mc.get("must_escalate") else ""
        parts.append(f"Must REFUTE claim: \"{mc['claim']}\"{esc}.")
    pc = case.get("personalization_check")
    if pc:
        level = pc["level"] if isinstance(pc, dict) else "L3"
        parts.append(f"Must use {level}-appropriate caution/safety framing.")
    if case.get("voice_check"):
        parts.append("Second-person voice only, never the patient's name.")
    rt = case.get("required_terms")
    if rt:
        min_req = case.get("min_required", len(rt))
        parts.append(f"Must mention >= {min_req} of: {', '.join(rt)}.")
    ft = case.get("forbidden_terms")
    if ft:
        parts.append(f"Must NOT contain: {', '.join(ft)}.")
    if not parts:
        parts.append("(no automated check defined)")
    return " ".join(parts)


def build_rag_section():
    cases = {c["id"]: c for c in load_cases(f"{REPO}/eval/test_rag.py", "\ndef judge_stance")}
    results = json.load(open(f"{REPO}/eval/results/rag.json"))
    date, commit = last_run_meta(f"{REPO}/eval/results/rag_history.jsonl")
    meta = results["summary"]
    lines = [
        f"Most recent run: `eval/results/rag.json`, {date}, commit `{commit}` — "
        f"{meta['passed']}/{meta['total']} passed.",
        "",
        "| ID | Question | Ground Truth (expected) | Tested Answer (model output) | Result |",
        "|---|---|---|---|---|",
    ]
    for r in results["cases"]:
        case = cases.get(r["id"], {})
        q = cell(case.get("question", case.get("desc", "")), 200)
        gt = cell(rag_ground_truth(case))
        ans = cell(r.get("answer", ""))
        result = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(f"| {r['id']} | {q} | {gt} | {ans} | {result} |")
    return "\n".join(lines)


def build_extractor_section():
    cases = {c["id"]: c for c in load_cases(f"{REPO}/eval/test_extractor.py", "\ndef _check_field")}
    results = json.load(open(f"{REPO}/eval/results/extractor.json"))
    date, commit = last_run_meta(f"{REPO}/eval/results/extractor_history.jsonl")
    meta = results["summary"]
    lines = [
        f"Most recent run: `eval/results/extractor.json`, {date}, commit `{commit}` — "
        f"{meta['passed']}/{meta['total']} passed.",
        "",
        "| ID | Patient Message | Ground Truth (expected fields) | Tested Output (extracted fields) | Result |",
        "|---|---|---|---|---|",
    ]
    for r in results["cases"]:
        case = cases.get(r["id"], {})
        msg = cell(case.get("message", ""), 250)
        gt = cell(json.dumps(case.get("expected", {})), 400)
        got = cell(json.dumps(r.get("result", {})), 400)
        result = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(f"| {r['id']} | {msg} | {gt} | {got} | {result} |")
    return "\n".join(lines)


def splice_into_summary(rag_section, extractor_section):
    path = f"{REPO}/eval/results/EVAL_RESULTS_SUMMARY.md"
    content = open(path).read()

    start4 = content.index("## 4. Latest RAG run")
    header4 = "## 4. Latest RAG run — full case-by-case results (ground truth vs. tested answer)\n\n"

    start5 = content.index("## 5. Latest extractor run")
    header5 = "## 5. Latest extractor run — full case-by-case results (ground truth vs. tested output)\n\n"

    end5 = content.index("## 6. Nightly smoke suite")

    new_content = (
        content[:start4]
        + header4 + rag_section.strip() + "\n\n"
        + header5 + extractor_section.strip() + "\n\n"
        + content[end5:]
    )
    open(path, "w").write(new_content)


def demo():
    """Smoke check: run against the real repo files and assert row counts match the source JSON."""
    rag_section = build_rag_section()
    extractor_section = build_extractor_section()
    n_rag = len(json.load(open(f"{REPO}/eval/results/rag.json"))["cases"])
    n_ext = len(json.load(open(f"{REPO}/eval/results/extractor.json"))["cases"])
    assert rag_section.count("PASS |") + rag_section.count("FAIL |") == n_rag, "RAG row count mismatch"
    assert extractor_section.count("PASS |") + extractor_section.count("FAIL |") == n_ext, "extractor row count mismatch"
    print(f"demo OK: {n_rag} RAG rows, {n_ext} extractor rows")
    return rag_section, extractor_section


if __name__ == "__main__":
    rag_section, extractor_section = demo()
    splice_into_summary(rag_section, extractor_section)
    print("EVAL_RESULTS_SUMMARY.md §4/§5 regenerated.")
