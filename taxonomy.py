"""
MyHeartCoach Component taxonomy — the 11 content domains this bot covers
(source: MyHeartCoach_Content_Registry.xlsx, Taxonomy tab, plus a client
document drop on 2026-09-07 that added "weight" and grounded 7 more).

As of 2026-09-07, every component except "medication" is grounded in real
ingested clinical content (medication has one thin document — the WHO
pharmacological hypertension guideline — and keeps the tightest safety
boundary of the group regardless). retrieval (vector_store.py) and
prompting (rag.py) reference this single, stable vocabulary instead of
hardcoding component names in multiple places. Adding real content for a
component later means filling in its COMPONENT_SCOPE entry and tagging
chunks with doc_components — no new tables, no schema change.

See docs/component_taxonomy_contract.md for open questions this taxonomy
deliberately does not resolve (Rehab R1-6, Dynamic persona, live RPE/HR
scoring, Personalization_Rules).
"""

COMPONENTS = [
    "foundations",
    "blood_pressure",
    "lipid",
    "diabetes",
    "weight",
    "exercise",
    "tobacco_nicotine_alcohol",
    "physical_activity",
    "nutrition",
    "psychosocial",
    "medication",
]

# Machine slug -> client-facing display string. Matches the source document
# folder titles verbatim (2026-09-07 client document drop), not a cleaned-up
# / title-cased version — explicit user instruction.
COMPONENT_LABELS = {
    "foundations": "Cardiac diseases management",
    "blood_pressure": "Blood Pressure management",
    "lipid": "Lipid management",
    "diabetes": "Diabetes management",
    "weight": "Weight management",
    "exercise": "Exercise Rehab",
    "tobacco_nicotine_alcohol": "Tobacco cessation",
    "physical_activity": "Physical activity",
    "nutrition": "Nutrition",
    "psychosocial": "Psychosocial management",
    "medication": "Medications",
}

# Fallback guard for any component that reaches component_scope_block()
# without a COMPONENT_SCOPE entry (e.g. a new component slug added to
# COMPONENTS before its scope text is written). All 11 current components
# have real entries below — see docs/component_taxonomy_contract.md.
_NO_CONTENT_GUARD = (
    "This question is about {label}, which does not yet have clinically-approved "
    "grounded content in this system. Do NOT answer from general knowledge or "
    "invent advice. Tell the patient this topic isn't available yet in this "
    "assistant and to ask their care team or doctor, then stop — do not continue "
    "with unrelated advice unless they re-ask a Nutrition question."
)

