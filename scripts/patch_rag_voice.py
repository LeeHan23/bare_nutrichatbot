"""
Patch rag.py to fix third-person voice when is_patient_self=True.

Two surgical changes:
  1. Insert a helper function _to_second_person_profile() that rewrites
     "Name: X" -> "Your name: X (do not repeat back)", etc.
  2. Replace the if is_patient_self branch's header and instruction with
     stronger versions including few-shot examples.

Idempotent — safe to run multiple times.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'rag.py'
src = open(path).read()
changed = 0

# ─────────────────────────────────────────────────────────────────
# 1. Insert helper function (before "def get_rag_response")
# ─────────────────────────────────────────────────────────────────
HELPER = '''def _to_second_person_profile(patient_context: str) -> str:
    """Rewrite third-person profile labels to second-person for self-mode.

    Turns lines like 'Name: Lim Siew Ching' into 'Your name: Lim Siew Ching
    (do NOT repeat this name back — address them as you).' so the LLM is
    primed for second-person responses by the input itself.
    """
    import re
    replacements = [
        (r"^Name:\\s*(.+)$",
            r"Your name: \\1  (do NOT repeat this name back — address them as 'you')"),
        (r"^Age:", r"Your age:"),
        (r"^Gender:", r"Your gender:"),
        (r"^Ethnicity:", r"Your ethnicity:"),
        (r"^Weight\\s*\\(kg\\):", r"Your weight (kg):"),
        (r"^Height\\s*\\(cm\\):", r"Your height (cm):"),
        (r"^BMI:", r"Your BMI:"),
        (r"^Conditions:", r"Your conditions:"),
        (r"^Medications:", r"Your medications:"),
        (r"^Allergies:", r"Your allergies:"),
        (r"^Dietary [Rr]estrictions?:", r"Your dietary restrictions:"),
        (r"^Religion:", r"Your religion:"),
        (r"^Notes:", r"Notes about you:"),
        # Extended supplementary fields — match prefixes broadly
        (r"^Tobacco status:", r"Your tobacco status:"),
        (r"^Alcohol", r"Your alcohol"),
        (r"^Fluid intake", r"Your fluid intake"),
        (r"^Supplements:", r"Your supplements:"),
        (r"^Activity ", r"Your activity "),
        (r"^Caffeine", r"Your caffeine"),
        (r"^Sodium ", r"Your sodium "),
        (r"^Meals ", r"Your meals "),
        (r"^Snacks ", r"Your snacks "),
        (r"^Processed food", r"Your processed food"),
        (r"^Fast food", r"Your fast food"),
        (r"^Self.prepared", r"Your self-prepared"),
        (r"^Sugar drinks", r"Your sugar drinks"),
        (r"^Food avoidance:", r"Your food avoidance:"),
        (r"^Nutrition knowledge:", r"Your nutrition knowledge:"),
        (r"^Readiness to change:", r"Your readiness to change:"),
        (r"^Fat intake", r"Your fat intake"),
        (r"^Fat type", r"Your fat type"),
        (r"^Medication compliance:", r"Your medication compliance:"),
    ]
    out = []
    for line in patient_context.split("\\n"):
        for pat, rep in replacements:
            line = re.sub(pat, rep, line, count=1)
        out.append(line)
    return "\\n".join(out)


'''

if "_to_second_person_profile" not in src:
    marker = "def get_rag_response("
    if marker not in src:
        print("⚠️  Could not find 'def get_rag_response(' — aborting")
        sys.exit(1)
    src = src.replace(marker, HELPER + marker, 1)
    print("✅ Added _to_second_person_profile helper")
    changed += 1
else:
    print("⏭️  helper already present")

# ─────────────────────────────────────────────────────────────────
# 2. Replace the self-mode header construction
# ─────────────────────────────────────────────────────────────────
OLD_HEADER = '''            if is_patient_self:
                header = f"Your Profile:\\n{patient_context}"
            else:
                header = f"Patient Profile:\\n{patient_context}"'''

NEW_HEADER = '''            if is_patient_self:
                self_ctx = _to_second_person_profile(patient_context)
                header = (
                    "This is the person you are talking to. They are reading your reply.\\n"
                    "Address them in second person ('you', 'your') — do NOT use their name.\\n\\n"
                    f"{self_ctx}"
                )
            else:
                header = f"Patient Profile:\\n{patient_context}"'''

if OLD_HEADER in src:
    src = src.replace(OLD_HEADER, NEW_HEADER)
    print("✅ Patched header construction")
    changed += 1
elif "_to_second_person_profile(patient_context)" in src:
    print("⏭️  header already patched")
else:
    print("⚠️  Could not match header block — manual fix needed")

# ─────────────────────────────────────────────────────────────────
# 3. Replace the self-mode instruction with strengthened version
# ─────────────────────────────────────────────────────────────────
OLD_INSTR = '''            if is_patient_self:
                instruction = (
                    "Respond directly to the patient using 'you' and 'your' — never use their name or say 'the patient'. "
                    "Verify all food and drink recommendations against the conditions listed above and flag any that are contraindicated. "
                    "Be conversational and practical; skip definitions and unnecessary preamble."
                )'''

NEW_INSTR = '''            if is_patient_self:
                instruction = (
                    "VOICE RULES — apply to every word of your reply:\\n"
                    "  You are speaking DIRECTLY to the person whose profile is shown above.\\n"
                    "  They are reading your reply word-for-word, in real time.\\n"
                    "  ALWAYS write in second person: 'you', 'your', 'yours'.\\n"
                    "  NEVER write the person's name. NEVER write 'the patient', 'they', 'she', 'he', 'her', 'his'.\\n"
                    "  NEVER use generic third-person framings like 'an adult with BMI X should...'.\\n"
                    "\\n"
                    "Examples of CORRECT phrasing:\\n"
                    "  CORRECT: 'Given your CKD and hypertension, you should aim for under 5g of sodium per day.'\\n"
                    "  CORRECT: 'I would recommend you cut back on processed foods.'\\n"
                    "  CORRECT: 'Because your BMI is 25.6, this is especially important for you.'\\n"
                    "\\n"
                    "Examples of WRONG phrasing — do NOT write like any of these:\\n"
                    "  WRONG: 'Lim Siew Ching should aim for...'\\n"
                    "  WRONG: 'The patient should limit...'\\n"
                    "  WRONG: 'An adult with a BMI of 25.6 should...'\\n"
                    "  WRONG: 'She has hypertension, so she should...'\\n"
                    "\\n"
                    "Also: verify every food and drink recommendation against your conditions and flag anything contraindicated. "
                    "Be conversational and practical — skip definitions and unnecessary preamble."
                )'''

if OLD_INSTR in src:
    src = src.replace(OLD_INSTR, NEW_INSTR)
    print("✅ Patched instruction (with few-shot examples)")
    changed += 1
elif "VOICE RULES" in src:
    print("⏭️  instruction already patched")
else:
    print("⚠️  Could not match instruction block — manual fix needed")

# ─────────────────────────────────────────────────────────────────
# Write back
# ─────────────────────────────────────────────────────────────────
if changed > 0:
    open(path, 'w').write(src)
    print(f"\\nSaved {changed} change(s) to {path}")
else:
    print("\\nNo changes needed")

print("Verify with: sed -n '90,210p' rag.py")
