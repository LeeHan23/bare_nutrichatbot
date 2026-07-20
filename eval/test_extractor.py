"""
Extractor regression tests — verifies extract_from_message() picks up the right
fields from patient messages in English, Bahasa Malaysia, and mixed input.

CLI usage:
    python eval/test_extractor.py                 # all 20 cases
    python eval/test_extractor.py --smoke         # 5 critical cases only (~2 min)
    python eval/test_extractor.py --out results/extractor.json
    python eval/test_extractor.py --case 3        # single case by index

Pytest usage (for local dev / CI):
    pytest eval/test_extractor.py -m smoke

Each test case specifies:
  message     : patient utterance
  expected    : dict of field → expected value (substring match for strings,
                subset check for lists, None means field must be absent)
  must_be_empty : if True, result must be {} (no extraction expected)
  tags        : smoke | en | bm | negative
"""

import os
import sys
import json
import time
import argparse

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractor import extract_from_message  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ─────────────────────────────────────────────────────────────────────────────

CASES = [
    # ── EN: fat intake & sources ──────────────────────────────────────────────
    {
        "id": 1, "tags": ["smoke", "en"],
        "desc": "High fat intake from palm oil and coconut milk",
        "message": "I fry everything in palm oil and add lots of coconut milk to my curries every day.",
        "expected": {
            "fat_intake_level": "high",
            "fat_sources": ["palm oil"],  # coconut milk may or may not be extracted (partial ok)
        },
    },
    {
        "id": 2, "tags": ["en"],
        "desc": "Low fat intake with olive oil",
        "message": "I only cook with olive oil and mostly eat grilled fish and steamed vegetables.",
        "expected": {
            "fat_intake_level": "low",
            "fat_sources": ["olive oil"],
        },
    },
    {
        "id": 3, "tags": ["en"],
        "desc": "High fat from butter and ghee",
        "message": "I use butter and ghee daily when I cook.",
        "expected": {
            "fat_intake_level": "high",
            "fat_sources": ["butter", "ghee"],
        },
    },

    # ── EN: medication compliance ─────────────────────────────────────────────
    {
        "id": 4, "tags": ["smoke", "en"],
        "desc": "Variable medication compliance",
        "message": "I forgot to take my blood pressure medication twice this week.",
        "expected": {"medication_compliance": "variable"},
    },
    {
        "id": 5, "tags": ["en"],
        "desc": "Poor medication compliance",
        "message": "Honestly I stopped taking my statin about a month ago, I don't like side effects.",
        "expected": {"medication_compliance": "poor"},
    },
    {
        "id": 6, "tags": ["en"],
        "desc": "Good medication compliance",
        "message": "I take all my tablets every morning without fail — I never miss a dose.",
        "expected": {"medication_compliance": "good"},
    },

    # ── EN: activity ──────────────────────────────────────────────────────────
    {
        "id": 7, "tags": ["smoke", "en"],
        "desc": "Walking 30 min daily",
        "message": "I go for a 30-minute brisk walk every morning.",
        "expected": {
            "activity_types": ["walking"],
            "activity_freq": "daily",
            "activity_minutes": 30,
        },
    },
    {
        "id": 8, "tags": ["en"],
        "desc": "Multiple activity types",
        "message": "I cycle to work on weekdays and swim on Saturday mornings.",
        "expected": {
            "activity_types": ["cycling", "swimming"],
        },
    },

    # ── EN: food allergies ────────────────────────────────────────────────────
    {
        "id": 9, "tags": ["en"],
        "desc": "Shellfish and nut allergy",
        "message": "I'm allergic to shellfish and tree nuts — I break out in hives.",
        "expected": {
            "extractor_food_allergies": ["shellfish", "nuts"],
        },
    },

    # ── EN: tobacco ───────────────────────────────────────────────────────────
    {
        "id": 10, "tags": ["en"],
        "desc": "Current smoker",
        "message": "I smoke about half a pack a day, have been doing it for 20 years.",
        "expected": {"tobacco_status": "Current smoker"},
    },
    {
        "id": 11, "tags": ["en"],
        "desc": "Former smoker",
        "message": "I quit smoking 5 years ago.",
        "expected": {"tobacco_status": "Former smoker"},
    },

    # ── EN: supplements ───────────────────────────────────────────────────────
    {
        "id": 12, "tags": ["en"],
        "desc": "Fish oil and vitamin D",
        "message": "I take fish oil and vitamin D every day.",
        "expected": {"supplements": ["fish oil", "vitamin d"]},
    },

    # ── BM: fat intake ────────────────────────────────────────────────────────
    {
        "id": 13, "tags": ["smoke", "bm"],
        "desc": "BM: high fat from nasi lemak and santan",
        "message": "Saya makan nasi lemak dengan banyak santan setiap pagi.",
        "expected": {
            "fat_intake_level": "high",
            "fat_sources": ["coconut milk"],  # extractor normalises santan → coconut milk
        },
    },

    # ── BM: medication compliance ─────────────────────────────────────────────
    {
        "id": 14, "tags": ["bm"],
        "desc": "BM: variable compliance — forget sometimes",
        "message": "Kadang-kadang saya lupa ambil ubat darah tinggi saya.",
        "expected": {"medication_compliance": "variable"},
    },

    # ── BM: food allergies ────────────────────────────────────────────────────
    {
        "id": 15, "tags": ["bm"],
        "desc": "BM: shellfish allergy",
        "message": "Saya alah dengan udang dan ketam, kalau makan terus gatal.",
        "expected": {
            "extractor_food_allergies": ["udang", "ketam"],
        },
    },

    # ── BM: tobacco ───────────────────────────────────────────────────────────
    {
        "id": 16, "tags": ["bm"],
        "desc": "BM: never smoked",
        "message": "Saya tak pernah merokok langsung.",
        "expected": {"tobacco_status": "Never smoked"},
    },

    # ── BM: activity ─────────────────────────────────────────────────────────
    {
        "id": 17, "tags": ["bm"],
        "desc": "BM: badminton twice a week",
        "message": "Saya main badminton dua kali seminggu, lebih kurang 45 minit.",
        "expected": {
            "activity_types": ["badminton"],
            "activity_minutes": 45,
        },
    },

    # ── Mixed (Manglish) ──────────────────────────────────────────────────────
    {
        "id": 18, "tags": ["en"],
        "desc": "Manglish: sometimes miss meds + coconut oil",
        "message": "Aiyah, sometimes I forget lah my medication. Also I cook with coconut oil every day.",
        "expected": {
            "medication_compliance": "variable",
            "fat_sources": ["coconut oil"],
        },
    },

    # ── Negative: no clinical info ────────────────────────────────────────────
    {
        "id": 19, "tags": ["smoke", "negative"],
        "desc": "Generic question — nothing to extract",
        "message": "What foods are good for my heart?",
        "must_be_empty": True,
        "expected": {},
    },
    {
        "id": 20, "tags": ["negative"],
        "desc": "Greeting — nothing to extract",
        "message": "Good morning! How are you today?",
        "must_be_empty": True,
        "expected": {},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# ASSERTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _check_field(result: dict, field: str, expected) -> tuple[bool, str]:
    """Returns (passed, reason)."""
    if expected is None:
        # Field must be absent
        if field in result:
            return False, f"{field}: expected absent, got {result[field]!r}"
        return True, ""

    if field not in result:
        return False, f"{field}: missing from result"

    actual = result[field]

    if isinstance(expected, list):
        # Subset check — all expected items must appear (case-insensitive)
        actual_lower = [str(x).lower() for x in (actual if isinstance(actual, list) else [actual])]
        missing = [e for e in expected if not any(e.lower() in a for a in actual_lower)]
        if missing:
            return False, f"{field}: missing items {missing!r} from {actual!r}"
        return True, ""

    if isinstance(expected, int):
        if actual != expected:
            return False, f"{field}: expected {expected}, got {actual!r}"
        return True, ""

    # String — check substring (covers allowed_values exact match and partial)
    if str(expected).lower() not in str(actual).lower():
        return False, f"{field}: expected {expected!r} in {actual!r}"
    return True, ""


def run_case(case: dict) -> dict:
    t0 = time.time()
    result = extract_from_message(case["message"], {})
    elapsed = time.time() - t0

    failures = []

    if case.get("must_be_empty"):
        if result:
            failures.append(f"expected empty dict, got {result}")
    else:
        for field, expected in case["expected"].items():
            passed, reason = _check_field(result, field, expected)
            if not passed:
                failures.append(reason)

    return {
        "id": case["id"],
        "desc": case["desc"],
        "tags": case.get("tags", []),
        "passed": len(failures) == 0,
        "failures": failures,
        "result": result,
        "elapsed_s": round(elapsed, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PYTEST ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
# Wraps each CASES entry as its own parametrized pytest test (see
# eval/test_rag.py for the same pattern). Cases tagged "smoke" get the
# `smoke` marker for `pytest eval/test_extractor.py -m smoke`.

try:
    import pytest

    def _case_id(case: dict) -> str:
        return f"{case['id']:02d}_{case['desc'][:40].replace(' ', '_')}"

    def _pytest_params():
        for case in CASES:
            marks = [pytest.mark.smoke] if "smoke" in case.get("tags", []) else []
            yield pytest.param(case, marks=marks, id=_case_id(case))

    @pytest.mark.parametrize("case", list(_pytest_params()))
    def test_case(case):
        result = run_case(case)
        assert result["passed"], "; ".join(result["failures"]) or "unknown failure"

except ImportError:
    pass  # pytest not installed — CLI runner below still works standalone


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only smoke-tagged cases")
    parser.add_argument("--case", type=int, help="Run a single case by id")
    parser.add_argument("--out", default=None, help="Write JSON results to file")
    parser.add_argument("--tag", default=None, help="Filter by tag (en, bm, negative, ...)")
    args = parser.parse_args()

    cases = CASES
    if args.smoke:
        cases = [c for c in cases if "smoke" in c["tags"]]
    elif args.case:
        cases = [c for c in cases if c["id"] == args.case]
    elif args.tag:
        cases = [c for c in cases if args.tag in c["tags"]]

    print(f"\nRunning {len(cases)} extractor test(s)...\n")
    results = []
    passed = failed = 0

    for case in cases:
        print(f"  [{case['id']:02d}] {case['desc'][:55]:<55} ", end="", flush=True)
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

    total = passed + failed
    print(f"\n{'─'*60}")
    print(f"Result: {passed}/{total} passed", "✓" if failed == 0 else f"  ({failed} failed)")

    if args.out:
        os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump({"summary": {"passed": passed, "failed": failed, "total": total},
                       "cases": results}, f, indent=2)
        print(f"Results written to {args.out}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