# component -> {"in_scope": str, "out_of_scope": str}. As of 2026-09-07,
# every component is grounded in real retrieved base_knowledge content
# ("exercise" additionally has the approved exercise-video catalog).
# "medication" stays thin (one document) and keeps the strictest boundary
# of the group regardless of grounding: never interpret the patient's own
# numbers/results, never give dosing/timing/programming/switching advice,
# always defer anything personalized or clinical to the care team. The
# 2026-08-14 "lay education only, no ingested documents" framing that used
# to apply to 8 of these components no longer reflects reality and has been
# replaced below — the safety (out_of_scope) boundaries themselves are
# unchanged, only the "no grounded content" framing was removed.
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
            "Plain-language explanations of what heart disease is, common types (coronary artery "
            "disease, heart failure, arrhythmia), risk factors, and why regular check-ups and "
            "screening matter — grounded in the retrieved cardiac disease management guideline "
            "content (e.g. CPG PCI, CPG Stable CAD, CPG Heart Failure, ACC/AHA and WHO CVD "
            "prevention guidance)."
        ),
        "out_of_scope": (
            "Diagnosing or explaining the patient's own condition, interpreting their personal test "
            "results or imaging, prognosis for their specific case, or anything that could substitute "
            "for their doctor explaining their actual diagnosis — defer these to the patient's care team."
        ),
    },
    "blood_pressure": {
        "in_scope": (
            "Education on what blood pressure is, what systolic/diastolic numbers mean in general, "
            "non-drug lifestyle factors linked to blood pressure (sodium, weight, stress, activity, "
            "sleep), and why regular monitoring matters — grounded in the retrieved hypertension "
            "guideline content (e.g. ISH 2020, NICE, national CPG Hypertension, WHO pharmacological "
            "treatment guideline, Life's Essential 8 blood pressure sheet)."
        ),
        "out_of_scope": (
            "Interpreting the patient's own blood pressure readings, telling them whether their own "
            "BP is controlled, target-number advice, or any guidance on antihypertensive medication "
            "(starting, stopping, timing, dosing) — defer these to the patient's care team."
        ),
    },
    "lipid": {
        "in_scope": (
            "Education on cholesterol and lipids (LDL, HDL, triglycerides), why they matter for "
            "heart health, and general lifestyle factors linked to them — grounded in the retrieved "
            "dyslipidaemia guideline content (e.g. national CPG Dyslipidaemia, AHA/ACC blood "
            "cholesterol guideline, Life's Essential 8 cholesterol sheet)."
        ),
        "out_of_scope": (
            "Interpreting the patient's own lipid panel results, target-number advice, or any "
            "guidance on lipid-lowering medication such as statins (starting, stopping, dosing, side "
            "effects) — defer these to the patient's care team."
        ),
    },
    "diabetes": {
        "in_scope": (
            "Education on what diabetes and prediabetes are, what blood glucose and HbA1c mean in "
            "general, non-drug lifestyle factors, and why monitoring matters — grounded in the "
            "retrieved diabetes guideline content (e.g. CPG T2DM 6th edition, CPG Diabetic Foot, "
            "e-MDES manual, NIDDK, Life's Essential 8 blood sugar sheet)."
        ),
        "out_of_scope": (
            "Interpreting the patient's own glucose readings or HbA1c results, diagnosing diabetes, "
            "or any guidance on insulin or other diabetes medication (dosing, timing, adjustment) — "
            "defer these to the patient's care team."
        ),
    },
    "weight": {
        "in_scope": (
            "Education on healthy weight and obesity as a cardiovascular risk factor, BMI/waist "
            "circumference in general terms, and non-prescriptive lifestyle factors linked to weight "
            "management (diet, activity, sleep, stress) — grounded in the retrieved weight-management "
            "guideline content (e.g. national CPG Management of Obesity 2nd edition, NHLBI Overweight "
            "and Obesity guideline, NICE Overweight and obesity, Life's Essential 8 weight sheet)."
        ),
        "out_of_scope": (
            "Interpreting the patient's own weight, BMI, or body-composition results, prescribing a "
            "calorie target or weight-loss plan, bariatric surgery eligibility, or any weight-"
            "management medication (starting, stopping, dosing) — defer these to the patient's care "
            "team."
        ),
    },
    "tobacco_nicotine_alcohol": {
        "in_scope": (
            "Education on how tobacco, nicotine, and alcohol affect cardiovascular health, "
            "encouragement to cut down or quit, and information about support and resources "
            "(quitlines, counselling) — grounded in the retrieved cessation guideline content "
            "(e.g. national CPG Tobacco Use Disorder, WHO tobacco cessation guideline, Modul "
            "Berhenti Merokok, Life's Essential 8 quit-tobacco sheet)."
        ),
        "out_of_scope": (
            "Prescribing a specific cessation programme, nicotine-replacement dosing, medical detox "
            "or withdrawal management, or judging whether a specific reduction plan is medically safe "
            "for this patient — defer these to the patient's care team."
        ),
    },
    "physical_activity": {
        "in_scope": (
            "Non-structured lay encouragement around everyday movement — walking more, reducing "
            "sitting time, general safety principles for staying active with a heart condition — "
            "grounded in the retrieved physical activity guideline content (e.g. Malaysian Physical "
            "Activity Guideline, Buku MDG 2020 Senaman, Life's Essential 8 activity sheet). This is "
            "broader lifestyle framing, not exercise programming."
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
            "Education on the link between stress/mental health and heart disease, normalizing "
            "common emotional experiences after a cardiac diagnosis (anxiety, low mood), self-care "
            "and coping information, and encouragement to seek support — grounded in the retrieved "
            "psychosocial guideline content (e.g. Joel 2022, Levine 2021 AHA scientific statement, "
            "Xu 2024, KKM National Strategic Plan for Mental Health, KKM stress/depression education "
            "materials)."
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
            "Non-personalized education about what common cardiac medication classes are generally "
            "used for (e.g. 'statins are commonly used to help manage cholesterol'), the general "
            "importance of taking medication as prescribed, and general blood-pressure medication "
            "class information — grounded in the retrieved medication guideline content (currently: "
            "the WHO Guideline for the pharmacological treatment of hypertension in adults)."
        ),
        "out_of_scope": (
            "Any dosing, timing, starting/stopping/switching medication, side-effect management, drug "
            "interactions, or confirming/denying whether a specific medicine is right for this patient "
            "— always defer these to the patient's doctor or pharmacist, no exceptions."
        ),
    },
}


