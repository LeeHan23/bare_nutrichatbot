"""
Add the three pre-v4 clinical review tabs to eval.computationalrd.com
(data/judge_calibration_cases.json), so the clinicians' answers can go into
the v4 fine-tune in one build:

  v4_anchors     scope examples already in finetune/data_mlx_v4 (base-model
                 answers the scope judge passed). APPROVE / NEEDS FIX.
  v4_scope_fix   questions whose live answer the scope judge rejected. Only
                 trained once a clinician marks ACCEPTABLE or writes the fix.
  stance_ruling  the 4 food/condition stances reviewers disputed. The ruling
                 replaces the eval's expected stance and the training target.

finetune/build_review_data.py --anchors <data dir>/scope_anchors.json reads
the verdicts back. Reviews live under "<tab>:<id>" in eval_review_store, so
re-running this keeps them. Needs `sudo systemctl restart eval`.

    .venv/bin/python scripts/add_v4_review_tabs.py
"""
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "scripts"))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "finetune"))

import build_judge_calibration_app as b  # noqa: E402  (also puts eval/ on sys.path)
import taxonomy  # noqa: E402

CASES_PATH = os.path.join(_PROJECT_ROOT, "data", "judge_calibration_cases.json")
ANCHORS_PATH = os.path.join(_PROJECT_ROOT, "finetune", "data_mlx_v4", "scope_anchors.json")
REVIEWS_PATH = os.path.join(_PROJECT_ROOT, "data", "eval_calibration_reviews.json")
LIVE_RUN = os.path.join(_PROJECT_ROOT, "eval", "results", "rag_nofood_noclara_2026-10-22.json")
STANCES = ["RESTRICT", "MODERATE", "PERMIT"]


def scope_claim(component, expected):
    scope = taxonomy.COMPONENT_SCOPE[component]
    return {"kind": "scope", "component": component,
            "component_label": taxonomy.COMPONENT_LABELS.get(component, component),
            "expected": expected, "in_scope": scope["in_scope"], "out_of_scope": scope["out_of_scope"]}


def anchor_card(a, verdicts):
    return {
        "id": a["id"],
        "desc": f"{taxonomy.COMPONENT_LABELS.get(a['component'], a['component'])}: "
                + ("general education" if a["expected"] == "GENERAL_EDUCATION" else "should defer to care team"),
        "tags": [a["component"]],
        "patient": b.patient_line({"id": a["id"], "patient_id": a["patient_id"]}),
        "question": a["question"],
        "claim": scope_claim(a["component"], a["expected"]),
        "verdict_options": verdicts,
        "consistency": [],
        "judge_verdict": "PASS" if a["status"] == "kept" else "FAIL",
        "judge_reason": a["judge_reason"],
        "answer": a["answer"],
        "reviews": [],
    }


def stance_tab():
    cases = {c["id"]: c for c in b.test_rag.CASES}
    live = b.index_by_id(b.load_results([LIVE_RUN])[0])
    with open(REVIEWS_PATH, encoding="utf-8") as f:
        reviews = json.load(f)
    rubric = b.JUDGE_CONFIG["contraindication_check"]["rubric"]
    out = []
    for key, rv in sorted(reviews.items(), key=lambda kv: int(kv[0].split(":")[1])):
        judge_key, cid = key.split(":")
        if judge_key != "stance":
            continue
        case = cases[int(cid)]
        check = case["contraindication_check"]
        rv = [r for r in rv if r.get("verdict")]
        if not any(r["verdict"].lower() not in check["acceptable_stances"] for r in rv):
            continue
        earlier = "; ".join(f"{r['reviewer']}: {r['verdict']}" + (f" (\"{r['notes'].strip()}\")" if r.get("notes", "").strip() else "")
                            for r in rv)
        out.append({
            "id": case["id"],
            "desc": f"{check['food']} / {check['condition']}",
            "tags": case.get("tags", []),
            "patient": b.patient_line(case),
            "question": b.question_text(case),
            "claim": {"kind": "stance", "food": check["food"], "condition": check["condition"],
                      "acceptable_stances": STANCES,
                      "acceptable_desc": [{"stance": s, "desc": rubric.get(s, "")} for s in STANCES]},
            "verdict_options": STANCES,
            "consistency": [],
            "judge_verdict": None,
            "judge_reason": f"The eval currently expects: {' or '.join(s.upper() for s in check['acceptable_stances'])}. "
                            f"Earlier reviews: {earlier}",
            "answer": live[case["id"]]["answer"],
            "reviews": [],
        })
    return out


def main():
    with open(ANCHORS_PATH, encoding="utf-8") as f:
        anchors = json.load(f)
    tabs = {
        "v4_anchors": {
            "title": "v4 training examples: sign-off (2026-10-22)",
            "verdict_options": ["APPROVE", "NEEDS FIX"],
            "notes_hint": "If NEEDS FIX: what is wrong, or what the reply should say. Leave blank to drop the example.",
            "intro": "These replies will be used to teach the fine-tuned model how to answer non-nutrition questions: "
                     "explain in general terms, or hand over to the care team. An automated judge has already passed each one. "
                     "Approve the ones you are happy for the model to copy. NEEDS FIX with a note gets rewritten from your note; "
                     "NEEDS FIX without a note is removed.",
            "cases": [anchor_card(a, ["APPROVE", "NEEDS FIX"]) for a in anchors if a["status"] == "kept"],
        },
        "v4_scope_fix": {
            "title": "Questions the bot answers poorly (2026-10-22)",
            "verdict_options": ["ACCEPTABLE", "NEEDS FIX"],
            "notes_hint": "If NEEDS FIX: write what the reply should say (this becomes the training example).",
            "intro": "Today's live bot answered these, and the automated judge said the reply oversteps "
                     "(e.g. gives dosing or a personal target) or misses the point. The judge may be too strict, so please check. "
                     "ACCEPTABLE means the reply is fine as it is, and it will be used for training. NEEDS FIX with a note "
                     "describing the correct reply gets rewritten from your note. Nothing here is trained until someone reviews it.",
            "cases": [anchor_card(a, ["ACCEPTABLE", "NEEDS FIX"]) for a in anchors if a["status"] == "rejected"],
        },
        "stance_ruling": {
            "title": "Stance rulings: 4 disputed foods (dietitian)",
            "verdict_options": STANCES,
            "notes_hint": "Reasoning, plus anything the reply must mention (e.g. a portion or a potassium-level condition).",
            "intro": "Reviewers disagreed with the eval's expected stance for these 4 food/condition pairs, so they are "
                     "currently left out of training in both directions. Please choose the stance the bot should take for "
                     "this patient. Your ruling becomes the eval's expected answer and the training target. The reply shown is "
                     "today's live bot.",
            "cases": stance_tab(),
        },
    }
    with open(CASES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for key, tab in tabs.items():
        data["judges"][key] = {"key": key, "has_reasoning": True, **tab}
        print(f"{key}: {len(tab['cases'])} cases {[c['id'] for c in tab['cases']]}")
    with open(CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
