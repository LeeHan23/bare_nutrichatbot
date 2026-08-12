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

# Shared guard for every component with no clinically-approved grounded
# content yet. Safety requirement: a cardiac patient must never get a
# confident, ungrounded answer on e.g. medication dosing just because the
# LLM "knows" something about it in general. One shared template, not 9
# bespoke blocks — see docs/component_taxonomy_contract.md.
_NO_CONTENT_GUARD = (
    "This question is about {label}, which does not yet have clinically-approved "
    "grounded content in this system. Do NOT answer from general knowledge or "
    "invent advice. Tell the patient this topic isn't available yet in this "
    "assistant and to ask their care team or doctor, then stop — do not continue "
    "with unrelated advice unless they re-ask a Nutrition question."
)

# component -> {"in_scope": str, "out_of_scope": str}. Only "nutrition" has a
# real block (ported from the Taxonomy tab's Nutrition row); the rest render
# the shared guard above via component_scope_block().
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
