"""
MyHeartCoach Component taxonomy — the 10 content domains this bot is
expanding to cover (source: MyHeartCoach_Content_Registry.xlsx, Taxonomy tab).

Only "nutrition" has real grounded content today. The other 9 exist here so
retrieval (vector_store.py) and prompting (rag.py) can reference a single,
stable vocabulary instead of hardcoding component names in multiple places.
Adding real content for another component later means filling in its
COMPONENT_SCOPE entry and tagging chunks with doc_components — no new
tables, no schema change.

See docs/component_taxonomy_contract.md for open questions this taxonomy
deliberately does not resolve (Rehab R1-6, Dynamic persona, live RPE/HR
scoring, Personalization_Rules).
"""

COMPONENTS = [
    "foundations",
    "blood_pressure",
    "lipid",
    "diabetes",
    "exercise",
    "tobacco_nicotine_alcohol",
    "physical_activity",
    "nutrition",
    "psychosocial",
    "medication",
]

# Machine slug -> client-facing display string (Taxonomy tab wording).
COMPONENT_LABELS = {
    "foundations": "Foundations - Heart Diseases",
    "blood_pressure": "Blood Pressure Management",
    "lipid": "Lipid Management",
    "diabetes": "Diabetes Management",
    "exercise": "Exercise",
    "tobacco_nicotine_alcohol": "Tobacco / Nicotine / Alcohol",
    "physical_activity": "Physical Activity",
    "nutrition": "Nutrition",
    "psychosocial": "Psychosocial",
    "medication": "Medication",
}

# Fallback guard for any component that reaches component_scope_block()
# without a COMPONENT_SCOPE entry (e.g. a new component slug added to
# COMPONENTS before its scope text is written). All 10 current components
# have real entries below — see docs/component_taxonomy_contract.md.
_NO_CONTENT_GUARD = (
    "This question is about {label}, which does not yet have clinically-approved "
    "grounded content in this system. Do NOT answer from general knowledge or "
    "invent advice. Tell the patient this topic isn't available yet in this "
    "assistant and to ask their care team or doctor, then stop — do not continue "
    "with unrelated advice unless they re-ask a Nutrition question."
)

# component -> {"in_scope": str, "out_of_scope": str}. "nutrition" and
# "exercise" are grounded in real retrieved content (base_knowledge chunks /
# the approved exercise-video catalog, respectively). The other 8 have no
# ingested clinical documents at all — their blocks are scoped to general,
# non-prescriptive lay education only (2026-08-14 decision): explain
# concepts, never interpret the patient's own numbers/results, never give
# dosing/timing/programming advice, always defer anything personalized or
# clinical to the care team.
COMPONENT_SCOPE = {
    "nutrition": {
        "in_scope": (
            "Healthy eating patterns, heart-healthy diet principles, food choices and "
            "substitutions, meal timing and habits, nutrient awareness (salt, sugar, fats), "
            "general non-prescriptive dietary guidance for the patient's conditions."
        ),
        "out_of_scope": (
            "Medical nutrition therapy (strict clinical diets), personalized meal plans with "
            "exact prescriptions, supplement or drug recommendations, exercise programming, "
            "clinical lab-based dietary adjustments — defer these to the patient's care team."
        ),
    },
    # Not the standard "no content yet" guard: this component has one real
    # grounded source, the approved exercise-video library (see
    # exercise_lookup.py). A level-filtered sample of it is injected as an
    # "Approved Exercise Catalog" block when present — you may name and
    # describe exercises FROM THAT LIST ONLY. The video LINK itself is
    # always attached automatically in code when the patient asks to
    # see/watch a demo — never invent, guess, or state a YouTube link
    # yourself under any circumstance.
    "exercise": {
        "in_scope": (
            "General guidance grounded only in the Approved Exercise Catalog block, when present: "
            "what type of exercise, at what intensity, targeting which body area, for roughly how "
            "long, suits this patient's level — you may name exercises from that list. Confirming "
            "that a matching video will be shown when the patient asks to see/watch a demo — do not "
            "say you have no videos available, and never state, describe, or invent a YouTube link "
            "yourself, one is attached automatically outside your response."
        ),
        "out_of_scope": (
            "Anything not in the Approved Exercise Catalog block (or if no catalog block is present "
            "at all), prescribing a structured programme or progression plan, judging whether a "
            "specific intensity or duration is medically safe beyond what the level filter already "
            "reflects — defer these to the patient's care team."
        ),
    },
    "foundations": {
        "in_scope": (
            "General, plain-language explanations of what heart disease is, common types (coronary "
            "artery disease, heart failure, arrhythmia), well-known risk factors, why regular "
            "check-ups and screening matter, and how the heart works at a lay level."
        ),
        "out_of_scope": (
            "Diagnosing or explaining the patient's own condition, interpreting their personal test "
            "results or imaging, prognosis for their specific case, or anything that could substitute "
            "for their doctor explaining their actual diagnosis — defer these to the patient's care team."
        ),
    },
    "blood_pressure": {
        "in_scope": (
            "General education on what blood pressure is, what systolic/diastolic numbers mean in "
            "general, well-known non-drug lifestyle factors linked to blood pressure (sodium, weight, "
            "stress, activity, sleep), and why regular monitoring matters."
        ),
        "out_of_scope": (
            "Interpreting the patient's own blood pressure readings, telling them whether their own "
            "BP is controlled, target-number advice, or any guidance on antihypertensive medication "
            "(starting, stopping, timing, dosing) — defer these to the patient's care team."
        ),
    },
    "lipid": {
        "in_scope": (
            "General education on cholesterol and lipids (LDL, HDL, triglycerides) at a lay level, "
            "why they matter for heart health, and well-known general lifestyle factors linked to them."
        ),
        "out_of_scope": (
            "Interpreting the patient's own lipid panel results, target-number advice, or any "
            "guidance on lipid-lowering medication such as statins (starting, stopping, dosing, side "
            "effects) — defer these to the patient's care team."
        ),
    },
    "diabetes": {
        "in_scope": (
            "General education on what diabetes and prediabetes are, what blood glucose and HbA1c "
            "mean in general, well-known non-drug lifestyle factors, and why monitoring matters."
        ),
        "out_of_scope": (
            "Interpreting the patient's own glucose readings or HbA1c results, diagnosing diabetes, "
            "or any guidance on insulin or other diabetes medication (dosing, timing, adjustment) — "
            "defer these to the patient's care team."
        ),
    },
    "tobacco_nicotine_alcohol": {
        "in_scope": (
            "General education on how tobacco, nicotine, and alcohol affect cardiovascular health, "
            "encouragement to cut down or quit, and general well-known information about the kinds of "
            "support and resources (e.g. quitlines, counselling) that exist."
        ),
        "out_of_scope": (
            "Prescribing a specific cessation programme, nicotine-replacement dosing, medical detox "
            "or withdrawal management, or judging whether a specific reduction plan is medically safe "
            "for this patient — defer these to the patient's care team."
        ),
    },
    "physical_activity": {
        "in_scope": (
            "General, non-structured lay encouragement around everyday movement — walking more, "
            "reducing sitting time, general safety principles for staying active with a heart "
            "condition. This is broader lifestyle framing, not exercise programming."
        ),
        "out_of_scope": (
            "Structured exercise programmes, specific intensities/durations/progressions, or naming "
            "specific exercises — that belongs to the 'exercise' component and its Approved Exercise "
            "Catalog only. Clearing the patient for a specific activity level — defer to the patient's "
            "care team."
        ),
    },
    "psychosocial": {
        "in_scope": (
            "General education on the well-known link between stress/mental health and heart disease, "
            "normalizing common emotional experiences after a cardiac diagnosis (anxiety, low mood), "
            "general self-care and coping information, and encouragement to seek support."
        ),
        "out_of_scope": (
            "Therapy, diagnosing a mental health condition, medication for mental health, or crisis "
            "intervention — if the patient expresses any self-harm or crisis language, direct them to "
            "emergency services or a crisis line immediately, then defer ongoing care to a mental "
            "health professional or their care team."
        ),
    },
    "medication": {
        "in_scope": (
            "General, non-personalized education about what common cardiac medication classes are "
            "generally used for (e.g. 'statins are commonly used to help manage cholesterol'), and "
            "the general importance of taking medication as prescribed."
        ),
        "out_of_scope": (
            "Any dosing, timing, starting/stopping/switching medication, side-effect management, drug "
            "interactions, or confirming/denying whether a specific medicine is right for this patient "
            "— always defer these to the patient's doctor or pharmacist, no exceptions."
        ),
    },
}


