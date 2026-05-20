"""Convert encpt_curated.json (v2 cardiac) into dietitian-friendly Markdown."""

import json
from collections import defaultdict

with open("/mnt/ssd/bare_NutriChatbot/data/encpt/encpt_curated.json") as f:
    data = json.load(f)

fields = data["fields"]

by_tier = defaultdict(list)
for f in fields:
    by_tier[f["priority"]].append(f)

TIER_INFO = {
    "tier1": ("Tier 1 — Critical", "Must collect for safe cardiac dietary advice. Bot should not give nutritional recommendations without these fields."),
    "tier2": ("Tier 2 — Important", "Significantly improves the quality and personalization of cardiac advice. Collect during the first few sessions."),
    "tier3": ("Tier 3 — Nice to Have", "Adds context and supports long-term care. Collect opportunistically during conversation."),
}


def fmt_conditions(conds):
    if conds == ["all"]:
        return "All patients"
    return ", ".join(conds)


def fmt_data_type(dt):
    pretty = {
        "number_ml": "Number (mL)",
        "number_mg": "Number (mg)",
        "number_minutes": "Number (minutes)",
        "number_drinks": "Number (drinks)",
        "number": "Number",
        "string": "Free text",
        "frequency_string": "Frequency phrase",
        "list": "List of items",
        "list_of_strings": "List of strings",
        "list_of_objects": "List of structured items",
        "boolean": "Yes / No",
        "scale_1_5": "1–5 scale",
        "scale_1_10": "1–10 scale",
        "stage": "Behavior change stage",
    }
    return pretty.get(dt, dt)


def fmt_allowed_values(field):
    if "allowed_values" in field:
        return f" — values: `{', '.join(field['allowed_values'])}`"
    return ""


lines = []

# Header
lines.append("# Nutribot Dynamic Data Collection — Cardiac eNCPT Schema (v2)")
lines.append("")
lines.append(f"**Specialty:** {data['specialty'].title()}")
lines.append(f"**Based on:** {data['based_on']}")
lines.append(f"**Total fields:** {data['total_fields']} ({data['new_fields']} new since v1)")
lines.append(f"**Languages:** English + Bahasa Malaysia")
lines.append("")
lines.append("This document lists the patient information the chatbot will dynamically collect during conversation, ")
lines.append("specialized for **cardiac patients**. Each field is mapped to a standard **eNCPT 2020** code so the data ")
lines.append("can integrate with clinical workflows and electronic health records. Fields are organized by priority tier ")
lines.append("(cardiac-adjusted from the general eNCPT schema).")
lines.append("")

# Summary
lines.append("## Summary")
lines.append("")
lines.append("| Tier | Description | Field Count |")
lines.append("|------|-------------|-------------|")
for tier_key in ["tier1", "tier2", "tier3"]:
    name, desc = TIER_INFO[tier_key]
    count = data["tier_counts"][tier_key]
    lines.append(f"| **{name}** | {desc} | {count} |")
lines.append("")

# Cardiac-specific changes
lines.append("## Changes for Cardiac Focus (v2 vs v1)")
lines.append("")
new_fields = [f for f in fields if f.get("new_field")]
promoted = [f for f in fields if "Promoted" in f.get("tier_change_note", "")]
demoted = [f for f in fields if "Demoted" in f.get("tier_change_note", "")]

if new_fields:
    lines.append("### New fields added (per dietitian)")
    lines.append("")
    lines.append("| Code | Field | Tier |")
    lines.append("|------|-------|------|")
    for f in new_fields:
        lines.append(f"| `{f['code']}` | {f['label']} | {f['priority']} |")
    lines.append("")

if promoted:
    lines.append("### Promoted fields (more critical for cardiac)")
    lines.append("")
    for f in promoted:
        lines.append(f"- `{f['code']}` **{f['label']}** — {f['tier_change_note']}")
    lines.append("")

if demoted:
    lines.append("### Demoted fields (less critical for cardiac)")
    lines.append("")
    for f in demoted:
        lines.append(f"- `{f['code']}` **{f['label']}** — {f['tier_change_note']}")
    lines.append("")

