"""
RAG pipeline regression tests — verifies get_rag_response() produces clinically
correct, well-voiced answers for representative cardiac nutrition questions.

Tests cover:
  - Clinical accuracy  : answer contains expected clinical terms
  - Voice correctness  : second-person mode never uses patient name
  - Personalization    : L3 patients get medically-supervised-only advice
  - CKD retrieval      : CKD patients get potassium/phosphorus guidance

Usage:
    python eval/test_rag.py                       # all 10 cases (~8-15 min)
    python eval/test_rag.py --smoke               # 4 critical cases (~4 min)
    python eval/test_rag.py --case 2              # single case by id
    python eval/test_rag.py --out results/rag.json
    python eval/test_rag.py --patient 2           # all cases for patient 2

Results are also printed in a human-readable table for dietitian review.
"""

import os
import sys
import json
import time
import argparse

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rag import get_rag_response          # noqa: E402
from database import SessionLocal, patient_to_profile_dict, Patient  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ─────────────────────────────────────────────────────────────────────────────
# required_terms: response must contain AT LEAST min_required of these (case-insensitive)
# forbidden_terms: response must contain NONE of these
# voice_check: if True, verify answer uses "you"/"your" and omits patient name
# personalization_check: if True, verify L3 restriction language is present

CASES = [
    {
        "id": 1, "tags": ["smoke", "ckd"],
        "desc": "CKD+HTN: foods to avoid",
        "patient_id": 2,
        "question": "What should I avoid eating?",
        "is_patient_self": True,
        "required_terms": ["potassium", "phosphorus", "sodium", "fluid"],
        "min_required": 3,
        "forbidden_terms": ["Lim Siew Ching", "the patient", "she should"],
        "voice_check": True,
    },
    {
        "id": 2, "tags": ["smoke", "ckd"],
        "desc": "CKD+HTN: can I eat bananas?",
        "patient_id": 2,
        "question": "Can I eat bananas?",
        "is_patient_self": True,
        "required_terms": ["potassium", "avoid", "limit", "kidney"],
        "min_required": 2,
        "forbidden_terms": ["Lim Siew Ching"],
        "voice_check": True,
    },
    {
        "id": 3, "tags": ["smoke", "dm"],
        "desc": "T2DM+HTN: can I eat white rice?",
        "patient_id": 1,
        "question": "Can I eat white rice?",
        "is_patient_self": True,
        "required_terms": ["carbohydrate", "carbs", "portion", "glycemic", "blood sugar", "limit"],
        "min_required": 2,
        "forbidden_terms": ["Ahmad Fadzillah"],
        "voice_check": True,
    },
    {
        "id": 4, "tags": ["smoke", "personalization"],
        "desc": "L3 Post-CABG+HF: can I exercise? (must require supervision)",
        "patient_id": 11,
        "question": "Can I start exercising?",
        "is_patient_self": True,
        "required_terms": ["supervised", "supervision", "doctor", "cardiac rehab", "medical"],
        "min_required": 1,
        "forbidden_terms": ["you can start jogging", "vigorous"],
        "personalization_check": True,
    },
    {
        "id": 5, "tags": ["cholesterol"],
        "desc": "HTN+Hypercholesterol+T2DM: cooking oil",
        "patient_id": 5,
        "question": "What cooking oil should I use?",
        "is_patient_self": True,
        "required_terms": ["olive", "canola", "saturated", "trans fat", "avoid", "limit"],
        "min_required": 2,
        "forbidden_terms": ["Tan Wei Loong"],
        "voice_check": True,
    },
    {
        "id": 6, "tags": ["pcos"],
        "desc": "PCOS+IR: foods for insulin resistance",
        "patient_id": 3,
        "question": "What foods help with insulin resistance?",
        "is_patient_self": True,
        "required_terms": ["fibre", "fiber", "whole grain", "glycemic", "low GI", "vegetable"],
        "min_required": 2,
        "forbidden_terms": ["Kavitha"],
        "voice_check": True,
    },
    {
        "id": 7, "tags": ["obesity"],
        "desc": "Dyslipidaemia+Obesity: portion control",
        "patient_id": 4,
        "question": "How much should I eat per day?",
        "is_patient_self": True,
        "required_terms": ["calorie", "caloric", "portion", "weight", "serving"],
        "min_required": 2,
        "forbidden_terms": ["Mohd Hafizuddin"],
        "voice_check": True,
    },
    {
        "id": 8, "tags": ["wellness"],
        "desc": "L0 general wellness: healthy breakfast (no over-restriction)",
        "patient_id": 10,
        "question": "What is a healthy breakfast?",
        "is_patient_self": True,
        "required_terms": ["whole grain", "protein", "fibre", "fiber", "fruit", "vegetable"],
        "min_required": 2,
        "forbidden_terms": ["potassium restriction", "phosphorus limit", "dialysis"],
    },
    {
        "id": 9, "tags": ["voice"],
        "desc": "Voice test: second-person throughout",
        "patient_id": 1,
        "question": "Tell me what I should eat for breakfast.",
        "is_patient_self": True,
        "required_terms": ["you", "your"],
        "min_required": 2,
        "forbidden_terms": ["Ahmad Fadzillah", "the patient should", "he should"],
        "voice_check": True,
    },
    {
        "id": 10, "tags": ["ckd"],
        "desc": "CKD Stage 4 (P11): protein restriction guidance",
        "patient_id": 11,
        "question": "How much protein should I eat?",
        "is_patient_self": True,
        "required_terms": ["protein", "restrict", "limit", "kidney", "CKD", "g/kg"],
        "min_required": 2,
        "forbidden_terms": ["Rajendran"],
        "voice_check": True,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_profile(patient_id: int) -> dict | None:
    with SessionLocal() as s:
        p = s.query(Patient).filter_by(id=patient_id).first()
        if not p:
            return None
        return patient_to_profile_dict(p)


def check_terms(answer: str, required: list, min_required: int) -> tuple[bool, list, list]:
    """Returns (passed, found_terms, missing_terms)."""
    answer_lower = answer.lower()
    found = [t for t in required if t.lower() in answer_lower]
    missing = [t for t in required if t.lower() not in answer_lower]
    return len(found) >= min_required, found, missing


def check_forbidden(answer: str, forbidden: list) -> tuple[bool, list]:
    """Returns (clean, found_forbidden_terms)."""
    answer_lower = answer.lower()
    found = [t for t in forbidden if t.lower() in answer_lower]
    return len(found) == 0, found


def run_case(case: dict) -> dict:
    profile = load_profile(case["patient_id"])
    if not profile:
        return {"id": case["id"], "passed": False,
                "failures": [f"Patient {case['patient_id']} not found"], "answer": ""}

    t0 = time.time()
    result = get_rag_response(
        question=case["question"],
        client_id=profile.get("client_id", 4),
        chat_session_id=f"eval-{case['id']}-{int(t0)}",
        profile=profile,
        is_patient_self=case.get("is_patient_self", False),
    )
    elapsed = time.time() - t0
    answer = result.get("answer", "") if isinstance(result, dict) else str(result)

    failures = []

    # Required terms check
    required = case.get("required_terms", [])
    min_req = case.get("min_required", len(required))
    if required:
        passed_terms, found, missing = check_terms(answer, required, min_req)
        if not passed_terms:
            failures.append(
                f"Required terms: found {len(found)}/{min_req} minimum "
                f"(found={found}, missing={missing})"
            )

    # Forbidden terms check
    forbidden = case.get("forbidden_terms", [])
    if forbidden:
        clean, found_forbidden = check_forbidden(answer, forbidden)
        if not clean:
            failures.append(f"Forbidden terms found: {found_forbidden}")

    # Voice check: answer uses "you"/"your"
    if case.get("voice_check"):
        if "you" not in answer.lower() and "your" not in answer.lower():
            failures.append("Voice: answer does not use second-person 'you'/'your'")

    # Personalization check: L3 patient should see supervision/medical language
    if case.get("personalization_check"):
        supervision_terms = ["supervised", "supervision", "doctor", "medical", "cardiac rehab"]
        if not any(t in answer.lower() for t in supervision_terms):
            failures.append("Personalization: L3 patient answer missing supervision language")

    return {
        "id": case["id"],
        "desc": case["desc"],
        "patient_id": case["patient_id"],
        "passed": len(failures) == 0,
        "failures": failures,
        "answer": answer,
        "elapsed_s": round(elapsed, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only smoke-tagged cases")
    parser.add_argument("--case", type=int, help="Run a single case by id")
    parser.add_argument("--patient", type=int, help="Run all cases for a patient id")
    parser.add_argument("--tag", default=None, help="Filter by tag")
    parser.add_argument("--out", default=None, help="Write JSON results to file")
    parser.add_argument("--show-answers", action="store_true",
                        help="Print full answer text for each case")
    args = parser.parse_args()

    cases = CASES
    if args.smoke:
        cases = [c for c in cases if "smoke" in c["tags"]]
    elif args.case:
        cases = [c for c in cases if c["id"] == args.case]
    elif args.patient:
        cases = [c for c in cases if c["patient_id"] == args.patient]
    elif args.tag:
        cases = [c for c in cases if args.tag in c["tags"]]

    print(f"\nRunning {len(cases)} RAG test(s) (this may take a few minutes)...\n")
    results = []
    passed = failed = 0

    for case in cases:
        print(f"  [{case['id']:02d}] P{case['patient_id']} — {case['desc'][:50]:<50} ", end="", flush=True)
        r = run_case(case)
        results.append(r)

        if r["passed"]:
            passed += 1
            print(f"PASS  ({r['elapsed_s']}s)")
        else:
            failed += 1
            print(f"FAIL  ({r['elapsed_s']}s)")
            for f in r["failures"]:
                print(f"         ✗ {f}")

        if args.show_answers:
            print(f"\n         Answer: {r['answer'][:300]}...\n")

    total = passed + failed
    print(f"\n{'─'*65}")
    print(f"Result: {passed}/{total} passed", "✓" if failed == 0 else f"  ({failed} failed)")

    if failed > 0:
        print("\nFailed cases:")
        for r in results:
            if not r["passed"]:
                print(f"  [{r['id']:02d}] {r['desc']}")
                for f in r["failures"]:
                    print(f"       ✗ {f}")
                print(f"       Answer preview: {r['answer'][:200]}")

    if args.out:
        os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump({
                "summary": {"passed": passed, "failed": failed, "total": total},
                "cases": results,
            }, f, indent=2)
        print(f"\nFull results written to {args.out}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