def component_scope_block(component: str | None) -> str:
    """Render the prompt block for a component's scope boundary.

    Returns "" for None/unknown/nutrition-with-no-override-needed-elsewhere so
    callers can skip the section header entirely when there's nothing to say.
    """
    if not component:
        return ""
    scope = COMPONENT_SCOPE.get(component)
    if scope:
        return f"In scope: {scope['in_scope']}\nOut of scope: {scope['out_of_scope']}"
    label = COMPONENT_LABELS.get(component, component)
    return _NO_CONTENT_GUARD.format(label=label)


# Onboarding stages (OB1-3) — an external state machine (not this repo) owns
# progressing a patient through these; Nutribot only needs to understand what
# an incoming onboarding_stage signal means so it can calibrate depth/safety
# accordingly. Read-only, same treatment as care_path — see
# docs/state_machine_contract.md. Ported from the Taxonomy tab's
# Personalization Classification rows.
ONBOARDING_STAGE_LABELS = {
    "OB1": (
        "Completed OB1 only — goals/preferences known, no medical history relied on yet. "
        "Focus on motivation, awareness, and safe entry into healthy behaviors; avoid "
        "condition-specific medical advice."
    ),
    "OB2": (
        "Completed OB2 — known medical conditions are on file. Guide safely by aligning "
        "advice with chronic disease management needs; avoid medication-specific instructions."
    ),
    "OB3": (
        "Completed OB3 — medications and allergies are on file. Contraindication and "
        "medication-interaction awareness is expected; still never suggest changing a dose "
        "or medication."
    ),
}


if __name__ == "__main__":
    # Every component must resolve to its own real scope block, never the
    # generic fallback guard — a missing entry here means that component
    # would silently refuse to answer anything.
    for _c in COMPONENTS:
        assert _c in COMPONENT_SCOPE, f"{_c} has no COMPONENT_SCOPE entry"
        block = component_scope_block(_c)
        assert "does not yet have clinically-approved" not in block, (
            f"{_c} fell through to the fallback guard"
        )
        assert "In scope:" in block and "Out of scope:" in block
    assert component_scope_block(None) == ""
    assert component_scope_block("made_up_component").startswith("This question is about")
    print(f"OK — all {len(COMPONENTS)} components have real scope blocks")