# Supplementary DB fields (patient_store.SUPPLEMENTARY_FIELDS) that give a
# direct signal the patient has engaged with a non-nutrition component.
# Components with no dedicated field (foundations, blood_pressure, lipid,
# diabetes, psychosocial) have no DB-backed "missing" signal — the manager
# persona offers those from the vocabulary directly, not from this check.
_MODULE_SIGNAL_FIELDS = {
    "tobacco_nicotine_alcohol": ("tobacco_status", "alcohol_per_week"),
    "physical_activity": ("activity_freq", "activity_minutes", "activity_intensity", "activity_types"),
    "medication": ("medication_compliance",),
}


def uncovered_modules(profile: dict | None) -> list[str]:
    """Display labels for components this patient has no supplementary data
    for yet, among the components detectable via DB fields. Used to give the
    manager persona concrete, non-hallucinated options to offer the patient
    instead of only ever talking about diet. Returns [] if profile is None.
    """
    if profile is None:
        return []
    return [
        COMPONENT_LABELS[component]
        for component, fields in _MODULE_SIGNAL_FIELDS.items()
        if all(not profile.get(f) for f in fields)
    ]


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
        "condition-specific medical advice.\n\n"
        "Role: Coach. Tone: Motivational, supportive.\n"
        "Exercise: intensity Low to Moderate; duration <=10 minutes; frequency <=2 loops/day; "
        "stop_conditions mandatory; safety_note required.\n"
        "Knowledge topics: healthy habits, diet, hydration, stress management, early signs of "
        "cardiac issues.\n"
        "Activity: ADL-based, light frequency, motivational reminders."
    ),
    "OB2": (
        "Completed OB2 — known medical conditions are on file. Guide safely by aligning "
        "advice with chronic disease management needs; avoid medication-specific instructions.\n\n"
        "Role: Guide. Tone: Safety-aware.\n"
        "Knowledge topics: hypertension, diabetes, stroke, kidney failure, heart failure.\n"
        "Focus: disease awareness, lifestyle adaptation, early complication indicators."
    ),
    "OB3": (
        "Completed OB3 — medications and allergies are on file. Contraindication and "
        "medication-interaction awareness is expected; still never suggest changing a dose "
        "or medication.\n\n"
        "Role: Guide. Tone: Safety-aware.\n"
        "Knowledge topics: medication purpose, medication adherence.\n"
        "Focus: compliance support, lifestyle interaction, adverse reaction awareness."
    ),
}

# L0-L3 Role/Tone/Exercise/Knowledge/Activity policy, transcribed verbatim from
# MyHeartCoach_RulesPolicyTables_v2.xlsx's "Prompt" tab (L0-L3 rows). This is
# additive to rag._LEVEL_INSTRUCTIONS / _LEVEL_INSTRUCTIONS_SELF, which cover
# dietary/nutrition framing only — this dict covers the client's Role/Tone and
# the non-nutrition Exercise/Knowledge/Activity scope for each risk level.
# Consumed by rag.py (live chat prompt) and scripts/generate_weekly_eka.py
# (weekly batch content prompt) — see docs/component_taxonomy_contract.md.
PERSONALIZATION_LEVEL_PROFILE = {
    "L0": (
        "Role: Coach. Tone: Performance-oriented.\n"
        "Exercise: Light, Moderate, Vigorous allowed; progression encouraged.\n"
        "Knowledge topics: healthy diet, smoking harms, weight management, CVD prevention.\n"
        "Activities: step goals allowed; structured activities allowed."
    ),
    "L1": (
        "Role: Guide. Tone: Supportive.\n"
        "Exercise: Light to Moderate only; cautious progression.\n"
        "Knowledge topics: smoking cessation, obesity prevention, LDL/HDL basics, preventive education.\n"
        "Activities: consistency-focused."
    ),
    "L2": (
        "Role: Protector. Tone: Cautious, reassuring.\n"
        "Exercise: Light to Moderate only; NO progression.\n"
        "Knowledge topics: medication adherence, salt reduction, disease-specific education, risk reduction.\n"
        "Activities: ADL only; fatigue-aware; pain-aware."
    ),
    "L3": (
        "Role: Gatekeeper. Tone: Clinical, calm, safety-first.\n"
        "Exercise: Stretching only; cooling down only; light intensity only; progression forbidden.\n"
        "Knowledge topics: emergency awareness, severe hypertension awareness, exercise safety, "
        "high-risk precautions.\n"
        "Activities: micro-movement only; sedentary-break reminders only."
    ),
}

