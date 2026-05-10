"""
eNCPT Parser — Extracts assessment terminology codes from the 2020 source PDF text
into a structured JSON schema usable by the nutribot extractor.

Focus: FH (Food/Nutrition-Related History) and CH-3 (Social History)
These are the categories the chatbot can collect via patient conversation.
Skipped: BD (lab tests), PD (physical exam), AD (measurements done at clinic),
         CS (reference values), and intervention codes — these come from
         clinicians or are not patient-reportable.
"""

import re
import json
from pathlib import Path
from collections import OrderedDict

INPUT = "/home/claude/encpt.txt"
OUTPUT = "/home/claude/encpt_schema.json"

# Categories to keep — these are patient-reportable / chatbot-collectable
COLLECTABLE_PREFIXES = ("FH-", "CH-")

# Within FH/CH, exclude these subtrees (clinician-only or too granular)
EXCLUDE_PATTERNS = [
    r"^FH-1\.[13]\.",   # parenteral/enteral nutrition (clinical)
    r"^FH-2\.",          # nutrient delivery method
    r"^CH-1\.1\.[1-3]$", # age/gender/sex (already in hospital DB)
    r"^CH-2\.",          # full medical history (already in hospital DB)
]


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_codes(text):
    """
    Extract every (code, label) pair from the document.
    Format in source: <label> <CODE> <ANDUID>
    Where CODE looks like FH-1.2.1.1.1.3 and ANDUID is a 5-digit number.

    The PDF was extracted as 2-column text so a single line often contains
    two unrelated entries side by side. We use the regex to find each
    entry independently.
    """
    # Pattern: optional checkbox + label text + code + 5-digit ANDUID
    # The label can include parentheses, dashes, slashes
    pattern = re.compile(
        r"❑?\s*([A-Za-z][A-Za-z0-9 ,()\-/'%.&+]+?)\s+"  # label
        r"((?:FH|AD|BD|PD|CH|CS|NI|NC|NB|ND|EY|RC|P)-\d+(?:\.\d+)*)\s+"  # code
        r"(\d{5})"  # ANDUID
    )

    seen = set()
    entries = []

    for m in pattern.finditer(text):
        label = re.sub(r"\s+", " ", m.group(1).strip())
        code = m.group(2)
        anduid = m.group(3)

        # Dedupe by (code, anduid) since labels sometimes wrap weirdly
        key = (code, anduid)
        if key in seen:
            continue
        seen.add(key)

        entries.append({
            "code": code,
            "anduid": anduid,
            "label": label,
        })

    return entries


def is_collectable(entry):
    """Filter for codes the chatbot can realistically collect from a patient."""
    code = entry["code"]

    if not code.startswith(COLLECTABLE_PREFIXES):
        return False

    for pat in EXCLUDE_PATTERNS:
        if re.match(pat, code):
            return False

    return True


def categorize(entry):
    """
    Add a logical category for organizing the schema.
    Maps eNCPT subtrees to plain-English buckets.
    """
    code = entry["code"]

    category_map = [
        (r"^FH-1\.1\.",     "Energy intake"),
        (r"^FH-1\.2\.1\.",  "Fluid intake"),
        (r"^FH-1\.2\.2\.",  "Food intake patterns"),
        (r"^FH-1\.2\.3\.",  "Breastmilk/infant formula"),
        (r"^FH-1\.4\.1\.",  "Alcohol intake"),
        (r"^FH-1\.4\.2\.",  "Bioactive substances"),
        (r"^FH-1\.4\.3\.",  "Caffeine intake"),
        (r"^FH-1\.5\.",     "Macronutrient intake"),
        (r"^FH-1\.6\.",     "Micronutrient intake"),
        (r"^FH-1\.7\.",     "Dietary supplement use"),
        (r"^FH-3\.",        "Medication & supplement use"),
        (r"^FH-4\.",        "Knowledge / beliefs / attitudes"),
        (r"^FH-5\.",        "Behavior"),
        (r"^FH-6\.",        "Food and supply access"),
        (r"^FH-7\.",        "Physical activity & function"),
        (r"^FH-8\.",        "Quality of life / patient-centered"),
        (r"^CH-1\.1\.[4-9]", "Personal demographics"),
        (r"^CH-1\.1\.1[0-9]", "Personal habits (tobacco, mobility)"),
        (r"^CH-3\.",        "Social history"),
    ]

    for pattern, name in category_map:
        if re.match(pattern, code):
            return name

    return "Other"


def build_schema(entries):
    """Group collectable entries by category."""
    schema = OrderedDict()

    for entry in entries:
        if not is_collectable(entry):
            continue

        cat = categorize(entry)
        schema.setdefault(cat, []).append({
            "code": entry["code"],
            "anduid": entry["anduid"],
            "label": entry["label"],
        })

    # Sort each category by code
    for cat in schema:
        schema[cat].sort(key=lambda e: [int(p) for p in e["code"].split("-")[1].split(".")])

    return schema


def main():
    text = read_file(INPUT)
    print(f"Read {len(text):,} chars")

    entries = parse_codes(text)
    print(f"Extracted {len(entries)} unique codes")

    schema = build_schema(entries)

    total_collectable = sum(len(v) for v in schema.values())
    print(f"Categorized {total_collectable} collectable codes into {len(schema)} categories:\n")

    for cat, items in schema.items():
        print(f"  {cat}: {len(items)} codes")

    # Save full structured schema
    with open(OUTPUT, "w") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT}")


if __name__ == "__main__":
    main()
