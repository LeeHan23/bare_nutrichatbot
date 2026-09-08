"""
generate_weekly_eka.py — Weekly Exercise / Knowledge / Activity content generator.

Generates three content types per condition group on a 4-week rotating schedule:
  E — Exercise: framing copy grounded in the REAL approved exercise-video catalog
      (exercise_lookup.py) — never an invented session plan, see _generate_exercise().
  K — Knowledge: 6 educational points on a health topic, general-education only.
  A — Activity: daily/weekly behavioural task with micro-actions.

Retired 2026-08-12, rebuilt 2026-08-14 on the taxonomy safety guardrails
(_SAFETY_GUARDRAILS, and Exercise grounded in the real catalog instead of
invented) after a dietitian flag on the old generator's output (material
id=68 — see materials/eka_dietitian_review_flags.md) recommended a
high-potassium food swap to CKD patients. All output still lands as
is_active=False — nothing here reaches a patient without a human approving
it via POST /content/materials/{id}/approve. See docs/component_taxonomy_contract.md.

Usage:
    # Generate all E/K/A for current ISO week
    python scripts/generate_weekly_eka.py

    # Generate for a specific week number
    python scripts/generate_weekly_eka.py --week 22

    # Filter to one group or type
    python scripts/generate_weekly_eka.py --group CKD --type K

    # Dry run — show what would be generated, no LLM call
    python scripts/generate_weekly_eka.py --dry-run

    # Force overwrite existing DB rows
    python scripts/generate_weekly_eka.py --force
"""
import argparse, json, os, sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# 4-week rotating topic library per condition group × content type
# ---------------------------------------------------------------------------
# Structure: group_slug → content_type → list of 4 (week_slot, topic_slug, title, rag_query, prompt_topic)
# week_slot 1-4 cycles via: rotation = ((iso_week - 1) % 4) + 1

