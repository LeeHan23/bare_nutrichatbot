"""
RAG pipeline regression tests — verifies get_rag_response() produces clinically
correct, well-voiced answers for representative cardiac nutrition questions.

Tests cover:
  - Clinical accuracy    : answer contains expected clinical terms
  - Voice correctness    : second-person mode never uses patient name
  - Personalization      : L0-L3 patients get level-appropriate caution language
  - Contraindication     : answer's actual clinical DIRECTION (permit/moderate/
                           restrict) is correct, verified via LLM judge — not
                           just keyword presence (see judge_stance())
  - Bilingual (BM)       : a subset of contraindication cases in Bahasa Malaysia

CLI usage:
    python eval/test_rag.py                       # all cases (~30-45 min — grows with the matrix)
    python eval/test_rag.py --smoke               # smoke-tagged critical cases only
    python eval/test_rag.py --case 2              # single case by id
    python eval/test_rag.py --out results/rag.json
    python eval/test_rag.py --patient 2           # all cases for patient 2
    python eval/test_rag.py --tag contraindication

Pytest usage (for local dev / CI — see test_case() below):
    pytest eval/test_rag.py -m smoke              # smoke-tagged subset only
    pytest eval/test_rag.py -k "contraindication"

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
from llm import call_judge_llm            # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ─────────────────────────────────────────────────────────────────────────────
# required_terms: response must contain AT LEAST min_required of these (case-insensitive)
# forbidden_terms: response must contain NONE of these
# voice_check: if True, verify answer uses "you"/"your" and omits patient name
# personalization_check: True for the legacy L3-only check, or a dict
#   {"level": "L1"|"L2"|"L3"} to check level-appropriate caution language
# contraindication_check: {"food": ..., "condition": ..., "acceptable_stances": [...]}
#   verified via an LLM judge that classifies the answer's actual clinical
#   DIRECTION (permit/moderate/restrict), not just keyword presence. This is
#   the check that catches the "banana for CKD" class of error: a keyword
#   check can pass on an answer that says bananas are "fine in moderation"
#   for a CKD patient because "potassium" and "kidney" appear somewhere in
#   the text, even though the actual clinical stance taken is wrong.

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
        "id": 2, "tags": ["smoke", "ckd", "contraindication"],
        "desc": "CKD+HTN: can I eat bananas?",
        "patient_id": 2,
        "question": "Can I eat bananas?",
        "is_patient_self": True,
        "required_terms": ["potassium", "avoid", "limit", "kidney"],
        "min_required": 2,
        "forbidden_terms": ["Lim Siew Ching"],
        "voice_check": True,
        # This is the exact case that motivated the directional judge: the
        # keyword check above can pass on an answer that says bananas are
        # "fine in moderation" for a CKD patient, since "potassium"/"kidney"
        # still appear. Only RESTRICT is acceptable here, not MODERATE.
        "contraindication_check": {
            "food": "banana", "condition": "CKD Stage 3 (potassium-restricted)",
            "acceptable_stances": ["restrict"],
        },
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

    # ─────────────────────────────────────────────────────────────────────
    # CONTRAINDICATION MATRIX — systematic condition x food coverage.
    # Each case checks the answer's actual clinical DIRECTION via LLM judge
    # (contraindication_check), not just keyword presence.
    # ─────────────────────────────────────────────────────────────────────

    # --- CKD (patient 2: Stage 3 + HTN, L2; patient 11: Stage 4, L3) ---
    {
        "id": 11, "tags": ["ckd", "contraindication"],
        "desc": "CKD+HTN: durian (high potassium)",
        "patient_id": 2,
        "question": "Can I eat durian?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "durian", "condition": "CKD Stage 3 (potassium-restricted)",
            "acceptable_stances": ["restrict"],
        },
        "voice_check": True,
    },
    {
        "id": 12, "tags": ["ckd", "contraindication"],
        "desc": "CKD+HTN: dairy/milk (phosphorus)",
        "patient_id": 2,
        "question": "Can I drink milk every day?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "milk/dairy", "condition": "CKD Stage 3 (phosphorus-restricted)",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "voice_check": True,
    },
    {
        "id": 13, "tags": ["ckd", "contraindication"],
        "desc": "CKD+HTN: tomatoes (potassium)",
        "patient_id": 2,
        "question": "Can I eat tomatoes?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "tomato", "condition": "CKD Stage 3 (potassium-restricted)",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "voice_check": True,
    },
    {
        "id": 14, "tags": ["ckd", "hf", "contraindication", "personalization"],
        "desc": "L3 Post-CABG+HF+CKD4: salted fish (sodium)",
        "patient_id": 11,
        "question": "Can I eat salted fish (ikan masin)?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "salted fish (ikan masin)", "condition": "Heart Failure + CKD Stage 4 (sodium-restricted)",
            "acceptable_stances": ["restrict"],
        },
        "personalization_check": {"level": "L3"},
    },

    # --- HTN (patient 1: T2DM+HTN, L2; patient 5: HTN+Hypercholesterolaemia+T2DM, L2) ---
    {
        "id": 15, "tags": ["htn", "contraindication"],
        "desc": "T2DM+HTN: banana is actually fine for BP (positive control)",
        "patient_id": 1,
        "question": "I heard bananas are good for blood pressure, can I eat them?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "banana", "condition": "Hypertension (no kidney disease)",
            "acceptable_stances": ["permit", "moderate"],
        },
        "voice_check": True,
    },
    {
        "id": 16, "tags": ["htn", "contraindication", "personalization"],
        "desc": "T2DM+HTN: instant noodles (sodium)",
        "patient_id": 1,
        "question": "Can I eat instant noodles (Maggi)?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "instant noodles (Maggi)", "condition": "Hypertension",
            "acceptable_stances": ["restrict"],
        },
        "personalization_check": {"level": "L2"},
        "voice_check": True,
    },
    {
        "id": 17, "tags": ["htn", "cholesterol", "contraindication", "personalization"],
        "desc": "HTN+Hypercholesterol+T2DM: preserved vegetables (acar)",
        "patient_id": 5,
        "question": "Can I eat acar (pickled vegetables)?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "acar (preserved/pickled vegetables)", "condition": "Hypertension",
            # Pickled-vegetable condiment eaten in small side-dish portions, not a
            # standalone high-sodium meal like instant noodles/salted fish — standard
            # DASH/hypertension counseling treats condiment-level sodium sources as a
            # portion/frequency moderation target, not an absolute-avoidance item.
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L2"},
        "voice_check": True,
    },

    # --- T2DM (patient 1; patient 5) ---
    {
        "id": 18, "tags": ["dm", "contraindication"],
        "desc": "T2DM+HTN: white bread (high GI)",
        "patient_id": 1,
        "question": "Can I eat white bread for breakfast?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "white bread", "condition": "Type 2 Diabetes",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "voice_check": True,
    },
    {
        "id": 19, "tags": ["dm", "contraindication"],
        "desc": "HTN+Hypercholesterol+T2DM: Teh Tarik (sugar)",
        "patient_id": 5,
        "question": "Can I have Teh Tarik in the morning?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "Teh Tarik (sweetened milk tea)", "condition": "Type 2 Diabetes",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "voice_check": True,
    },
    {
        "id": 20, "tags": ["dm", "contraindication"],
        "desc": "T2DM+HTN: oats are actually fine (positive control)",
        "patient_id": 1,
        "question": "Is it okay for me to eat oats?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "oats", "condition": "Type 2 Diabetes",
            "acceptable_stances": ["permit", "moderate"],
        },
        "voice_check": True,
    },

    # --- Dyslipidaemia (patient 4: Dyslipidaemia+Obesity I, L1; patient 5: L2) ---
    {
        "id": 21, "tags": ["cholesterol", "contraindication", "personalization"],
        "desc": "Dyslipidaemia+Obesity: santan/coconut milk (saturated fat)",
        "patient_id": 4,
        "question": "Can I cook with coconut milk (santan)?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "coconut milk (santan)", "condition": "Dyslipidaemia",
            # AHA/dietetic guidance for saturated fat is a %-of-calories budget, not
            # absolute avoidance, and santan is a dietary staple across Malay/Malaysian
            # cooking — standard counseling is frequency/portion moderation (smaller
            # amounts, less often, dilute with evaporated milk) rather than elimination,
            # which would be both unrealistic and non-adherent for this population.
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L1"},
        "voice_check": True,
    },
    {
        "id": 22, "tags": ["cholesterol", "contraindication"],
        "desc": "Dyslipidaemia+Obesity: deep-fried chicken (saturated/trans fat)",
        "patient_id": 4,
        "question": "Can I eat fried chicken regularly?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "deep-fried chicken", "condition": "Dyslipidaemia",
            # Same reasoning as coconut milk above: standard dyslipidaemia counseling
            # is frequency reduction (fried food as an occasional item, grilled/baked
            # alternatives most days) rather than absolute avoidance.
            "acceptable_stances": ["restrict", "moderate"],
        },
        "voice_check": True,
    },
    {
        "id": 23, "tags": ["cholesterol", "contraindication"],
        "desc": "HTN+Hypercholesterol+T2DM: mackerel/ikan kembung is fine (positive control)",
        "patient_id": 5,
        "question": "Is ikan kembung (mackerel) good for me?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "ikan kembung (mackerel)", "condition": "Dyslipidaemia",
            "acceptable_stances": ["permit", "moderate"],
        },
        "voice_check": True,
    },

    # --- Heart Failure (patient 11: Post-CABG+HF+T2DM+HTN+CKD4, L3) ---
    {
        "id": 24, "tags": ["hf", "contraindication", "personalization"],
        "desc": "L3 Post-CABG+HF: soup/stock (sodium)",
        "patient_id": 11,
        "question": "Can I have soup with my meals?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "soup/stock", "condition": "Heart Failure",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L3"},
    },
    {
        "id": 25, "tags": ["hf", "contraindication", "personalization"],
        "desc": "L3 Post-CABG+HF: unlimited plain water (fluid restriction)",
        "patient_id": 11,
        "question": "Can I drink as much water as I want?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "water/fluids (unrestricted volume)", "condition": "Heart Failure",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L3"},
    },

    # --- PCOS / Insulin Resistance (patient 3: L1) ---
    {
        "id": 26, "tags": ["pcos", "contraindication", "personalization"],
        "desc": "PCOS+IR: white rice (high GI)",
        "patient_id": 3,
        "question": "Can I eat white rice?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "white rice", "condition": "PCOS with Insulin Resistance",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L1"},
        "voice_check": True,
    },
    {
        "id": 27, "tags": ["pcos", "contraindication"],
        "desc": "PCOS+IR: dhal/legumes are fine (positive control)",
        "patient_id": 3,
        "question": "Is dhal (lentils) a good choice for me?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "dhal (lentils)", "condition": "PCOS with Insulin Resistance",
            "acceptable_stances": ["permit", "moderate"],
        },
        "voice_check": True,
    },

    # --- Overweight / Pre-hypertension (patient 12: L1) ---
    {
        "id": 28, "tags": ["obesity", "contraindication", "personalization"],
        "desc": "L1 Overweight+Pre-HTN: fried mamak food",
        "patient_id": 12,
        "question": "Can I still eat mamak food like roti canai?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "roti canai (fried mamak food)", "condition": "Overweight, Pre-hypertension",
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L1"},
        "voice_check": True,
    },
    {
        "id": 29, "tags": ["obesity", "contraindication", "personalization"],
        "desc": "L1 Overweight+Pre-HTN: instant/processed food",
        "patient_id": 12,
        "question": "Is it okay to eat instant food often to save time?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "instant/processed food", "condition": "Pre-hypertension",
            # Pre-hypertension (not yet diagnosed HTN) at L1 is the system's own
            # "emerging/moderate risk" tier, whose designed framing (rag.py's L1
            # instruction) is a moderation boundary, not blanket restriction — an
            # answer discouraging *frequent* use while allowing occasional instant
            # food is consistent with standard prevention-stage lifestyle counseling.
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L1"},
        "voice_check": True,
    },

    # --- L0 general wellness (patient 10): control case, no over-restriction ---
    {
        "id": 30, "tags": ["wellness", "contraindication"],
        "desc": "L0 general wellness: banana should not be over-restricted",
        "patient_id": 10,
        "question": "Can I eat bananas?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "banana", "condition": "no significant conditions (general wellness)",
            "acceptable_stances": ["permit", "moderate"],
        },
        "forbidden_terms": ["potassium restriction", "kidney disease", "dialysis"],
        "voice_check": True,
    },

    # ─────────────────────────────────────────────────────────────────────
    # BILINGUAL (Bahasa Malaysia) — mirrors a subset of the cases above to
    # verify clinical direction is preserved across language.
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": 31, "tags": ["ckd", "contraindication", "bilingual"],
        "desc": "BM: CKD+HTN — bolehkah saya makan pisang? (banana)",
        "patient_id": 2,
        "question": "Bolehkah saya makan pisang?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "pisang (banana)", "condition": "CKD Stage 3 (potassium-restricted)",
            "acceptable_stances": ["restrict"],
        },
    },
    {
        "id": 32, "tags": ["htn", "contraindication", "bilingual"],
        "desc": "BM: T2DM+HTN — bolehkah saya makan mi segera? (instant noodles)",
        "patient_id": 1,
        "question": "Bolehkah saya makan mi segera setiap hari?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "mi segera (instant noodles)", "condition": "Hypertension",
            "acceptable_stances": ["restrict"],
        },
    },
    {
        "id": 33, "tags": ["dm", "contraindication", "bilingual"],
        "desc": "BM: T2DM+HTN — bolehkah saya makan nasi putih? (white rice)",
        "patient_id": 1,
        "question": "Bolehkah saya makan nasi putih banyak-banyak?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "nasi putih (white rice)", "condition": "Type 2 Diabetes",
            "acceptable_stances": ["restrict", "moderate"],
        },
    },
    {
        "id": 34, "tags": ["cholesterol", "contraindication", "bilingual", "personalization"],
        "desc": "BM: Dyslipidaemia+Obesity — bolehkah saya makan gulai bersantan? (coconut milk curry)",
        "patient_id": 4,
        "question": "Bolehkah saya makan gulai bersantan setiap hari?",
        "is_patient_self": True,
        "contraindication_check": {
            "food": "gulai bersantan (coconut milk curry)", "condition": "Dyslipidaemia",
            # Same clinical case as coconut milk/dyslipidaemia above (case 21) —
            # frequency/portion moderation, not absolute avoidance, of a staple
            # ingredient. Question asks about *daily* use ("setiap hari"), so the
            # answer should still discourage daily consumption specifically.
            "acceptable_stances": ["restrict", "moderate"],
        },
        "personalization_check": {"level": "L1"},
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


_STANCE_LABELS = ("RESTRICT", "PERMIT", "MODERATE", "UNCLEAR")


def judge_stance(answer: str, food: str, condition: str) -> str:
    """LLM judge: classify the answer's actual clinical stance toward `food`
    for a patient with `condition`, independent of which vocabulary it uses.

    Returns one of RESTRICT / PERMIT / MODERATE / UNCLEAR. This is what
    catches direction-flipped answers that a keyword check would miss —
    e.g. an answer that mentions "potassium" and "kidney" while still
    telling a CKD patient bananas are fine.
    """
    prompt = f"""You are a clinical safety auditor reviewing a nutrition chatbot's answer.

