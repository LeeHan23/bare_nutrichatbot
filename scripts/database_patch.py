"""
Apply v2 ORM additions to database.py. Adds 4 new columns to the Patient
model and updates the SUPPLEMENTARY_FIELDS whitelist.
"""
import re

DB_PATH = '/mnt/ext/bare_NutriChatbot/database.py'
PSTORE_PATH = '/mnt/ext/bare_NutriChatbot/patient_store.py'

# ── 1. Patch database.py — add new columns after sodium_awareness ─────
content = open(DB_PATH).read()

old = '    sodium_awareness       = Column(String, nullable=True)         # FH-1.5.6.1'
new = '''    sodium_awareness       = Column(String, nullable=True)         # FH-1.5.6.1

    # ── v2 (cardiac priority additions) ─────────────────────────────────
    fat_intake_level       = Column(String, nullable=True)         # FH-1.5.1.1 (low/moderate/high)
    fat_sources            = Column(JSON, default=list)            # FH-1.5.1.2
    medication_compliance  = Column(String, nullable=True)         # FH-3.1.1.1 (good/variable/poor)
    activity_types         = Column(JSON, default=list)            # FH-7.3.1.1'''

if 'fat_intake_level' in content:
    print("database.py: already patched with v2 columns")
elif old in content:
    content = content.replace(old, new)
    open(DB_PATH, 'w').write(content)
    print("database.py: added 4 v2 columns to Patient model")
else:
    print("ERROR: could not find sodium_awareness anchor in database.py")
    raise SystemExit(1)

# ── 2. Patch patient_store.py — add new fields to SUPPLEMENTARY_FIELDS ─
content = open(PSTORE_PATH).read()

if 'fat_intake_level' in content:
    print("patient_store.py: already has v2 fields in whitelist")
else:
    # Find the SUPPLEMENTARY_FIELDS set and inject before the closing brace
    old = '    "sodium_awareness",\n}'
    new = '''    "sodium_awareness",
    # v2 cardiac additions
    "fat_intake_level",
    "fat_sources",
    "medication_compliance",
    "activity_types",
}'''
    if old in content:
        content = content.replace(old, new)
        open(PSTORE_PATH, 'w').write(content)
        print("patient_store.py: added 4 v2 fields to SUPPLEMENTARY_FIELDS whitelist")
    else:
        print("ERROR: could not find SUPPLEMENTARY_FIELDS anchor in patient_store.py")
        raise SystemExit(1)