_TEMPLATES = {
    "T2DM": {
        "condition_tags": ["Type 2 Diabetes"],
        "E": [
            (1, "walking_foundation",
             "Week {w} — Walking Foundation for Blood Sugar",
             "walking aerobic exercise type 2 diabetes blood glucose safety",
             "a 20-25 min beginner walking programme for T2DM, blood glucose checks before/after exercise, "
             "safe intensity using talk test, what to do if glucose is too low before starting"),
            (2, "resistance_basics",
             "Week {w} — Resistance Training for Insulin Sensitivity",
             "resistance strength training type 2 diabetes insulin sensitivity bodyweight bands",
             "simple resistance exercises (bodyweight or bands) 2×/week to improve insulin sensitivity for T2DM in Malaysia, "
             "including progressions from seated to standing movements"),
            (3, "mixed_training",
             "Week {w} — Combining Cardio and Strength",
             "combined aerobic resistance exercise diabetes HbA1c blood sugar gym-free",
             "a 40-min combined session: 20 min aerobic + 20 min strength, gym-free, safe blood glucose management"),
            (4, "flexibility_balance",
             "Week {w} — Flexibility and Balance for Diabetes",
             "stretching flexibility yoga diabetes peripheral neuropathy balance foot care",
             "gentle stretching and balance exercises addressing peripheral neuropathy risk in T2DM, "
             "with foot inspection reminder as part of cool-down"),
        ],
        "K": [
            (1, "understanding_t2dm",
             "Week {w} — Understanding Type 2 Diabetes",
             "type 2 diabetes pathophysiology insulin resistance beta cell progression Malaysia",
             "what T2DM is, why insulin resistance develops, and how Malaysian diet and lifestyle patterns drive progression"),
            (2, "blood_sugar_food",
             "Week {w} — How Food Affects Blood Sugar",
             "glycaemic index glycaemic load carbohydrate blood glucose response Malaysian food",
             "how GI and GL of common Malaysian foods (nasi, roti, mee, kuih) affect blood sugar and how to reduce spikes"),
            (3, "exercise_insulin",
             "Week {w} — Why Exercise Is Medicine for Diabetes",
             "exercise diabetes HbA1c insulin sensitivity glucose uptake GLUT4 benefit",
             "the science of GLUT4-mediated glucose uptake during exercise, how it lowers blood sugar independent of insulin"),
            (4, "monitoring_targets",
             "Week {w} — Monitoring Your Blood Sugar",
             "blood glucose self-monitoring HbA1c fasting postprandial targets home glucometer",
             "how to use a glucometer, what fasting and post-meal glucose targets mean, when to call the clinic"),
        ],
        "A": [
            (1, "step_tracking",
             "Week {w} — Daily Step Tracking Challenge",
             "daily steps walking diabetes blood sugar benefit 5000 10000",
             "setting a daily step goal starting at 5000 steps/day, how to track, and the blood sugar benefit"),
            (2, "glucose_diary",
             "Week {w} — Blood Glucose and Meal Diary",
             "blood glucose diary food log self-monitoring diabetes patterns",
             "a simple food + blood glucose log to identify personal trigger foods and meal-timing patterns"),
            (3, "meal_timing",
             "Week {w} — Meal Timing Tracker",
             "meal timing regularity carbohydrate distribution diabetes blood sugar spikes",
             "tracking meal times and carb portions across the day to smooth blood sugar fluctuations"),
            (4, "monthly_review",
             "Week {w} — Monthly Progress Check-In",
             "diabetes self-assessment HbA1c goals progress lifestyle review",
             "4-week review of steps, glucose logs, and lifestyle changes; setting the next month's goals"),
        ],
    },
    "HTN": {
        "condition_tags": ["Hypertension"],
        "E": [
            (1, "gentle_walking",
             "Week {w} — Gentle Walking for Blood Pressure",
             "walking aerobic exercise hypertension blood pressure reduction safe",
             "a 20-min gentle walking programme for hypertension, RPE scale for effort, "
             "BP monitoring before and after, hydration in Malaysian heat"),
            (2, "low_impact_cardio",
             "Week {w} — Low-Impact Cardio Routine",
             "low impact exercise hypertension swimming cycling light aerobic blood pressure",
             "low-impact cardio options available in Malaysia (pool walking, cycling, light aerobics) safe for hypertension, "
             "how to build to 150 min/week gradually"),
            (3, "breathing_exercises",
             "Week {w} — Breathing and Relaxation Exercises",
             "deep breathing diaphragmatic breathing blood pressure reduction hypertension stress",
             "slow deep breathing (4-7-8 technique, diaphragmatic breathing) to acutely lower BP and reduce sympathetic tone"),
            (4, "gentle_yoga",
             "Week {w} — Gentle Yoga and Stretching",
             "yoga stretching hypertension blood pressure parasympathetic relaxation",
             "gentle yoga poses for hypertension: which inversions to avoid, best poses for BP reduction"),
        ],
        "K": [
            (1, "understanding_htn",
             "Week {w} — Understanding Hypertension",
             "hypertension pathophysiology blood pressure stages causes risk Malaysia prevalence",
             "what BP numbers mean (systolic/diastolic), how hypertension damages vessels, why 'silent killer' matters in Malaysia"),
            (2, "sodium_bp",
             "Week {w} — Sodium, Potassium, and Blood Pressure",
             "sodium potassium blood pressure DASH diet hypertension reduction mechanism",
             "the mechanism of sodium-BP link, potassium as counter-balance, and examples from Malaysian cooking (kicap, belacan, monosodium glutamate)"),
            (3, "stress_bp",
             "Week {w} — Stress and Blood Pressure",
             "stress cortisol adrenaline blood pressure hypertension sympathetic nervous system",
             "how work stress, financial stress, and social pressures raise BP via cortisol and adrenaline, "
             "and evidence-based coping strategies"),
            (4, "bp_monitoring",
             "Week {w} — Understanding Your Blood Pressure Numbers",
             "blood pressure measurement technique home monitoring systolic diastolic target hypertension",
             "correct BP measurement technique at home, white-coat effect, treatment targets by guideline"),
        ],
        "A": [
            (1, "bp_tracking",
             "Week {w} — Twice-Daily Blood Pressure Log",
             "blood pressure home monitoring log morning evening hypertension tracking",
             "setting up a twice-daily BP logging habit (morning before meds, evening) with simple chart"),
            (2, "sodium_audit",
             "Week {w} — Sodium Audit Challenge",
             "sodium food label reading hypertension high sodium Malaysian foods audit",
             "auditing 5 commonly used condiments and packaged foods at home for sodium content"),
            (3, "stress_checkin",
             "Week {w} — Daily Stress Check-In",
             "stress monitoring mood BP hypertension daily habit awareness",
             "a 2-min daily stress rating (1-10) + trigger note, to identify BP-driving stressors"),
            (4, "weekly_bp_review",
             "Week {w} — Weekly BP Trend Review",
             "blood pressure trend analysis hypertension progress dietary lifestyle response",
             "reviewing 4 weeks of BP readings: identifying patterns, diet + exercise correlations, progress"),
        ],
    },
    "CKD": {
        "condition_tags": ["Chronic Kidney Disease"],
        "E": [
            (1, "gentle_mobility",
             "Week {w} — Gentle Mobility for Kidney Patients",
             "exercise CKD chronic kidney disease safety gentle mobility fatigue management",
             "very gentle range-of-motion and mobility exercises safe for CKD, energy conservation principles, "
             "when to rest vs. push through fatigue"),
            (2, "seated_exercise",
             "Week {w} — Seated Exercise Routine",
             "seated exercise chair workout CKD chronic kidney disease anaemia fatigue",
             "a 15-min seated exercise circuit for CKD patients with fatigue or mobility issues, "
             "including arm raises, seated marching, ankle rotations"),
            (3, "light_walking",
             "Week {w} — Light Progressive Walking",
             "walking CKD kidney disease anaemia fatigue blood pressure exercise tolerance",
             "a progressive walking programme for CKD starting at 10 min: managing anaemia-related fatigue, "
             "monitoring for oedema and shortness of breath"),
            (4, "balance_safety",
             "Week {w} — Balance and Fall Prevention",
             "balance training fall prevention CKD kidney disease elderly neuropathy",
             "balance exercises to reduce fall risk in CKD (tandem stand, single-leg stand with support), "
             "footwear and home safety tips"),
        ],
        "K": [
            (1, "understanding_ckd",
             "Week {w} — Understanding Chronic Kidney Disease",
             "chronic kidney disease CKD eGFR stages kidneys filtration function Malaysia",
             "what eGFR stages mean (1-5), how kidneys filter waste, and what declining function means for diet in Malaysia"),
            (2, "diet_kidneys",
             "Week {w} — How Diet Affects Your Kidneys",
             "kidney diet protein potassium phosphorus sodium CKD nutrition impact",
             "how protein, potassium, phosphorus, and sodium each stress or protect kidneys, with Malaysian food examples"),
            (3, "fluid_kidneys",
             "Week {w} — Fluid Balance and CKD",
             "fluid restriction CKD oedema fluid overload signs measurement urine output",
             "why fluid restriction matters in CKD, how to measure daily intake, signs of fluid overload (ankle swelling, breathlessness)"),
            (4, "ckd_progression",
             "Week {w} — Slowing CKD Progression",
             "CKD progression slowing blood pressure diabetes control diet eGFR",
             "evidence-based strategies to slow CKD: BP < 130/80, HbA1c < 7%, low-protein diet, RAAS inhibitors"),
        ],
        "A": [
            (1, "fluid_tracking",
             "Week {w} — Daily Fluid Intake Tracker",
             "fluid intake tracking CKD kidney disease restriction daily habit",
             "setting up a daily fluid tracking habit using a marked water bottle, converting common drinks to ml"),
            (2, "daily_weight",
             "Week {w} — Daily Weight Monitoring",
             "weight monitoring fluid retention CKD oedema daily morning weigh-in",
             "daily morning weigh-in to detect fluid retention early: what gain over 2 days should trigger a call to clinic"),
            (3, "kidney_food_diary",
             "Week {w} — Kidney-Safe Food Diary",
             "food diary CKD kidney disease potassium phosphorus sodium tracking identification",
             "food diary focused on 3 key minerals: marking high-K, high-P, high-Na foods daily"),
            (4, "lab_tracker",
             "Week {w} — Understanding Your Lab Values",
             "CKD lab values eGFR creatinine potassium phosphorus bicarbonate monitoring",
             "a patient-friendly explanation of 5 key CKD lab values, what trends mean, and what to report to doctor"),
        ],
    },
    "Cardiac": {
        "condition_tags": ["Ischaemic Heart Disease", "Heart Failure", "Post-CABG"],
        "E": [
            (1, "cardiac_walk_phase1",
             "Week {w} — Phase 1 Cardiac Walking Programme",
             "cardiac rehabilitation phase 1 walking post-CABG heart failure exercise safe",
             "Phase 1 cardiac rehab: 10-15 min flat-ground walking at RPE 9-11 (very light), "
             "pulse monitoring, stop-criteria, temperature safety in Malaysian climate"),
            (2, "cardiac_walk_phase2",
             "Week {w} — Phase 2 Cardiac Walking Progression",
             "cardiac rehab phase 2 walking exercise progression heart disease safe",
             "Progressing to 20-25 min at RPE 11-13 (light-moderate), "
             "interval approach (walk 5, rest 1), Borg scale use, warning signs"),
            (3, "upper_body_gentle",
             "Week {w} — Gentle Upper Body Movements",
             "upper body exercise cardiac patients heart failure seated arm movements circulation",
             "gentle seated upper-body movements (shoulder circles, arm raises < shoulder height) "
             "to improve circulation without raising cardiac demand significantly"),
            (4, "breathing_cardiac",
             "Week {w} — Breathing Exercises for Heart Health",
             "pursed lip breathing diaphragmatic breathing heart failure dyspnoea cardiac",
             "pursed-lip breathing and diaphragmatic breathing to reduce dyspnoea, "
             "improve oxygen efficiency, and calm sympathetic activation in heart failure"),
        ],
        "K": [
            (1, "understanding_heart",
             "Week {w} — Understanding Your Heart Condition",
             "heart disease ischaemic heart failure ejection fraction pathophysiology Malaysia",
             "what IHD or heart failure means in plain language, what ejection fraction is, "
             "and why diet and activity matter for recovery"),
            (2, "cholesterol_heart",
             "Week {w} — Cholesterol and Your Heart",
             "cholesterol LDL HDL triglycerides atherosclerosis plaque cardiac Malaysia",
             "how LDL deposits in arteries, what raises and lowers LDL, "
             "which Malaysian foods are worst (santan, ghee, offal) and best (fish, oats)"),
            (3, "cardiac_medications",
             "Week {w} — Your Heart Medications Explained",
             "statin aspirin beta blocker ACE inhibitor ARNI cardiac medication food interaction",
             "plain-language explanation of common cardiac medications, why stopping them is dangerous, "
             "and key food interactions (grapefruit with statins, vitamin K with warfarin)"),
            (4, "warning_signs",
             "Week {w} — Warning Signs and When to Call for Help",
             "chest pain angina heart failure warning signs emergency worsening symptoms",
             "recognising red-flag symptoms (new chest pain, sudden breathlessness, leg swelling worsening) "
             "and the exact action to take (ambulance vs. clinic)"),
        ],
        "A": [
            (1, "pulse_log",
             "Week {w} — Daily Pulse and Symptom Log",
             "resting heart rate pulse symptom log cardiac daily monitoring breathlessness fatigue",
             "daily morning resting pulse + symptom check (breathlessness, ankle swelling, fatigue rating)"),
            (2, "activity_tolerance",
             "Week {w} — Activity Tolerance Journal",
             "activity tolerance cardiac heart failure functional capacity daily living log",
             "logging which daily activities cause symptoms, to document improving tolerance over weeks"),
            (3, "medication_adherence",
             "Week {w} — Medication Adherence Tracker",
             "medication adherence cardiac statin antiplatelet compliance tracking habit",
             "simple daily medication tick-off chart, what to do for missed doses, "
             "and why every dose matters for cardiac outcomes"),
            (4, "symptom_review",
             "Week {w} — 4-Week Cardiac Symptom Review",
             "cardiac symptom trend review heart failure NYHA functional class weight",
             "4-week symptom review: weight trend, activity tolerance progression, and when to escalate to doctor"),
        ],
    },
    "PCOS": {
        "condition_tags": ["Polycystic Ovary Syndrome (PCOS)", "Insulin Resistance"],
        "E": [
            (1, "cardio_pcos",
             "Week {w} — Cardio Foundation for PCOS",
             "aerobic cardio exercise PCOS insulin resistance hormones benefit 150 minutes",
             "a 25-min moderate cardio programme for PCOS — how it improves insulin sensitivity, "
             "reduces androgen levels, and supports weight management"),
            (2, "resistance_pcos",
             "Week {w} — Resistance Training for PCOS",
             "resistance strength training PCOS insulin sensitivity lean muscle androgens",
             "why building muscle is especially beneficial for PCOS: improves insulin sensitivity and "
             "reduces testosterone-driven symptoms, with a beginner resistance programme"),
            (3, "light_hiit",
             "Week {w} — Light HIIT for Insulin Sensitivity",
             "HIIT interval training PCOS insulin sensitivity blood sugar exercise benefit",
             "a beginner 20-min light HIIT (30-sec effort / 90-sec rest × 8 rounds) "
             "to maximise insulin-sensitising effects without overtraining cortisol spike in PCOS"),
            (4, "yoga_pcos",
             "Week {w} — Yoga and Stress Reduction for PCOS",
             "yoga stress cortisol PCOS hormonal balance relaxation parasympathetic",
             "yoga sequences to lower cortisol and improve hormonal balance in PCOS: "
             "restorative poses, breathwork, and pelvic-focused stretches"),
        ],
        "K": [
            (1, "understanding_pcos",
             "Week {w} — Understanding PCOS",
             "PCOS polycystic ovary syndrome pathophysiology hormones Malaysia prevalence diagnosis",
             "what PCOS is, how insulin resistance drives hyperandrogenism, diagnosis criteria, "
             "and why it is so common in Malaysian women"),
            (2, "insulin_hormones",
             "Week {w} — Insulin, Hormones, and PCOS",
             "insulin resistance androgens LH FSH ratio PCOS hormones cycle disruption",
             "the LH/FSH ratio disruption in PCOS, how high insulin triggers ovarian androgen production, "
             "and why diet is a first-line treatment"),
            (3, "diet_pcos",
             "Week {w} — The Best Diet for PCOS",
             "low GI diet anti-inflammatory PCOS weight loss insulin sensitivity evidence",
             "evidence review: low-GI diet vs Mediterranean vs low-carb for PCOS, "
             "with Malaysian-friendly meal swaps"),
            (4, "stress_sleep_pcos",
             "Week {w} — Stress, Sleep, and PCOS",
             "cortisol stress sleep quality PCOS hormonal worsening insulin resistance",
             "how chronic stress and poor sleep elevate cortisol → worsen insulin resistance → worsen PCOS: "
             "practical sleep hygiene and stress management"),
        ],
        "A": [
            (1, "cycle_tracking",
             "Week {w} — Menstrual Cycle Tracking",
             "menstrual cycle tracking PCOS irregular periods app symptom log",
             "setting up a period and symptom tracking habit (app or paper): cycle length, spotting, "
             "acne, mood to detect improvement over time"),
            (2, "food_mood_diary",
             "Week {w} — Food and Mood Diary",
             "food diary mood energy PCOS insulin hormones tracking pattern recognition",
             "tracking food choices alongside mood, energy, and cravings to identify insulin-driven patterns"),
            (3, "exercise_energy_log",
             "Week {w} — Exercise and Energy Tracker",
             "exercise energy cravings blood sugar PCOS improvement self-monitoring",
             "logging pre- and post-exercise energy + hunger/cravings to see insulin-sensitising effect"),
            (4, "monthly_symptom_review",
             "Week {w} — Monthly PCOS Symptom Review",
             "PCOS symptom review acne hirsutism fatigue mood cycle weight improvement",
             "monthly review of PCOS symptom domains: cycle regularity, skin, energy, weight, mood — noting trends"),
        ],
    },
    "Dyslipidaemia": {
        "condition_tags": ["Dyslipidaemia", "Hypercholesterolaemia"],
        "E": [
            (1, "aerobic_lipids",
             "Week {w} — Aerobic Exercise and Your Lipid Profile",
             "aerobic exercise LDL HDL triglycerides dyslipidaemia cholesterol reduction mechanism",
             "how aerobic exercise lowers triglycerides and raises HDL: a 25-min walking/cycling programme "
             "with target heart rate zone for lipid benefit"),
            (2, "step_programme",
             "Week {w} — Progressive Daily Step Programme",
             "daily walking steps HDL cholesterol triglyceride improvement goal 7000",
             "progressive daily walking building to 7000-8000 steps/day to improve lipid profile, "
             "with Malaysian-accessible tracking options"),
            (3, "resistance_lipids",
             "Week {w} — Resistance Training for Cholesterol",
             "resistance strength training muscle mass LDL HDL triglycerides metabolic",
             "how resistance training reduces LDL and visceral fat, improves metabolic rate: "
             "a beginner 2×/week programme"),
            (4, "cardio_endurance",
             "Week {w} — Building Cardio Endurance",
             "cardiorespiratory fitness VO2max cholesterol cardiovascular risk dyslipidaemia",
             "4-week cardio progression overview: how VO2max improvement reduces LDL, raises HDL, "
             "and cuts cardiovascular event risk"),
        ],
        "K": [
            (1, "understanding_lipids",
             "Week {w} — Understanding Your Lipid Panel",
             "LDL HDL triglycerides total cholesterol lipid panel interpretation targets Malaysia",
             "what each number means (LDL < 2.6, HDL > 1.0, TG < 1.7), "
             "why total cholesterol alone is misleading, and what optimal looks like"),
            (2, "diet_cholesterol",
             "Week {w} — Diet and Cholesterol",
             "saturated fat trans fat dietary cholesterol LDL raising lowering foods Malaysia",
             "which Malaysian foods raise LDL (santan, ghee, palm oil, processed meat) "
             "and which lower it (oats, psyllium, omega-3 fish, legumes)"),
            (3, "statin_lifestyle",
             "Week {w} — Statins and Lifestyle Together",
             "statin atorvastatin rosuvastatin diet exercise lifestyle dyslipidaemia combination",
             "why lifestyle changes still matter on statins, how they work synergistically, "
             "statin side effects, and grapefruit/alcohol interactions"),
            (4, "cv_risk",
             "Week {w} — Cholesterol and Cardiovascular Risk",
             "LDL cholesterol cardiovascular risk atherosclerosis plaque rupture Malaysia",
             "how LDL builds plaque, what causes plaque rupture (heart attack), "
             "and how reducing LDL by 1 mmol/L cuts risk"),
        ],
        "A": [
            (1, "food_label_audit",
             "Week {w} — Saturated Fat Food Label Audit",
             "food label reading saturated fat trans fat cholesterol Malaysia packaged food",
             "auditing 5 daily-use packaged products for saturated fat content — "
             "calculating how much comes from each"),
            (2, "cooking_tracker",
             "Week {w} — Cooking Method Tracker",
             "cooking method healthy cholesterol steaming grilling baking vs frying switch",
             "tracking this week's cooking methods: how many fried vs. healthier methods, "
             "and identifying one easy swap"),
            (3, "step_goal",
             "Week {w} — Weekly Step Goal Challenge",
             "daily steps aerobic physical activity HDL benefit walking challenge",
             "7-day step challenge: daily goal + check-in, HDL-raising effect of consistent steps"),
            (4, "lipid_trend",
             "Week {w} — Tracking Your Lipid Results Over Time",
             "LDL HDL triglycerides monitoring trend dyslipidaemia progress statin lifestyle",
             "building a simple lipid result log to see trends, understand what changes mean, "
             "and what to tell your doctor"),
        ],
    },
    "General": {
        "condition_tags": [],
        "E": [
            (1, "beginner_fitness",
             "Week {w} — Beginner Fitness Foundation",
             "beginner exercise aerobic walking 150 minutes weekly general wellness",
             "a 3-day beginner programme: 25-min walks + basic stretching, "
             "progressing from sedentary to WHO-recommended 150 min/week"),
            (2, "cardio_build",
             "Week {w} — Building Cardiovascular Fitness",
             "aerobic cardio fitness VO2max cardiorespiratory endurance general wellness",
             "week 2 progression: brisk walking, cycling, or swimming at moderate intensity "
             "to build aerobic base and metabolic health"),
            (3, "strength_basics",
             "Week {w} — Bodyweight Strength Basics",
             "bodyweight exercise strength training squats push-ups lunges general wellness",
             "a 2×/week beginner bodyweight circuit (squat, hinge, push, pull, core) "
             "no equipment, home-friendly for Malaysian adults"),
            (4, "active_recovery",
             "Week {w} — Flexibility and Active Recovery",
             "stretching flexibility yoga active recovery mobility general wellness",
             "full-body stretching + light yoga for active recovery: "
             "why rest days matter, mobility for long-term joint health"),
        ],
        "K": [
            (1, "nutrition_basics",
             "Week {w} — Nutrition Fundamentals",
             "balanced diet macronutrients protein carbohydrate fat micronutrients Malaysia",
             "the basics of balanced nutrition: macros, fibre, micronutrients, "
             "and how Malaysian food can meet or miss the mark"),
            (2, "exercise_science",
             "Week {w} — Why Regular Exercise Is Essential",
             "exercise benefits physical activity heart brain metabolic mental health longevity Malaysia",
             "the evidence: 150 min/week moderate exercise reduces all-cause mortality, "
             "mechanism across cardiovascular, metabolic, and mental health"),
            (3, "sleep_health",
             "Week {w} — Sleep and Your Health",
             "sleep quality duration health metabolism weight cortisol immune function",
             "how poor sleep drives weight gain, impairs insulin sensitivity, weakens immunity, "
             "and harms mental health — practical sleep hygiene for Malaysians"),
            (4, "stress_disease",
             "Week {w} — Chronic Stress and Disease",
             "chronic stress cortisol inflammation metabolic disease cardiovascular risk lifestyle",
             "how long-term stress elevates cortisol → chronic inflammation → increased risk of diabetes, "
             "heart disease, and depression; evidence-based interventions"),
        ],
        "A": [
            (1, "step_challenge",
             "Week {w} — 7-Day Step Challenge",
             "daily steps 8000 10000 walking activity wellness habit tracking",
             "a 7-day progressive step challenge: start at personal baseline, add 500 steps/day, "
             "aiming toward 8000-10000 by day 7"),
            (2, "hydration_habit",
             "Week {w} — Daily Hydration Habit",
             "water intake hydration 2L daily tracking health Malaysia climate heat",
             "tracking daily water intake toward 2-2.5L/day in Malaysian heat: "
             "visual tracker, replacing sugary drinks, recognising dehydration signs"),
            (3, "sleep_log",
             "Week {w} — Sleep Quality Log",
             "sleep tracking bedtime wake time quality rating wellness habit",
             "7-day sleep log: bedtime, wake time, quality rating 1-5, and one habit to improve it"),
            (4, "wellness_checkin",
             "Week {w} — 4-Week Wellness Check-In",
             "wellness review energy mood weight activity sleep nutrition progress goals",
             "structured 4-week review across 5 domains: steps, sleep, nutrition, stress, and weight — "
             "setting realistic next-month goals"),
        ],
    },
    # 2026-09-07 addition: 6 new groups added alongside the original 7 (client
    # request, added not replaced — PCOS/T2DM/HTN/CKD/Cardiac/Dyslipidaemia/
    # General unchanged). Developer-drafted like every other group here —
    # PROVISIONAL until reviewed; nothing reaches a patient without
    # POST /content/materials/{id}/approve (same is_active=False gate as
    # everything else). Add matching CONDITION_MAP keywords in
    # scripts/generate_content.py if real patient condition data should
    # auto-match to these.
    "Mental Health": {
        "condition_tags": ["Depression", "Anxiety"],
        "E": [
            (1, "movement_mood",
             "Week {w} — Movement for Mood",
             "exercise depression anxiety mood endorphins physical activity benefit",
             "a gentle 20-min walking or light-cardio routine and the evidence for exercise's "
             "antidepressant effect via endorphins and BDNF"),
            (2, "outdoor_activity",
             "Week {w} — Outdoor Activity and Sunlight",
             "outdoor exercise sunlight vitamin D mood circadian rhythm",
             "why outdoor movement (vs indoor) adds a mood benefit through light exposure and "
             "circadian regulation, with a simple outdoor walking plan"),
            (3, "gentle_strength",
             "Week {w} — Gentle Strength for Resilience",
             "resistance training mental health self-efficacy mood anxiety",
             "a beginner bodyweight strength routine and evidence linking resistance training to "
             "reduced anxiety and improved self-efficacy"),
            (4, "breath_movement",
             "Week {w} — Breath-Led Movement",
             "yoga tai chi breathing exercise parasympathetic anxiety relaxation",
             "slow, breath-led movement (yoga/tai chi style) to activate the parasympathetic "
             "nervous system and reduce anxiety symptoms"),
        ],
        "K": [
            (1, "understanding_mental_health",
             "Week {w} — Understanding Depression and Anxiety",
             "depression anxiety symptoms diagnosis cardiac patients prevalence",
             "what depression and anxiety are, how common they are after a cardiac diagnosis, "
             "and why they matter for heart health"),
            (2, "heart_mind_link",
             "Week {w} — The Heart-Mind Connection",
             "depression cardiovascular disease bidirectional risk inflammation",
             "the well-established bidirectional link between depression/anxiety and cardiovascular "
             "disease — inflammation, behaviour, and shared risk"),
            (3, "when_to_seek_help",
             "Week {w} — When and How to Seek Help",
             "mental health help seeking therapy counselling Malaysia resources",
             "recognising when symptoms need professional support, and how to access "
             "counselling/psychiatric care in Malaysia (public and private pathways)"),
            (4, "myths_stigma",
             "Week {w} — Myths and Stigma Around Mental Health",
             "mental health stigma myths Malaysia misconceptions",
             "addressing common myths and stigma around mental health treatment in a Malaysian "
             "context, and why seeking help is a sign of strength not weakness"),
        ],
        "A": [
            (1, "mood_tracker",
             "Week {w} — Daily Mood Tracker",
             "mood tracking daily log mental health pattern",
             "a simple daily 1-5 mood rating log to notice patterns and triggers over a week"),
            (2, "gratitude_journal",
             "Week {w} — Gratitude and Reflection Journal",
             "gratitude journaling mental health wellbeing practice",
             "a short daily gratitude/reflection journaling habit and the evidence for its effect on mood"),
            (3, "social_connection_log",
             "Week {w} — Social Connection Check-In",
             "social connection isolation support mental health tracking",
             "tracking meaningful social contact each day and noticing the link between "
             "connection and mood"),
            (4, "monthly_mental_health_review",
             "Week {w} — Monthly Mental Health Review",
             "mental health review mood trend symptoms professional support",
             "a 4-week review of mood trends and symptoms, with guidance on when to bring this "
             "to a doctor or counsellor"),
        ],
    },
    "Stress Management": {
        "condition_tags": ["Chronic Stress"],
        "E": [
            (1, "walking_destress",
             "Week {w} — Walking to De-Stress",
             "walking exercise stress reduction cortisol light activity",
             "a simple daily walking habit and how light aerobic movement lowers cortisol "
             "and stress hormones"),
            (2, "progressive_relaxation",
             "Week {w} — Progressive Muscle Relaxation",
             "progressive muscle relaxation stress technique physical tension",
             "a guided progressive muscle relaxation routine to physically release stress-held tension"),
            (3, "stretch_break",
             "Week {w} — Desk and Stretch Breaks",
             "desk stretching sedentary stress break workplace",
             "short stretch breaks through the day to interrupt sedentary stress build-up, "
             "especially for office workers"),
            (4, "active_stress_release",
             "Week {w} — Active Stress Release",
             "physical activity stress release exercise intensity mood",
             "moderate-intensity activity (cycling, swimming, brisk walking) as an active "
             "stress-release outlet, and matching intensity to how stressed you feel"),
        ],
        "K": [
            (1, "understanding_stress_response",
             "Week {w} — Understanding the Stress Response",
             "stress response cortisol fight flight physiology",
             "the physiology of the stress response (cortisol, fight-or-flight) and why "
             "chronic activation is harmful"),
            (2, "stress_heart_link",
             "Week {w} — Stress and Heart Disease",
             "chronic stress cardiovascular disease blood pressure inflammation risk",
             "how chronic stress raises blood pressure, promotes inflammation, and is an "
             "independent cardiovascular risk factor"),
            (3, "breathing_techniques",
             "Week {w} — Breathing Techniques for Stress",
             "diaphragmatic breathing box breathing stress technique evidence",
             "evidence-based breathing techniques (diaphragmatic, box breathing) and how to "
             "practise them"),
            (4, "time_boundaries",
             "Week {w} — Time Management and Boundaries",
             "time management boundaries workload stress prevention",
             "practical time-management and boundary-setting strategies to reduce chronic "
             "workload stress"),
        ],
        "A": [
            (1, "stress_trigger_log",
             "Week {w} — Stress Trigger Log",
             "stress trigger tracking log pattern identification",
             "a daily log of stress triggers and intensity to identify patterns worth addressing"),
            (2, "relaxation_practice_tracker",
             "Week {w} — Relaxation Practice Tracker",
             "relaxation practice tracking breathing meditation habit",
             "tracking a daily relaxation practice (breathing, meditation, or stretching) to "
             "build consistency"),
            (3, "energy_stress_diary",
             "Week {w} — Energy and Stress Diary",
             "energy level stress diary daily tracking correlation",
             "logging energy levels alongside stress ratings to spot the connection over a week"),
            (4, "monthly_stress_review",
             "Week {w} — Monthly Stress Review",
             "stress review monthly trend coping strategies effectiveness",
             "a 4-week review of stress trends and which coping strategies worked, adjusting "
             "the plan going forward"),
        ],
    },
    "Sleep": {
        "condition_tags": ["Sleep Disturbance", "Insomnia"],
        "E": [
            (1, "daytime_activity_sleep",
             "Week {w} — Daytime Activity for Better Sleep",
             "daytime exercise sleep quality circadian rhythm timing",
             "how regular daytime activity improves night-time sleep quality, and the right "
             "timing (avoiding late-evening vigorous exercise)"),
            (2, "evening_winddown",
             "Week {w} — Evening Wind-Down Movement",
             "gentle evening stretching wind down sleep preparation",
             "a gentle 10-min evening stretching routine as part of a wind-down ritual before bed"),
            (3, "morning_light_walk",
             "Week {w} — Morning Light Walk",
             "morning sunlight walk circadian rhythm melatonin sleep",
             "a short morning walk to anchor the circadian rhythm and improve night-time "
             "melatonin release"),
            (4, "weekend_consistency",
             "Week {w} — Keeping Activity Consistent on Weekends",
             "weekend activity consistency sleep schedule routine",
             "why keeping activity and wake times consistent on weekends helps stabilise sleep, "
             "avoiding 'social jet lag'"),
        ],
        "K": [
            (1, "sleep_architecture",
             "Week {w} — Understanding Sleep Stages",
             "sleep stages architecture REM deep sleep cycle",
             "what happens during a night's sleep (light, deep, REM stages) and why each "
             "matters for health"),
            (2, "sleep_heart_link",
             "Week {w} — Sleep and Heart Health",
             "poor sleep cardiovascular disease blood pressure risk evidence",
             "the evidence linking poor sleep duration/quality to hypertension, weight gain, "
             "and cardiovascular risk"),
            (3, "sleep_hygiene",
             "Week {w} — Sleep Hygiene Fundamentals",
             "sleep hygiene bedroom environment habits caffeine screens",
             "practical sleep hygiene: bedroom environment, caffeine timing, screen use, and "
             "consistent schedules"),
            (4, "when_to_see_doctor_sleep",
             "Week {w} — When Sleep Problems Need a Doctor",
             "sleep apnea insomnia snoring doctor referral warning signs",
             "warning signs that sleep problems need medical assessment (e.g. loud snoring with "
             "pauses suggesting sleep apnea) and why untreated sleep apnea is a cardiac risk"),
        ],
        "A": [
            (1, "sleep_diary",
             "Week {w} — 7-Day Sleep Diary",
             "sleep diary bedtime waketime quality tracking",
             "a 7-day sleep diary logging bedtime, wake time, and subjective quality"),
            (2, "caffeine_screen_log",
             "Week {w} — Caffeine and Screen-Time Log",
             "caffeine intake screen time evening tracking sleep",
             "tracking afternoon/evening caffeine and screen use to see their effect on sleep "
             "that night"),
            (3, "winddown_routine_tracker",
             "Week {w} — Wind-Down Routine Tracker",
             "wind down routine bedtime habit consistency tracking",
             "building and tracking a consistent 30-min wind-down routine before bed"),
            (4, "monthly_sleep_review",
             "Week {w} — Monthly Sleep Review",
             "sleep review monthly trend quality improvement",
             "a 4-week review of sleep duration/quality trends and which changes helped most"),
        ],
    },
    "Atrial Fibrillation": {
        "condition_tags": ["Atrial Fibrillation"],
        "E": [
            (1, "safe_cardio_afib",
             "Week {w} — Safe Cardio with AFib",
             "atrial fibrillation exercise safe cardio intensity guidance",
             "general guidance on light-to-moderate cardio activity with atrial fibrillation, and "
             "the importance of clearing intensity with your cardiologist first"),
            (2, "walking_progression_afib",
             "Week {w} — Walking Progression",
             "walking programme atrial fibrillation pacing gradual",
             "a gradual walking progression plan and pacing by how you feel, not just a fixed target"),
            (3, "strength_light_afib",
             "Week {w} — Light Strength Work",
             "light resistance training atrial fibrillation general guidance",
             "general, non-strenuous strength-maintenance movement and why very heavy "
             "straining/Valsalva-type effort is generally avoided"),
            (4, "recognising_limits",
             "Week {w} — Recognising Your Limits During Activity",
             "atrial fibrillation exercise stop signs symptoms activity",
             "how to recognise symptoms that mean it's time to stop and rest (palpitations, "
             "dizziness, breathlessness) during any activity"),
        ],
        "K": [
            (1, "understanding_afib",
             "Week {w} — Understanding Atrial Fibrillation",
             "atrial fibrillation pathophysiology irregular heart rhythm explanation",
             "what atrial fibrillation is, how the irregular rhythm happens, and why it matters "
             "for stroke risk"),
            (2, "afib_stroke_risk",
             "Week {w} — AFib and Stroke Risk",
             "atrial fibrillation stroke risk anticoagulation general education",
             "why AFib raises stroke risk and the general role of anticoagulation — never "
             "suggesting starting/stopping/adjusting any medication"),
            (3, "afib_triggers",
             "Week {w} — Common AFib Triggers",
             "atrial fibrillation triggers alcohol caffeine sleep stress general",
             "commonly recognised triggers (alcohol, poor sleep, stress, excess caffeine) that "
             "can worsen AFib episodes"),
            (4, "living_well_afib",
             "Week {w} — Living Well with AFib",
             "atrial fibrillation lifestyle management quality of life general",
             "general lifestyle factors (weight, blood pressure, sleep apnea treatment) shown "
             "to help AFib management long-term"),
        ],
        "A": [
            (1, "pulse_rhythm_log",
             "Week {w} — Pulse and Rhythm Log",
             "atrial fibrillation pulse tracking symptom log daily",
             "a daily log of resting pulse feel (regular/irregular) and any symptoms, to share "
             "with your cardiologist"),
            (2, "episode_diary",
             "Week {w} — Episode Diary",
             "atrial fibrillation episode diary trigger tracking",
             "logging any felt episodes alongside possible triggers (caffeine, alcohol, stress, "
             "poor sleep) that day"),
            (3, "medication_adherence_afib",
             "Week {w} — Medication Adherence Tracker",
             "atrial fibrillation medication adherence anticoagulant tracking",
             "a simple daily tick-off for anticoagulant/rate-control medication and why "
             "consistency matters for stroke prevention"),
            (4, "monthly_afib_review",
             "Week {w} — Monthly AFib Review",
             "atrial fibrillation monthly review episode trend doctor",
             "a 4-week review of episode frequency/triggers to discuss with your cardiologist "
             "at the next visit"),
        ],
    },
    "Heart Failure": {
        "condition_tags": ["Heart Failure"],
        "E": [
            (1, "cardiac_rehab_hf",
             "Week {w} — Cardiac Rehab-Style Movement for HF",
             "heart failure exercise cardiac rehabilitation supervised gradual",
             "general education on structured, gradual cardiac-rehab-style activity for heart "
             "failure, and the importance of a supervised programme"),
            (2, "breathing_paced_activity",
             "Week {w} — Pacing Activity with Breathlessness",
             "heart failure breathlessness pacing activity energy conservation",
             "energy-conservation and pacing techniques for daily activity when breathlessness "
             "is a limiting symptom"),
            (3, "seated_gentle_hf",
             "Week {w} — Seated and Gentle Movement Options",
             "heart failure seated exercise low intensity gentle safe",
             "low-intensity seated or standing movement options for days with more fatigue, "
             "without pushing through red-flag symptoms"),
            (4, "progress_tolerance_hf",
             "Week {w} — Noticing Activity Tolerance Changes",
             "heart failure functional capacity NYHA activity tolerance change",
             "why tracking activity tolerance over time matters in heart failure, and when a "
             "change should prompt a doctor visit"),
        ],
        "K": [
            (1, "understanding_hf",
             "Week {w} — Understanding Heart Failure",
             "heart failure pathophysiology ejection fraction explanation",
             "what heart failure means, ejection fraction in plain language, and common types "
             "(reduced vs preserved)"),
            (2, "fluid_sodium_hf",
             "Week {w} — Fluid and Sodium Awareness",
             "heart failure fluid restriction sodium awareness general education",
             "why fluid and sodium intake matter in heart failure, at a general educational "
             "level — exact limits always set by the patient's own care team"),
            (3, "warning_signs_hf",
             "Week {w} — Warning Signs That Need Urgent Attention",
             "heart failure warning signs weight gain swelling breathlessness emergency",
             "the classic HF red flags (rapid weight gain, worsening swelling, increasing "
             "breathlessness) and when to seek urgent care"),
            (4, "medication_importance_hf",
             "Week {w} — Why Heart Failure Medications Matter",
             "heart failure medication importance adherence general education",
             "plain-language explanation of why heart failure medication classes matter and "
             "the danger of stopping them without medical guidance"),
        ],
        "A": [
            (1, "daily_weight_log",
             "Week {w} — Daily Weight Log",
             "heart failure daily weight monitoring fluid retention tracking",
             "a daily morning weight log (same time, same conditions) — the single most "
             "important heart-failure self-monitoring habit, with a note to flag any rapid "
             "gain to the care team"),
            (2, "symptom_traffic_light",
             "Week {w} — Symptom Traffic-Light Log",
             "heart failure symptom traffic light zone tool tracking",
             "a simple green/yellow/red symptom traffic-light log (breathlessness, swelling, "
             "fatigue) to make it easy to know when to act"),
            (3, "medication_adherence_hf",
             "Week {w} — Medication Adherence Tracker",
             "heart failure medication adherence tracking daily habit",
             "a daily medication tick-off chart and what to do about a missed dose"),
            (4, "monthly_hf_review",
             "Week {w} — Monthly Heart Failure Review",
             "heart failure monthly review weight symptom trend doctor",
             "a 4-week review of weight and symptom trends to bring to the next care-team "
             "appointment"),
        ],
    },
    "CVD Risk Management": {
        "condition_tags": ["Cardiovascular Risk"],
        "E": [
            (1, "aerobic_base_cvd",
             "Week {w} — Building an Aerobic Base",
             "cardiovascular risk reduction aerobic exercise 150 minutes evidence",
             "the WHO-recommended 150 min/week moderate aerobic activity target and how it "
             "lowers overall CVD risk"),
            (2, "strength_cvd_risk",
             "Week {w} — Strength Training for Risk Reduction",
             "resistance training cardiovascular risk reduction metabolic benefit",
             "evidence for 2x/week resistance training reducing cardiovascular risk via "
             "metabolic and blood-pressure effects"),
            (3, "reduce_sedentary_time",
             "Week {w} — Reducing Sedentary Time",
             "sedentary behaviour cardiovascular risk breaking up sitting",
             "why breaking up long sitting periods independently reduces cardiovascular risk, "
             "with practical every-30-min movement cues"),
            (4, "risk_appropriate_intensity",
             "Week {w} — Matching Intensity to Your Risk Profile",
             "exercise intensity cardiovascular risk stratification safe progression",
             "how exercise intensity should be matched to individual risk profile, and general "
             "safe-progression principles"),
        ],
        "K": [
            (1, "understanding_cvd_risk_factors",
             "Week {w} — Understanding Your CVD Risk Factors",
             "cardiovascular risk factors blood pressure cholesterol smoking diabetes overview",
             "an overview of the major modifiable CVD risk factors (blood pressure, cholesterol, "
             "smoking, diabetes, weight, inactivity)"),
            (2, "risk_score_explained",
             "Week {w} — How Risk Scores Work",
             "cardiovascular risk score calculation general explanation Framingham",
             "a plain-language explanation of how CVD risk scoring generally works and why "
             "it's a starting point, not a diagnosis, for a doctor conversation"),
            (3, "diet_cvd_risk",
             "Week {w} — Diet and Cardiovascular Risk",
             "heart healthy diet cardiovascular risk reduction evidence Malaysia",
             "evidence-based dietary patterns (Mediterranean-style, DASH) shown to reduce "
             "cardiovascular risk, with Malaysian-friendly examples"),
            (4, "smoking_alcohol_cvd",
             "Week {w} — Smoking, Alcohol, and CVD Risk",
             "smoking alcohol cardiovascular risk cessation reduction general",
             "how smoking and excess alcohol independently raise cardiovascular risk, and the "
             "general benefit of cutting down or quitting"),
        ],
        "A": [
            (1, "risk_factor_checklist",
             "Week {w} — Personal Risk Factor Checklist",
             "cardiovascular risk factor checklist self assessment tracking",
             "a self-assessment checklist of known risk factors to review and discuss with a doctor"),
            (2, "activity_minutes_tracker",
             "Week {w} — Weekly Activity Minutes Tracker",
             "weekly activity minutes tracking 150 minutes goal cardiovascular",
             "tracking weekly moderate-activity minutes toward the 150-min target"),
            (3, "lifestyle_habit_tracker",
             "Week {w} — Daily Lifestyle Habit Tracker",
             "lifestyle habit tracker diet activity smoking cardiovascular risk",
             "a simple daily tick-off for the key lifestyle habits that influence CVD risk "
             "(activity, diet quality, no smoking)"),
            (4, "monthly_risk_review",
             "Week {w} — Monthly Risk Review",
             "cardiovascular risk monthly review progress doctor discussion",
             "a 4-week review of habit trends and a prompt to discuss risk-score changes at "
             "the next doctor visit"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Build flat niche case list from templates
# ---------------------------------------------------------------------------

def build_eka_cases(iso_week: int) -> list:
    """Return 84 niche case dicts for the given ISO week number."""
    rotation = ((iso_week - 1) % 4) + 1  # 1-4 rotation
    cases = []
    for group, gdata in _TEMPLATES.items():
        for ctype in ("E", "K", "A"):
            entries = gdata[ctype]
            slot, topic_slug, title_tmpl, rag_query, prompt_topic = entries[rotation - 1]
            cases.append({
                "group":          group,
                "condition_tags": gdata["condition_tags"],
                "content_type":   ctype,
                "week_number":    iso_week,
                "topic":          topic_slug,
                "title":          title_tmpl.format(w=iso_week),
                "rag_query":      rag_query,
                "prompt_topic":   prompt_topic,
            })
    return cases


# ---------------------------------------------------------------------------
# RAG retrieval helper (shared with generate_content.py)
# ---------------------------------------------------------------------------

def _retrieve_chunks(query: str, client_id: int, top_k: int = 8) -> str:
    from langchain_community.vectorstores import PGVector
    from vector_store import get_connection_string
    from embeddings import get_embedding_function

    conn = get_connection_string()
    emb = get_embedding_function()
    base_db = PGVector(connection_string=conn, embedding_function=emb,
                       collection_name="base_knowledge", use_jsonb=True)
    docs = base_db.similarity_search(query, k=top_k)
    try:
        client_db = PGVector(connection_string=conn, embedding_function=emb,
                             collection_name=f"client_{client_id}_knowledge", use_jsonb=True)
        seen = {d.page_content for d in docs}
        for d in client_db.similarity_search(query, k=3):
            if d.page_content not in seen:
                docs.append(d)
    except Exception:
        pass
    return "\n\n---\n\n".join(d.page_content[:800] for d in docs[:top_k])


# ---------------------------------------------------------------------------
# Type-specific LLM generation
# ---------------------------------------------------------------------------

_PERSONALIZATION_GUIDANCE = """\
Personalization level rules:
L0 (no risk, general wellness): Full spectrum; vigorous activity allowed; no clinical stop signs needed.
  Role: Coach. Tone: Performance-oriented. Knowledge topics: healthy diet, smoking harms, weight
  management, CVD prevention. Activities: step goals and structured activities allowed.
L1 (emerging/moderate risk): Structured, safety-aware; clear do/don't boundaries; moderate intensity max.
  Role: Guide. Tone: Supportive. Knowledge topics: smoking cessation, obesity prevention, LDL/HDL
  basics, preventive education. Activities: consistency-focused.
L2 (established conditions, higher CV risk): Low-intensity only; symptom monitoring required; strict stop conditions.
  Role: Protector. Tone: Cautious, reassuring. Knowledge topics: medication adherence, salt reduction,
  disease-specific education, risk reduction. Activities: ADL only; fatigue-aware; pain-aware.
L3 (high clinical risk, recent cardiac event): Medical oversight only; extremely gentle; include emergency guidance.
  Role: Gatekeeper. Tone: Clinical, calm, safety-first. Knowledge topics: emergency awareness, severe
  hypertension awareness, exercise safety, high-risk precautions. Activities: micro-movement only;
  sedentary-break reminders only.
"""

# General-education guardrail (added 2026-08-14, see docs/component_taxonomy_contract.md
# and taxonomy.COMPONENT_SCOPE): this is what changed when the weekly EKA generator was
# rebuilt after the material id=68 dietitian flag (a Knowledge item recommended lentils/
# beans — high-potassium — as a low-protein swap for CKD patients). Nothing here is
# personalized clinical advice; it's lay education that always routes specifics back to
# the patient's own care team, matching the boundary taxonomy.py enforces in live chat.
_SAFETY_GUARDRAILS = """\
Safety rules — do not violate these:
- Do NOT recommend a specific food, supplement swap, or medication change as a direct instruction
  (e.g. never say "eat X instead of Y" or "stop/reduce your medication dose"). If the topic touches
  diet or medication, describe it at a general educational level only, and explicitly tell the
  patient to confirm any specific change with their dietitian or doctor first.
- Any numeric threshold or monitoring cue you give (e.g. "call the clinic if you gain 2kg in 2 days")
  must be a well-established, widely-published self-monitoring practice, not an invented clinical
  target — and must be framed as general guidance to confirm with their care team, not a prescription.
- Never suggest a specific ingredient/food is safe or unsafe for this condition group without a
  caveat that individual restrictions (e.g. potassium, phosphorus, sodium limits) vary by patient
  and must be confirmed with their own dietitian.
"""

# Weekly EKA content is written for a condition group in general, not one patient's exact
# personalization_level — this maps each group to the level used to sample the REAL exercise
# catalog below (exercise_lookup.py), mirroring the live chat pipeline's risk-tier framing.
_GROUP_LEVEL = {
    "T2DM": "L1", "HTN": "L1", "Dyslipidaemia": "L1", "PCOS": "L1",
    "CKD": "L2", "Cardiac": "L2",
    "General": "L0",
    # 2026-09-07 additions
    "Mental Health": "L1", "Stress Management": "L1", "Sleep": "L1",
    "CVD Risk Management": "L1",
    "Atrial Fibrillation": "L2", "Heart Failure": "L2",
}


def _generate_exercise(niche: dict, chunks: str) -> dict:
    """Grounded in the REAL approved exercise-video catalog (exercise_lookup.py) —
    same source of truth the live chat 'exercise' Component uses. The LLM only
    writes short framing/why-it-helps copy about real catalog entries; it never
    invents session structure (duration, sets, warmup/cooldown, stop signs) —
    see taxonomy.COMPONENT_SCOPE["exercise"] for why that boundary exists.
    """
    from llm import call_ollama_generate
    from exercise_lookup import list_exercise_samples_for_level

    level = _GROUP_LEVEL.get(niche["group"], "L1")
    catalog = list_exercise_samples_for_level(level, per_type=2)
    if not catalog:
        return {"catalog_highlights": [], "note": "no catalog entries available for this level"}

    catalog_text = "\n".join(
        f"- {c['title']} ({c['type']}, {c['intensity_tier']} intensity, {c['body_focus']}, {c['video_duration']})"
        for c in catalog
    )

    prompt = f"""You are a patient educator writing short framing copy for a Malaysian cardiac/metabolic programme.

TOPIC: {niche["prompt_topic"]}
CONDITION GROUP: {niche["group"]}
WEEK: {niche["week_number"]}

APPROVED EXERCISE CATALOG (you may ONLY reference these exact items — never invent, rename, or add exercises, durations, or intensities not listed here):
{catalog_text}

{_SAFETY_GUARDRAILS}

{_PERSONALIZATION_GUIDANCE}

TASK: Write general, non-prescriptive framing copy for this week's theme, tying it to the catalog above. Return ONLY valid JSON — no prose, no markdown fences, and the "title" field in each highlight must be copied verbatim from the catalog above:
{{
  "framing": "1-2 sentences introducing this week's theme and why gentle/appropriate movement matters for this condition group",
  "catalog_highlights": [
    {{"title": "<verbatim title from the catalog above>", "why_it_helps": "<=25-word general benefit, no invented specifics"}},
    {{"title": "<verbatim title from the catalog above>", "why_it_helps": "<=25-word general benefit, no invented specifics"}}
  ],
  "general_safety_note": "one general reminder to stop and seek help for chest pain, severe breathlessness, or dizziness, and to check with their care team before starting anything new",
  "malaysian_context": "short, optional note on climate/home-setting practicality"
}}"""
    result = _call_and_parse(prompt, 500)
    if isinstance(result, dict) and not result.get("parse_error"):
        # Re-attach the real catalog metadata (type/intensity/duration) the LLM was
        # never asked to reproduce, keyed off the verbatim titles it echoed back.
        by_title = {c["title"]: c for c in catalog}
        highlights = result.get("catalog_highlights") or []
        for h in highlights:
            match = by_title.get(h.get("title"))
            if match:
                h.update({k: v for k, v in match.items() if k != "title"})
        result["catalog_highlights"] = [h for h in highlights if h.get("title") in by_title]
    return result


def _generate_knowledge(niche: dict, chunks: str) -> dict:
    from llm import call_ollama_generate
    prompt = f"""You are a clinical educator creating patient health literacy content for a Malaysian hospital.

TOPIC: {niche["prompt_topic"]}
CONDITION GROUP: {niche["group"]}
WEEK: {niche["week_number"]}

CLINICAL EVIDENCE:
{chunks or "No specific guideline chunks available — use evidence-based clinical knowledge."}

{_SAFETY_GUARDRAILS}

{_PERSONALIZATION_GUIDANCE}

TASK: Generate 6 educational learning points for patients. Each point should be clear, jargon-free, general (not a personalized prescription), and culturally relevant to Malaysia. Return ONLY valid JSON — no prose, no markdown fences:
{{
  "topic_summary": "one sentence summarising the topic",
  "learning_points": [
    {{"point": "short heading", "explanation": "1-2 sentence explanation", "why_it_matters": "why this matters to patient"}},
    {{"point": "...", "explanation": "...", "why_it_matters": "..."}},
    {{"point": "...", "explanation": "...", "why_it_matters": "..."}},
    {{"point": "...", "explanation": "...", "why_it_matters": "..."}},
    {{"point": "...", "explanation": "...", "why_it_matters": "..."}},
    {{"point": "...", "explanation": "...", "why_it_matters": "..."}}
  ],
  "key_takeaway": "one-sentence bottom line for the patient",
  "local_context": "specific Malaysian food, culture, or healthcare context note"
}}"""
    return _call_and_parse(prompt, 900)


def _generate_activity(niche: dict, chunks: str) -> dict:
    from llm import call_ollama_generate
    prompt = f"""You are a health behaviour coach creating patient habit-building tasks for a Malaysian hospital programme.

TOPIC: {niche["prompt_topic"]}
CONDITION GROUP: {niche["group"]}
WEEK: {niche["week_number"]}

{_SAFETY_GUARDRAILS}

{_PERSONALIZATION_GUIDANCE}

TASK: Design a practical weekly behavioural activity. It must be simple enough to do daily, relevant to Malaysian patients, and directly support health outcomes. Return ONLY valid JSON — no prose, no markdown fences:
{{
  "task_name": "short catchy name",
  "description": "1-2 sentence description of the task",
  "instructions": ["step 1", "step 2", "step 3", "step 4"],
  "tracking_method": "how to track (app / paper chart / phone notes)",
  "weekly_goal": "specific measurable goal for this week",
  "micro_actions": [
    "Monday: ...",
    "Tuesday: ...",
    "Wednesday: ...",
    "Thursday: ...",
    "Friday: ...",
    "Weekend: ..."
  ],
  "self_monitoring_prompts": [
    "End-of-day reflection question 1",
    "End-of-day reflection question 2"
  ],
  "success_looks_like": "what completing this week successfully looks like"
}}"""
    return _call_and_parse(prompt, 800)


def _call_and_parse(prompt: str, max_tokens: int) -> dict:
    from llm import call_ollama_generate
    raw = call_ollama_generate(prompt, max_tokens=max_tokens).strip()
    if raw.startswith("```"):
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end] if start != -1 else raw
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return {"raw_output": raw[:1000], "parse_error": True}


_GENERATORS = {"E": _generate_exercise, "K": _generate_knowledge, "A": _generate_activity}


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def _write_eka_excel(results: list, output_path: str, status_fn=None, comments_fn=None):
    """status_fn/comments_fn: optional item -> str callables, used by the
    /eka-review "reviewed" export (docs_api.py) to show live approval status
    and reviewer notes instead of the generation-time placeholder. Default
    behavior (no callables passed) is unchanged from before this was added.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    hdr_fill  = PatternFill("solid", fgColor="1a3c6b")
    hdr_font  = Font(bold=True, color="FFFFFF", size=11)
    type_fills = {
        "E": PatternFill("solid", fgColor="d4e6f1"),
        "K": PatternFill("solid", fgColor="d5f5e3"),
        "A": PatternFill("solid", fgColor="fef9e7"),
    }
    thin = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"),  bottom=Side(style="thin"),
    )

    type_labels = {"E": "Exercise", "K": "Knowledge", "A": "Activity"}

    for ctype in ("E", "K", "A"):
        ws = wb.create_sheet(title=type_labels[ctype])
        headers = ["Group", "Week", "Topic", "Title", "Field", "Value", "Status", "Comments"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin
        ws.row_dimensions[1].height = 22

        row = 2
        items = [r for r in results if r["content_type"] == ctype]
        for item in sorted(items, key=lambda x: x["group"]):
            content = item.get("content", {})
            if not content:
                content = {"(empty)": "(generation failed)"}
            fill = type_fills[ctype]
            status = status_fn(item) if status_fn else "raw — pending review"
            comments = comments_fn(item) if comments_fn else ""
            for field, value in content.items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                for col, val in enumerate([
                    item["group"], item["week_number"],
                    item["topic"], item["title"],
                    field, str(value), status, comments
                ], 1):
                    cell = ws.cell(row=row, column=col, value=val)
                    cell.border = thin
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                    if col <= 4:
                        cell.fill = fill
                row += 1

        for i, w in enumerate([14, 8, 22, 40, 25, 70, 20, 50], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"

    wb.save(output_path)
    print(f"  Excel saved → {output_path}")


def export_reviewed_excel(db_session, week_number: int, output_dir: str = None):
    """Write materials/eka_week{N}_reviewed.xlsx reflecting the CURRENT DB
    state (live approval status + reviewer notes) for one week — a single,
    always-overwritten file, separate from the generation-time snapshot
    (eka_week{N}_{date}.xlsx), which this never touches.

    Shared by two callers:
      - docs_api.py's /eka-review action endpoints (approve/unapprove/edit/
        note), to keep the file live as reviewers work.
      - database.py's cleanup_expired_eka_materials(), called right before
        deleting a week's expired rows — added 2026-09-08 after a real
        incident where a week generated under an earlier, shorter expiry
        policy was deleted with no export ever having been written for it
        (nobody had reviewed anything in it yet, so the docs_api sync path
        had never fired). Calling this unconditionally here means an
        expiring batch is always archived first, never silently lost.

    Returns the path written, or None if the week has no E/K/A materials.
    """
    import database as db_module

    materials = db_module.get_materials_by_filters(
        db_session, week_number=week_number, is_active=None, include_expired=True,
        limit=1000, offset=0,
    )
    results = [
        {
            "group": m.condition_group,
            "week_number": m.week_number,
            "topic": m.topic,
            "title": m.title,
            "content": m.raw_tips or {},
            "content_type": m.content_type,
            "_status": "✓ approved" if m.is_active else "pending review",
            "_notes": m.review_notes or [],
        }
        for m in materials
        if m.content_type in ("E", "K", "A")
    ]
    if not results:
        return None

    def status_fn(item):
        return item["_status"]

    def comments_fn(item):
        return " | ".join(
            f"{n.get('reviewer') or 'unknown'}: {n.get('text', '')}" for n in item["_notes"]
        )

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "materials")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"eka_week{week_number}_reviewed.xlsx")
    _write_eka_excel(results, output_path, status_fn=status_fn, comments_fn=comments_fn)
    return output_path


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_weekly_eka(iso_week: int = None, client_id: int = 4,
                        filter_group: str = None, filter_type: str = None,
                        dry_run: bool = False, force: bool = False,
                        output_dir: str = None) -> list:
    if iso_week is None:
        iso_week = date.today().isocalendar()[1]

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "materials")
    os.makedirs(output_dir, exist_ok=True)

    cases = build_eka_cases(iso_week)
    if filter_group:
        cases = [c for c in cases if c["group"] == filter_group]
    if filter_type:
        cases = [c for c in cases if c["content_type"] == filter_type]

    if not cases:
        print("No cases match filters.")
        return []

    rotation = ((iso_week - 1) % 4) + 1
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Weekly EKA Generation — ISO Week {iso_week} (Rotation {rotation}/4)")
    print(f"  Generating {len(cases)} items  |  Client: {client_id}  |  Force: {force}\n")

    db_session = None
    if not dry_run:
        import database as db_module
        db_module.create_db_and_tables()
        db_session = db_module.SessionLocal()

    results = []
    try:
        for i, niche in enumerate(cases, 1):
            label = f"[{i}/{len(cases)}] {niche['group']} / {niche['content_type']} / {niche['topic']}"
            print(f"  {label}")

            if dry_run:
                results.append({**niche, "content": {}, "skipped": True})
                print("    → (dry run)")
                continue

            print("    → retrieving chunks...")
            try:
                chunks = _retrieve_chunks(niche["rag_query"], client_id)
            except Exception as e:
                print(f"    → retrieval error: {e}")
                chunks = ""

            print("    → generating via Ollama...")
            try:
                gen_fn = _GENERATORS[niche["content_type"]]
                content = gen_fn(niche, chunks)
            except Exception as e:
                print(f"    → generation error: {e}")
                content = {"error": str(e)}

            parse_ok = not content.get("parse_error")
            print(f"    → {'OK' if parse_ok else 'PARSE ERROR'} ({len(str(content))} chars)")

            result = {**niche, "content": content}
            results.append(result)

            if db_session:
                try:
                    db_module.upsert_eka_material(
                        db_session,
                        condition_group=niche["group"],
                        condition_tags=niche["condition_tags"],
                        content_type=niche["content_type"],
                        week_number=niche["week_number"],
                        topic=niche["topic"],
                        title=niche["title"],
                        raw_content=content,
                        force=force,
                    )
                except Exception as e:
                    print(f"    → DB write error: {e}")

    finally:
        if db_session:
            db_session.close()

    if not dry_run and results:
        ts = datetime.now().strftime("%Y-%m-%d")
        excel_path = os.path.join(output_dir, f"eka_week{iso_week}_{ts}.xlsx")
        try:
            _write_eka_excel(results, excel_path)
        except Exception as e:
            print(f"  Excel write error: {e}")

    print(f"\nDone. {len(results)} items generated for week {iso_week}.")
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate weekly EKA content library")
    parser.add_argument("--week",      type=int, help="ISO week number (default: current week)")
    parser.add_argument("--client-id", type=int, default=4)
    parser.add_argument("--group",     type=str, help="Filter to one group (T2DM, HTN, CKD, Cardiac, Dyslipidaemia, General, Mental Health, Stress Management, Sleep, Atrial Fibrillation, Heart Failure, CVD Risk Management, PCOS)")
    parser.add_argument("--type",      type=str, help="Filter to one type (E, K, A)")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--force",     action="store_true", help="Overwrite existing DB rows")
    parser.add_argument("--output-dir", type=str)
    args = parser.parse_args()

    generate_weekly_eka(
        iso_week=args.week,
        client_id=args.client_id,
        filter_group=args.group,
        filter_type=args.type,
        dry_run=args.dry_run,
        force=args.force,
        output_dir=args.output_dir,
    )