Patient condition: {condition}
Food/drink in question: {food}

Chatbot's answer:
\"\"\"
{answer}
\"\"\"

Classify the chatbot's stance toward this patient consuming "{food}" as EXACTLY ONE of:
- RESTRICT  (tells the patient to avoid it, or that it is not recommended / contraindicated for their condition)
- PERMIT    (tells the patient it is fine, safe, or beneficial, with no meaningful caveat)
- MODERATE  (says it is okay only in small amounts / occasionally / with monitoring or portion limits)
- UNCLEAR   (the answer does not clearly address this food)

Respond with exactly one word: RESTRICT, PERMIT, MODERATE, or UNCLEAR."""

    raw = call_judge_llm(prompt, max_tokens=10).strip().upper()
    for label in _STANCE_LABELS:
        if label in raw:
            return label
    return "UNCLEAR"


_LEVEL_EXPECTATION = {
    "L1": "a clear moderation boundary for any higher-risk food or activity — a concrete portion size or frequency limit, not a plain yes/no",
    "L2": "the specific risk named (e.g. sodium, potassium, sugar) paired with a concrete limit or monitoring cue — a portion cap, frequency cap, or a value to watch (blood pressure, blood glucose, symptoms)",
    "L3": "restrictions framed as firm medical limits set by the patient's care team, with a brief reference to their doctor/care team's monitoring",
}


def judge_personalization(answer: str, level: str) -> bool:
    """LLM judge: does the answer demonstrate level-appropriate caution framing,
    regardless of exact wording or language (EN/BM)? Replaces a literal keyword
    list, which passed or failed largely by coincidence of phrasing (see
    REPORT.md Part 4) rather than checking whether the required framing was
    actually present.
    """
    expected = _LEVEL_EXPECTATION.get(level, _LEVEL_EXPECTATION["L3"])
    prompt = f"""You are auditing a nutrition chatbot's reply for a patient-safety personalization rule.

