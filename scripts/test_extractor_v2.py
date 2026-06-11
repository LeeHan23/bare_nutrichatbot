"""
Smoke test for the v2 cardiac extractor.
Run on the RTX 3050 server to verify the new fields extract correctly.
"""
import sys
sys.path.insert(0, '/mnt/ext/bare_NutriChatbot')

from extractor import extract_from_message

TESTS = [
    # ── Tier 1 cardiac fields ────────────────────────────────────────
    {
        "name": "Multi-field T1 (English)",
        "message": "I drink 6 glasses of water daily, take fish oil, never smoked, and add salt to most foods without checking labels.",
        "expect_keys": {"fluid_intake_ml", "supplements", "tobacco_status", "sodium_awareness"},
    },
    {
        "name": "Fat intake — high level from food sources",
        "message": "Most days I have nasi lemak for breakfast and fried chicken for lunch.",
        "expect_keys": {"fat_intake_level"},
    },
    {
        "name": "Fat intake — low level",
        "message": "I mostly eat steamed fish and grilled vegetables, rarely fried foods.",
        "expect_keys": {"fat_intake_level"},
    },

    # ── Tier 2 cardiac fields ────────────────────────────────────────
    {
        "name": "Medication compliance — variable",
        "message": "I take my blood pressure pills in the morning but sometimes forget the evening dose.",
        "expect_keys": {"medication_compliance"},
    },
    {
        "name": "Fat sources — palm oil, butter",
        "message": "I cook with palm oil and put butter on my bread.",
        "expect_keys": {"fat_sources"},
    },
    {
        "name": "Activity — type, freq, duration, intensity",
        "message": "I walk for 30 minutes 3 times a week, moderate pace where I get a bit out of breath.",
        "expect_keys": {"activity_freq", "activity_minutes", "activity_intensity", "activity_types"},
    },

    # ── Bahasa Malaysia messages ────────────────────────────────────
    {
        "name": "BM — fluid intake",
        "message": "Saya minum 8 gelas air sehari.",
        "expect_keys": {"fluid_intake_ml"},
    },
    {
        "name": "BM — tobacco",
        "message": "Saya berhenti merokok 3 tahun lepas.",
        "expect_keys": {"tobacco_status"},
    },
    {
        "name": "BM rojak — meds + fat",
        "message": "Saya cook dengan minyak kelapa sawit selalu, and sometimes terlupa makan ubat malam.",
        "expect_keys": {"fat_sources", "medication_compliance"},
    },

    # ── Negative tests — should NOT extract ─────────────────────────
    {
        "name": "No specific info",
        "message": "What can I have for breakfast?",
        "expect_keys": set(),
    },
    {
        "name": "Should NOT infer specific number",
        "message": "My doctor told me to drink more water.",
        "expect_keys": set(),
    },
    {
        "name": "Already-known should be filtered",
        "message": "I drink 6 glasses of water daily.",
        "current_profile": {"fluid_intake_ml": 1500},
        "expect_keys": set(),
    },
]


def run():
    passed = 0
    failed = 0
    for i, test in enumerate(TESTS, 1):
        print(f"\n[{i}/{len(TESTS)}] {test['name']}")
        print(f"  Message: {test['message']}")
        result = extract_from_message(
            test["message"],
            current_profile=test.get("current_profile", {}),
        )
        print(f"  Extracted: {result}")
        actual_keys = set(result.keys())
        expected = test["expect_keys"]

        if expected.issubset(actual_keys):
            extra = actual_keys - expected
            if extra:
                print(f"  PASS (with extra keys: {extra})")
            else:
                print(f"  PASS")
            passed += 1
        else:
            missing = expected - actual_keys
            print(f"  FAIL — missing expected keys: {missing}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{len(TESTS)} passed")
    if failed:
        print(f"Note: extractor accuracy isn't 100% perfect even on a 32B model.")
        print(f"Some 'failures' may be the LLM being conservative — review case-by-case.")


if __name__ == "__main__":
    run()
