"""
Export embedding training pairs (anchor question + positive chunk) to CSV,
adding the source document reference by matching chunk text against pgvector.
"""
import csv
import json
import os
import re
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)
TRAIN_FILE = os.path.expanduser("~/data/embedding_train.jsonl")
VAL_FILE   = os.path.expanduser("~/data/embedding_val.jsonl")
OUT_CSV    = os.path.expanduser("~/data/training_pairs_with_sources.csv")

# How many chars of chunk text to include in the CSV (keeps file size manageable)
CHUNK_PREVIEW_LEN = 500

# Keyword rules for inferring source when hash match fails (re-ingested docs)
SOURCE_KEYWORDS = [
    (r"Recommended Nutrient Intakes for Malaysia|RNI 2017|RNI for Malaysia|Thiamin|Riboflavin|Niacin|Pyridoxine|Pantothenic|Biotin|Folate|Cobalamin|Ascorbic acid|Vitamin [A-K].*RNI|dietary reference|nutrient intake.*Malaysia",
     "RNI 2017.pdf"),
    (r"Malaysian Dietary Guideline|Suku.Suku.Separuh|quarter.quarter.half|MyPlate|Processed culinary ingredients|dental caries.*Malaysian",
     "Malaysian Dietary Guideline 2020.pdf"),
    (r"HbA1c|Type 2 Diabet|T2DM|CPG.*Diabetes|metformin|SGLT2|GLP-1|insulin.*diabet|fasting plasma glucose|oral glucose tolerance|diabetic nephropathy|diabetic retinopathy",
     "CPG_T2DM_6th_Edition_2020_13042021.pdf"),
    (r"Heart Failure|HFrEF|HFpEF|LVEF|cardiac cachexia|BNP|NT.proBNP|cardiogenic shock|S3 gallop|fluid overload.*heart|decompensated.*heart|ventricular dysfunction",
     "Management of Heart Failure (5th Edition).pdf"),
    (r"antihypertensive|blood pressure.*target|systolic blood pressure.*mmHg|diastolic blood pressure.*mmHg|ACE.I.*ARB.*hypertension|calcium channel blocker.*hypertension|thiazide.*hypertension",
     "Management of Hypertension (5th Edition).pdf"),
    (r"Dyslipidaemia|LDL.cholesterol|HDL.cholesterol|triglyceride|statin|lipid.lowering|atorvastatin|rosuvastatin|ezetimibe|PCSK9|familial hypercholesterolaemia",
     "Management of Dyslipidaemia 2023 (6th Edition).pdf"),
    (r"Medical Nutrition Therapy.*diabet|MNT.*diabetes|carbohydrate.*diabet|glycaemic index|ALT.*AST.*diabet|fatty liver.*diabet",
     "MNT_for_DM2.pdf"),
    (r"trans fat|saturated fat.*LDL|omega.3|cardiovascular.*diet|dietary pattern.*cardiovascular|Mediterranean.*diet|DASH.*diet|cardioprotective.*diet",
     "Primary & Secondary Prevention of Cardiovascular Disease.pdf"),
    (r"genetic.*counsel|familial.*screening|genetic testing.*cardiac|inherited.*cardiomyopathy|channelopathy",
     "CPG Stable Coronary Artery Disease (2nd Edition).pdf"),
    (r"adrenaline.*cardiogenic|adrenalin.*shock|vasopressor.*heart failure|inotrope|dobutamine|dopamine.*heart",
     "Management of Heart Failure (5th Edition).pdf"),
    (r"Vitamin C|ascorbic acid|Vitamin D.*IU|calcium.*RNI|iron.*RNI|zinc.*RNI|iodine.*RNI|folate.*RNI|selenium.*RNI",
     "RNI 2017.pdf"),
]


def infer_source(text: str) -> str:
    for pattern, source in SOURCE_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return source + " (inferred)"
    return "unknown"


def load_source_map() -> dict[str, str]:
    """Build hash(text)→source mapping from pgvector for exact matching."""
    import hashlib
    print("Loading source map from pgvector...", flush=True)
    url = PGVECTOR_URL
    if "+psycopg2" in url:
        url = url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("""
        SELECT e.document, e.cmetadata->>'source'
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON c.uuid = e.collection_id
        WHERE c.name = 'base_knowledge'
          AND length(e.document) > 100
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    # Key by SHA256 of full text — exact match, no collisions
    source_map = {hashlib.sha256(text.encode()).hexdigest(): source for text, source in rows}
    print(f"  Loaded {len(source_map):,} chunk→source mappings.")
    return source_map


def process_file(path: str, split_label: str, source_map: dict, writer: csv.DictWriter):
    import hashlib
    matched = unmatched = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pair = json.loads(line)
            anchor   = pair.get("anchor", "")
            positive = pair.get("positive", "")
            key      = hashlib.sha256(positive.encode()).hexdigest()
            source = source_map.get(key)
            if source:
                matched += 1
            else:
                source = infer_source(positive)
                unmatched += 1
            writer.writerow({
                "split":           split_label,
                "question":        anchor,
                "source_document": source,
                "chunk_preview":   positive[:CHUNK_PREVIEW_LEN].replace("\n", " ").strip(),
            })
    print(f"  {split_label}: {matched:,} matched, {unmatched:,} unmatched")


def main():
    source_map = load_source_map()

    print(f"Writing CSV to {OUT_CSV} ...")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=[
            "split", "question", "source_document", "chunk_preview"
        ])
        writer.writeheader()
        process_file(TRAIN_FILE, "train", source_map, writer)
        process_file(VAL_FILE,   "val",   source_map, writer)

    size_mb = os.path.getsize(OUT_CSV) / 1_048_576
    print(f"Done. {OUT_CSV} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