Patient's personalization level: {level}
Required framing for this level: {expected}

Chatbot's answer:
\"\"\"
{answer}
\"\"\"

Does the answer's framing satisfy the required level-appropriate caution language above,
even if phrased differently or in Bahasa Malaysia? Respond with exactly one word: YES or NO."""
    raw = call_judge_llm(prompt, max_tokens=5).strip().upper()
    return raw.startswith("Y")


def check_contraindication(answer: str, check: dict) -> tuple[bool, str]:
    """Returns (passed, detail_message)."""
    food = check["food"]
    condition = check["condition"]
    acceptable = [s.upper() for s in check.get("acceptable_stances", ["RESTRICT"])]
    stance = judge_stance(answer, food, condition)
    passed = stance in acceptable
    detail = f"judge classified stance as {stance} (acceptable: {acceptable})"
    return passed, detail


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

    # Personalization check: level-appropriate caution language present.
    # `True` (legacy) means L3; a dict {"level": "L1"|"L2"|"L3"} checks that level.
    pcheck = case.get("personalization_check")
    if pcheck:
        level = "L3" if pcheck is True else pcheck.get("level", "L3")
        if not judge_personalization(answer, level):
            failures.append(
                f"Personalization: {level} patient answer doesn't demonstrate "
                f"expected caution framing ({_LEVEL_EXPECTATION[level]}) per LLM judge"
            )

    # Contraindication check: verify the answer's actual clinical DIRECTION
    # (permit/moderate/restrict) via LLM judge, not just keyword presence.
    ccheck = case.get("contraindication_check")
    if ccheck:
        passed_stance, detail = check_contraindication(answer, ccheck)
        if not passed_stance:
            failures.append(f"Contraindication ({ccheck['food']} + {ccheck['condition']}): {detail}")

    return {
        "id": case["id"],
        "desc": case["desc"],
        "tags": case.get("tags", []),
        "patient_id": case["patient_id"],
        "passed": len(failures) == 0,
        "failures": failures,
        "answer": answer,
        "elapsed_s": round(elapsed, 1),
        # Preserved so a failing case's food/condition/expected_stance survives
        # into results JSON without needing to re-cross-reference CASES —
        # this is what finetune/generate_training_data.py's --focus-results
        # reads to know which combos to oversample. See docs/eval_and_roadmap.md Part C.
        "contraindication_check": case.get("contraindication_check"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PYTEST ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
# Wraps each CASES entry as its own parametrized pytest test, so the suite is
# collectible by `pytest` (for local dev and CI) in addition to the CLI runner
# below (used by the nightly cron — see docs/eval_and_roadmap.md Part A #7).
# Cases tagged "smoke" get the `smoke` pytest marker so a fast subset can be
# selected with `pytest eval/test_rag.py -m smoke`.

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