# Structured (role, tone) lookup — the same Role/Tone values embedded in the
# prose blocks above, extracted so the main persona (rag.py, agent.py) can
# name the active role in its opening line instead of it only appearing
# buried in the later Personalization Level / Onboarding Stage sections.
PERSONALIZATION_LEVEL_ROLE = {
    "L0": ("Coach", "Performance-oriented"),
    "L1": ("Guide", "Supportive"),
    "L2": ("Protector", "Cautious, reassuring"),
    "L3": ("Gatekeeper", "Clinical, calm, safety-first"),
}
ONBOARDING_STAGE_ROLE = {
    "OB1": ("Coach", "Motivational, supportive"),
    "OB2": ("Guide", "Safety-aware"),
    "OB3": ("Guide", "Safety-aware"),
}


def resolve_active_role(profile: dict | None) -> tuple[str, str] | None:
    """Return (role, tone) for the main persona to adopt right now, or None.

    personalization_level wins over onboarding_stage when both are set — per
    the xlsx's own "Chatbot System prompt" row: level-specific rules "are
    mandatory and override generic recommendations". onboarding_stage is
    only a fallback for a patient not yet risk-stratified.
    """
    if not profile:
        return None
    level = profile.get("personalization_level")
    if level in PERSONALIZATION_LEVEL_ROLE:
        return PERSONALIZATION_LEVEL_ROLE[level]
    stage = profile.get("onboarding_stage")
    if stage in ONBOARDING_STAGE_ROLE:
        return ONBOARDING_STAGE_ROLE[stage]
    return None


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

    # PERSONALIZATION_LEVEL_PROFILE / ONBOARDING_STAGE_LABELS must cover all
    # 4 levels / 3 stages, and the original summary text must still be present
    # (a regression guard against an accidental overwrite instead of append).
    _ONBOARDING_ORIGINAL_MARKERS = {
        "OB1": "no medical history relied on yet",
        "OB2": "known medical conditions are on file",
        "OB3": "medications and allergies are on file",
    }
    for _level in ("L0", "L1", "L2", "L3"):
        assert _level in PERSONALIZATION_LEVEL_PROFILE, f"{_level} has no PERSONALIZATION_LEVEL_PROFILE entry"
        assert _level in PERSONALIZATION_LEVEL_ROLE, f"{_level} has no PERSONALIZATION_LEVEL_ROLE entry"
    for _stage, _marker in _ONBOARDING_ORIGINAL_MARKERS.items():
        assert _marker in ONBOARDING_STAGE_LABELS[_stage], f"{_stage} lost its original summary text"
        assert _stage in ONBOARDING_STAGE_ROLE, f"{_stage} has no ONBOARDING_STAGE_ROLE entry"

    # resolve_active_role() precedence: personalization_level overrides
    # onboarding_stage; onboarding_stage is a fallback; neither -> None.
    assert resolve_active_role(None) is None
    assert resolve_active_role({}) is None
    assert resolve_active_role({"onboarding_stage": "OB2"}) == ("Guide", "Safety-aware")
    assert resolve_active_role({"personalization_level": "L2"}) == ("Protector", "Cautious, reassuring")
    assert resolve_active_role(
        {"personalization_level": "L2", "onboarding_stage": "OB2"}
    ) == ("Protector", "Cautious, reassuring"), "personalization_level must win over onboarding_stage"

    # uncovered_modules(): no profile -> nothing claimed missing; a profile
    # with every signal field set -> nothing missing; a bare profile -> all
    # three DB-detectable modules missing.
    assert uncovered_modules(None) == []
    assert uncovered_modules({}) == [
        COMPONENT_LABELS["tobacco_nicotine_alcohol"],
        COMPONENT_LABELS["physical_activity"],
        COMPONENT_LABELS["medication"],
    ]
    assert uncovered_modules({"tobacco_status": "Never smoked", "activity_freq": "3x/week",
                               "medication_compliance": "Good"}) == []

    print(f"OK — all {len(COMPONENTS)} components have real scope blocks")