# How to read
lines.append("## How to Read This Schema")
lines.append("")
lines.append("- **eNCPT Code**: Standardized terminology code from the Academy of Nutrition and Dietetics.")
lines.append("- **Field Description**: What the bot is trying to learn about the patient.")
lines.append("- **Data Type**: Format the field is stored in. `allowed_values` show valid options where applicable.")
lines.append("- **Example Question (EN/MS)**: How the bot might naturally ask, in English and Bahasa Malaysia.")
lines.append("- **Example Patient Answer**: Typical response the extractor should be able to handle.")
lines.append("- **Most Relevant For**: Clinical conditions where this field is especially important.")
lines.append("- **Clinical Relevance**: Why this matters for cardiac care.")
lines.append("")

# Per-tier sections
for tier_key in ["tier1", "tier2", "tier3"]:
    name, desc = TIER_INFO[tier_key]
    items = by_tier[tier_key]

    lines.append(f"## {name}")
    lines.append("")
    lines.append(f"_{desc}_")
    lines.append("")

    # Compact table first
    lines.append("| eNCPT Code | Field | Data Type | Most Relevant For |")
    lines.append("|------------|-------|-----------|-------------------|")
    for f in items:
        marker = " 🆕" if f.get("new_field") else ""
        lines.append(
            f"| `{f['code']}` | {f['label']}{marker} | {fmt_data_type(f['data_type'])}{fmt_allowed_values(f)} | {fmt_conditions(f.get('relevant_conditions', ['all']))} |"
        )
    lines.append("")

    # Detailed per field
    lines.append(f"### {name} — Detailed Cards")
    lines.append("")
    for f in items:
        marker = " 🆕 NEW" if f.get("new_field") else ""
        lines.append(f"#### `{f['code']}` — {f['label']}{marker}")
        lines.append("")
        if f.get("clinical_relevance"):
            lines.append(f"**Clinical relevance:** {f['clinical_relevance']}")
            lines.append("")
        if f.get("tier_change_note"):
            lines.append(f"**Note:** {f['tier_change_note']}")
            lines.append("")
        if f.get("extractor_note"):
            lines.append(f"**Extractor note:** {f['extractor_note']}")
            lines.append("")

        # Bot question - EN + MS
        eq = f.get("example_question", {})
        if isinstance(eq, dict):
            lines.append(f"> **Bot (EN):** {eq.get('en', '')}")
            lines.append(f">")
            lines.append(f"> **Bot (MS):** {eq.get('ms', '')}")
        else:
            lines.append(f"> **Bot:** {eq}")
        lines.append(f">")
        lines.append(f"> **Patient:** \"{f.get('example_answer', '')}\"")
        lines.append("")
    lines.append("---")
    lines.append("")

# Notes for dietitian
lines.append("## Notes for Reviewing Dietitians")
lines.append("")
lines.append("This v2 schema reflects the cardiac-focused priorities discussed. Please review:")
lines.append("")
lines.append("1. **Cardiac tier assignments** — Are any fields in the wrong tier for cardiac patients?")
lines.append("2. **New fields** — Do `Total fat intake`, `Fat type sources`, `Medication compliance`, ")
lines.append("   and `Type of physical activity` capture what you intended?")
lines.append("3. **Bahasa Malaysia phrasing** — Are the BM questions natural for Malaysian patients? ")
lines.append("   Should some be more colloquial (e.g., using 'nak' instead of 'mahu')?")
lines.append("4. **Allowed values** — For fields like `medication compliance` (good/variable/poor) ")
lines.append("   and `fat intake` (low/moderate/high), are these the right buckets?")
lines.append("5. **Other cardiac sub-conditions** — When ready to differentiate (e.g., heart failure vs ")
lines.append("   ischemic heart disease vs valvular), what fields would shift in priority?")
lines.append("")
lines.append("Please mark any suggested changes directly in this document or send feedback to Lee Yean Han.")

with open("/mnt/ssd/bare_NutriChatbot/data/encpt/encpt_curated.json", "w") as f:
    f.write("\n".join(lines))

import os
print(f"Wrote {len(lines)} lines to /mnt/ssd/bare_NutriChatbot/data/encpt/encpt_curated.json")
print(f"File size: {os.path.getsize('/mnt/ssd/bare_NutriChatbot/data/encpt/encpt_curated.json'):,} bytes")
