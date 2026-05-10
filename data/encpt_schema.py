"""
Step A: Curated bot-collectable schema.

From the 447 auto-extracted codes, select the highest-priority 40 for
chatbot collection. Each entry adds:
  - extraction_priority: tier1 (must have) / tier2 (important) / tier3 (nice)
  - data_type: how to store it (number/string/list/json)
  - example_question: how the bot might ask this
  - example_answer: typical patient phrasing
  - relevant_conditions: which diseases this is most important for

This file is the actual input to the extractor module.
"""

import json
from pathlib import Path

CURATED = [
    # ── TIER 1: Critical for safe dietary advice ──────────────────────
    {
        "code": "FH-1.2.1.1.1",
        "label": "Total fluid estimated intake in 24 hours",
        "priority": "tier1",
        "data_type": "number_ml",
        "example_question": "About how much fluid do you drink in a typical day?",
        "example_answer": "I drink about 6 glasses of water plus 2 cups of coffee",
        "relevant_conditions": ["Heart Failure", "CKD", "Hypertension"],
    },
    {
        "code": "FH-1.4.1.1",
        "label": "Alcohol intake in one week",
        "priority": "tier1",
        "data_type": "number_drinks",
        "example_question": "How much alcohol do you drink in a typical week?",
        "example_answer": "Maybe 2-3 beers on weekends",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-3.2.1",
        "label": "Vitamin/mineral supplement intake",
        "priority": "tier1",
        "data_type": "list_of_objects",
        "example_question": "Are you taking any vitamins, minerals, or other supplements?",
        "example_answer": "I take fish oil and vitamin D every day",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-1.6",
        "label": "Food allergies and intolerances",
        "priority": "tier1",
        "data_type": "list",
        "example_question": "Do you have any food allergies or foods that make you feel unwell?",
        "example_answer": "I'm allergic to shellfish and dairy gives me stomach issues",
        "relevant_conditions": ["all"],
    },
    {
        "code": "CH-3.1.7",
        "label": "Religion (affects diet)",
        "priority": "tier1",
        "data_type": "string",
        "example_question": "Are there foods you avoid for religious or cultural reasons?",
        "example_answer": "I'm Muslim so I only eat halal, no pork",
        "relevant_conditions": ["all"],
    },

    # ── TIER 2: Important for tailored advice ─────────────────────────
    {
        "code": "FH-1.2.2.3.1.1",
        "label": "Number of meals estimated in 24 hours",
        "priority": "tier2",
        "data_type": "number",
        "example_question": "How many meals do you eat in a day?",
        "example_answer": "Three main meals plus 2 snacks usually",
        "relevant_conditions": ["Diabetes", "Hypertension"],
    },
    {
        "code": "FH-1.2.2.3.1.2",
        "label": "Number of snacks estimated in 24 hours",
        "priority": "tier2",
        "data_type": "number",
        "example_question": "How many snacks do you have between meals?",
        "example_answer": "1 or 2 snacks usually",
        "relevant_conditions": ["Diabetes", "Obesity"],
    },
    {
        "code": "FH-1.2.2.2.5",
        "label": "Processed food intake",
        "priority": "tier2",
        "data_type": "frequency_string",
        "example_question": "How often do you eat processed or packaged foods?",
        "example_answer": "Maybe once a week, mostly home-cooked",
        "relevant_conditions": ["Hypertension", "Dyslipidemia", "Obesity"],
    },
    {
        "code": "FH-1.2.2.2.6",
        "label": "Quick service food intake",
        "priority": "tier2",
        "data_type": "frequency_string",
        "example_question": "How often do you eat fast food or takeaway?",
        "example_answer": "Twice a week or so",
        "relevant_conditions": ["Hypertension", "Dyslipidemia", "Obesity", "Diabetes"],
    },
    {
        "code": "FH-1.2.2.2.7",
        "label": "Self prepared food intake",
        "priority": "tier2",
        "data_type": "frequency_string",
        "example_question": "Do you usually cook your own meals or does someone else?",
        "example_answer": "My wife cooks most days",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-1.4.3.1",
        "label": "Total caffeine estimated intake in 24 hours",
        "priority": "tier2",
        "data_type": "number_mg",
        "example_question": "How much coffee or tea do you drink a day?",
        "example_answer": "Two cups of coffee in the morning",
        "relevant_conditions": ["Hypertension", "Atrial Fibrillation"],
    },
    {
        "code": "FH-1.2.1.1.1.3",
        "label": "Sugar sweetened beverage estimated oral intake in 24 hours",
        "priority": "tier2",
        "data_type": "number_ml",
        "example_question": "Do you drink sweetened drinks like soda, juice or sweetened tea?",
        "example_answer": "I have one teh tarik a day",
        "relevant_conditions": ["Diabetes", "Obesity"],
    },
    {
        "code": "FH-7.3.1",
        "label": "Physical activity frequency",
        "priority": "tier2",
        "data_type": "frequency_string",
        "example_question": "How often do you exercise or do physical activity?",
        "example_answer": "I walk for 30 minutes 3 times a week",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-7.3.2",
        "label": "Physical activity duration",
        "priority": "tier2",
        "data_type": "number_minutes",
        "example_question": "About how long do your exercise sessions last?",
        "example_answer": "30 to 45 minutes each time",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-7.3.3",
        "label": "Physical activity intensity",
        "priority": "tier2",
        "data_type": "string",
        "example_question": "Would you describe your exercise as light, moderate, or vigorous?",
        "example_answer": "Moderate - I get a bit out of breath",
        "relevant_conditions": ["Cardiac", "Heart Failure"],
    },
    {
        "code": "FH-5.2.1",
        "label": "Food avoidance",
        "priority": "tier2",
        "data_type": "list",
        "example_question": "Are there any foods you avoid eating, and why?",
        "example_answer": "I avoid fatty foods because they upset my stomach",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-5.4.1",
        "label": "Cultural/religious eating practices",
        "priority": "tier2",
        "data_type": "string",
        "example_question": "Are there cultural or family traditions that shape what you eat?",
        "example_answer": "We always have rice with every meal",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-4.1.3",
        "label": "Nutrition knowledge of individual client",
        "priority": "tier2",
        "data_type": "scale_1_5",
        "example_question": "How familiar are you with what foods to eat for your condition?",
        "example_answer": "I know I should eat less salt but not much else",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-4.2.8",
        "label": "Readiness to change nutrition-related behaviors",
        "priority": "tier2",
        "data_type": "stage",  # precontemplation/contemplation/preparation/action/maintenance
        "example_question": "How ready do you feel to make changes to your diet?",
        "example_answer": "I'm trying to eat less rice already",
        "relevant_conditions": ["all"],
    },

    # ── TIER 3: Nice to have / quality of life / context ──────────────
    {
        "code": "FH-1.4.1.4",
        "label": "Alcohol intake pattern on drinking days",
        "priority": "tier3",
        "data_type": "string",
        "example_question": "On days you drink, do you usually have one drink or several?",
        "example_answer": "Usually 2-3 in one sitting",
        "relevant_conditions": ["Liver", "Hypertension"],
    },
    {
        "code": "FH-6.2.1",
        "label": "Availability of shopping facilities",
        "priority": "tier3",
        "data_type": "string",
        "example_question": "Is it easy for you to buy fresh fruit and vegetables where you live?",
        "example_answer": "Yes, there's a market nearby",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-6.2.3",
        "label": "Access to food preparation equipment",
        "priority": "tier3",
        "data_type": "boolean",
        "example_question": "Do you have a kitchen with a stove and refrigerator?",
        "example_answer": "Yes, just basic but it works",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-5.4.2",
        "label": "Eating environment (alone/with family/etc)",
        "priority": "tier3",
        "data_type": "string",
        "example_question": "Do you usually eat alone or with others?",
        "example_answer": "With my family for dinner, lunch is at work",
        "relevant_conditions": ["all"],
    },
    {
        "code": "CH-3.1.9",
        "label": "Daily stress level",
        "priority": "tier3",
        "data_type": "scale_1_10",
        "example_question": "How stressful would you say your daily life is, on a scale of 1 to 10?",
        "example_answer": "About a 7, work has been intense",
        "relevant_conditions": ["Hypertension", "Cardiac"],
    },
    {
        "code": "CH-3.1.6",
        "label": "Occupation",
        "priority": "tier3",
        "data_type": "string",
        "example_question": "What do you do for work?",
        "example_answer": "I'm a teacher, mostly desk work",
        "relevant_conditions": ["all"],
    },
    {
        "code": "CH-3.1.4",
        "label": "Social and medical support",
        "priority": "tier3",
        "data_type": "string",
        "example_question": "Do you have family or friends helping you manage your health?",
        "example_answer": "My daughter helps with my appointments",
        "relevant_conditions": ["all"],
    },
    {
        "code": "FH-1.5.6.1",
        "label": "Sodium awareness/intake estimation",
        "priority": "tier2",
        "data_type": "string",
        "example_question": "How salty do you like your food, and do you check labels for sodium?",
        "example_answer": "I add salt to almost everything, never check labels",
        "relevant_conditions": ["Hypertension", "Heart Failure", "CKD"],
    },
    {
        "code": "FH-1.5.4.5",
        "label": "Fiber estimated intake",
        "priority": "tier3",
        "data_type": "string",
        "example_question": "Do you eat whole grains, beans, or lots of fruits and vegetables?",
        "example_answer": "Some fruit daily, mostly white rice for grains",
        "relevant_conditions": ["Diabetes", "Dyslipidemia", "Obesity"],
    },
    {
        "code": "FH-8.1",
        "label": "Nutrition quality of life",
        "priority": "tier3",
        "data_type": "scale_1_5",
        "example_question": "How happy are you with the way you eat right now?",
        "example_answer": "Not really, I want to change but it's hard",
        "relevant_conditions": ["all"],
    },
    {
        "code": "CH-1.1.10",
        "label": "Tobacco use",
        "priority": "tier1",
        "data_type": "string",
        "example_question": "Do you currently smoke or use any tobacco?",
        "example_answer": "I quit 5 years ago",
        "relevant_conditions": ["Cardiac", "Hypertension", "Dyslipidemia"],
    },
]


def main():
    out = {
        "version": "1.0",
        "based_on": "eNCPT 2020 Edition (Academy of Nutrition and Dietetics)",
        "total_fields": len(CURATED),
        "tier_counts": {
            "tier1": sum(1 for f in CURATED if f["priority"] == "tier1"),
            "tier2": sum(1 for f in CURATED if f["priority"] == "tier2"),
            "tier3": sum(1 for f in CURATED if f["priority"] == "tier3"),
        },
        "fields": CURATED,
    }

    with open("/home/claude/encpt_curated.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"Curated schema: {out['total_fields']} fields")
    print(f"  Tier 1 (critical): {out['tier_counts']['tier1']}")
    print(f"  Tier 2 (important): {out['tier_counts']['tier2']}")
    print(f"  Tier 3 (nice to have): {out['tier_counts']['tier3']}")
    print("Wrote /home/claude/encpt_curated.json")


if __name__ == "__main__":
    main()
