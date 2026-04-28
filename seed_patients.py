"""
seed_patients.py — Creates the patients table and inserts 5 demo Malaysian patient records.

All patients belong to client_id=1 (the existing 'uitm' client).
Password for all demo accounts: demo1234

Usage:
    python seed_patients.py

Safe to re-run — skips any patient whose username already exists.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, create_db_and_tables, add_patient, get_patient_by_username

CLIENT_ID = 2  # test1 client — matches current API key

PATIENTS = [
    dict(
        name="Ahmad Fadzillah bin Roslan",
        ic_number="731015-14-5231",
        age=52,
        gender="Male",
        ethnicity="Malay",
        weight_kg=88.0,
        height_cm=168.0,
        conditions=["Type 2 Diabetes", "Hypertension"],
        medications=["Metformin 500mg BD", "Lisinopril 10mg OD", "Aspirin 100mg OD"],
        dietary_restrictions=["Halal only", "Low sodium", "Low simple carbohydrates"],
        allergies=[],
        notes=(
            "Office administrator, sedentary lifestyle. Eats Nasi Lemak and Teh Tarik daily. "
            "HbA1c 8.2%, BP 148/92 mmHg. Referred by KK Wangsa Maju. "
            "Motivated to change but struggles with late-night mamak habits."
        ),
        username="ahmad.fadzillah",
        password="demo1234",
    ),
    dict(
        name="Lim Siew Ching",
        ic_number="620318-10-5642",
        age=64,
        gender="Female",
        ethnicity="Chinese",
        weight_kg=61.5,
        height_cm=155.0,
        conditions=["Chronic Kidney Disease Stage 3", "Hypertension"],
        medications=["Amlodipine 5mg OD", "Furosemide 40mg OD", "Calcitriol 0.25mcg OD"],
        dietary_restrictions=[
            "Low potassium", "Low phosphorus",
            "Fluid restriction 1.5L per day", "Low sodium",
        ],
        allergies=["Shellfish"],
        notes=(
            "Retired schoolteacher. eGFR 42 mL/min/1.73m². "
            "Loves dim sum and herbal soups — counselled on high-potassium soup stock. "
            "Lives alone; son visits on weekends. Compliant with medications."
        ),
        username="lim.siewching",
        password="demo1234",
    ),
    dict(
        name="Kavitha a/p Subramaniam",
        ic_number="910725-07-5890",
        age=35,
        gender="Female",
        ethnicity="Indian",
        weight_kg=72.0,
        height_cm=158.0,
        conditions=["Polycystic Ovary Syndrome (PCOS)", "Insulin Resistance"],
        medications=["Metformin 850mg OD", "Inositol supplement 2g BD"],
        dietary_restrictions=["Low glycaemic index", "Anti-inflammatory diet preferred"],
        allergies=["Peanuts"],
        notes=(
            "Software engineer, high-stress job with irregular meal patterns — often skips breakfast. "
            "BMI 28.8. Trying to conceive; dietary counselling requested by ObGyn. "
            "Enjoys Thosai and vegetable curries. Exercises occasionally."
        ),
        username="kavitha.subra",
        password="demo1234",
    ),
    dict(
        name="Mohd Hafizuddin bin Salleh",
        ic_number="800512-14-6731",
        age=46,
        gender="Male",
        ethnicity="Malay",
        weight_kg=95.5,
        height_cm=172.0,
        conditions=["Dyslipidaemia", "Obesity Class I"],
        medications=["Atorvastatin 20mg ON", "Fenofibrate 145mg OD"],
        dietary_restrictions=["Halal only", "Low saturated fat", "Low cholesterol"],
        allergies=[],
        notes=(
            "Lorry driver with irregular meal schedule; eats mainly at roadside stalls. "
            "Total cholesterol 7.2 mmol/L, LDL 4.8 mmol/L, triglycerides elevated. "
            "Frequent mamak meals: murtabak, roti canai with curry. Smokes 10 cigarettes/day. "
            "Resistant to dietary changes — motivational approach recommended."
        ),
        username="hafizuddin.salleh",
        password="demo1234",
    ),
    dict(
        name="Tan Wei Loong",
        ic_number="681203-10-5123",
        age=58,
        gender="Male",
        ethnicity="Chinese",
        weight_kg=78.0,
        height_cm=165.0,
        conditions=["Hypertension", "Hypercholesterolaemia", "Type 2 Diabetes"],
        medications=[
            "Metformin 1000mg BD", "Perindopril 8mg OD",
            "Rosuvastatin 10mg ON", "Aspirin 75mg OD",
        ],
        dietary_restrictions=[
            "Low sodium", "Low simple carbohydrates",
            "Low saturated fat", "No pork (personal preference)",
        ],
        allergies=["Sulfa drugs (note for nursing reference only)"],
        notes=(
            "Retired civil servant. Eats hawker food 3x daily — char kway teow, economy rice. "
            "BP 155/95 mmHg, HbA1c 7.8%. Son accompanies all consultations. "
            "Willing to change diet but wife does all cooking; family-based counselling advised."
        ),
        username="tan.weiloong",
        password="demo1234",
    ),
]


def main():
    print("--- NutriChatbot Patient Seeder ---")
    create_db_and_tables()

    session = SessionLocal()
    try:
        seeded = 0
        skipped = 0
        patched = 0
        for p in PATIENTS:
            existing = get_patient_by_username(session, p["username"])
            if existing:
                # Patch ic_number if missing
                if not existing.ic_number and p.get("ic_number"):
                    existing.ic_number = p["ic_number"]
                    session.commit()
                    print(f"  PATCH {p['username']} — ic_number updated to {p['ic_number']}")
                    patched += 1
                else:
                    print(f"  SKIP  {p['username']} (already exists)")
                    skipped += 1
                continue
            patient = add_patient(session, client_id=CLIENT_ID, **p)
            bmi = patient.weight_kg / ((patient.height_cm / 100) ** 2)
            print(
                f"  OK    id={patient.id}  {patient.name}"
                f"  ({patient.ethnicity}, {patient.age}y, BMI {bmi:.1f})"
                f"  conditions={patient.conditions}"
            )
            seeded += 1

        print(f"\nDone. Seeded: {seeded}, Patched: {patched}, Skipped: {skipped}")
        print("\nPatient login credentials (for testing):")
        print("  Username                Password")
        print("  ----------------------  --------")
        for p in PATIENTS:
            print(f"  {p['username']:<22}  {p['password']}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
