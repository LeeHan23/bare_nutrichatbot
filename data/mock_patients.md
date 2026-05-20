# Mock Patient Database

7 synthetic Malaysian patients for dev/staging. Patients are identified by name or IC number — no password login is used.

> **Production note:** All patient data in production must live on the hospital/university server. This local DB is dev/staging only.

---

| ID | IC Number | Name | Age | Gender | Ethnicity | Weight | Height | BMI | Level |
|----|-----------|------|-----|--------|-----------|--------|--------|-----|-------|
| 1 | 731015-14-5231 | Ahmad Fadzillah bin Roslan | 52 | M | Malay | 88.0 kg | 168 cm | 31.2 | L2 |
| 2 | 620318-10-5642 | Lim Siew Ching | 64 | F | Chinese | 61.5 kg | 155 cm | 25.6 | L2 |
| 3 | 910725-07-5890 | Kavitha a/p Subramaniam | 35 | F | Indian | 72.0 kg | 158 cm | 28.8 | L1 |
| 4 | 800512-14-6731 | Mohd Hafizuddin bin Salleh | 46 | M | Malay | 95.5 kg | 172 cm | 32.3 | L1 |
| 5 | 681203-10-5123 | Tan Wei Loong | 58 | M | Chinese | 78.0 kg | 165 cm | 28.7 | L2 |
| 10 | 990304-14-6218 | Nurul Ain binti Zulkifli | 27 | F | Malay | 56.0 kg | 162 cm | 21.3 | L0 |
| 11 | 530818-07-5341 | Rajendran a/l Muthu | 73 | M | Indian | 67.0 kg | 163 cm | 25.2 | L3 |

---

## Patient Details

### P1 — Ahmad Fadzillah bin Roslan `L2`
| Field | Value |
|-------|-------|
| IC | 731015-14-5231 |
| Username | ahmad.fadzillah |
| Age / Gender | 52, Male, Malay |
| Weight / Height / BMI | 88.0 kg / 168 cm / 31.2 |
| Conditions | Type 2 Diabetes, Hypertension |
| Medications | Metformin 500mg BD, Lisinopril 10mg OD, Aspirin 100mg OD |
| Dietary Restrictions | Halal only, Low sodium, Low simple carbohydrates |
| Allergies | — |
| Notes | Office administrator, sedentary. Eats Nasi Lemak and Teh Tarik daily. HbA1c 8.2%, BP 148/92 mmHg. Struggles with late-night mamak habits. |

---

### P2 — Lim Siew Ching `L2`
| Field | Value |
|-------|-------|
| IC | 620318-10-5642 |
| Username | lim.siewching |
| Age / Gender | 64, Female, Chinese |
| Weight / Height / BMI | 61.5 kg / 155 cm / 25.6 |
| Conditions | Chronic Kidney Disease Stage 3, Hypertension |
| Medications | Amlodipine 5mg OD, Furosemide 40mg OD, Calcitriol 0.25mcg OD |
| Dietary Restrictions | Low potassium, Low phosphorus, Fluid restriction ≤1.5L/day, Low sodium |
| Allergies | Shellfish |
| Notes | Retired schoolteacher. eGFR 42 mL/min/1.73m². Loves dim sum and herbal soups — counselled on high-potassium soup stock. Lives alone. Compliant with medications. |

---

### P3 — Kavitha a/p Subramaniam `L1`
| Field | Value |
|-------|-------|
| IC | 910725-07-5890 |
| Username | kavitha.subra |
| Age / Gender | 35, Female, Indian |
| Weight / Height / BMI | 72.0 kg / 158 cm / 28.8 |
| Conditions | Polycystic Ovary Syndrome (PCOS), Insulin Resistance |
| Medications | Metformin 850mg OD, Inositol supplement 2g BD |
| Dietary Restrictions | Low glycaemic index, Anti-inflammatory diet preferred |
| Allergies | Peanuts |
| Notes | Software engineer, irregular meal patterns — often skips breakfast. Trying to conceive; dietary counselling requested by ObGyn. Enjoys Thosai and vegetable curries. Exercises occasionally. |

---

### P4 — Mohd Hafizuddin bin Salleh `L1`
| Field | Value |
|-------|-------|
| IC | 800512-14-6731 |
| Username | hafizuddin.salleh |
| Age / Gender | 46, Male, Malay |
| Weight / Height / BMI | 95.5 kg / 172 cm / 32.3 |
| Conditions | Dyslipidaemia, Obesity Class I |
| Medications | Atorvastatin 20mg ON, Fenofibrate 145mg OD |
| Dietary Restrictions | Halal only, Low saturated fat, Low cholesterol |
| Allergies | — |
| Notes | Lorry driver, irregular meal schedule. Total cholesterol 7.2 mmol/L, LDL 4.8 mmol/L. Frequent mamak meals: murtabak, roti canai with curry. Smokes 10 cigarettes/day. Resistant to dietary changes. |

---

### P5 — Tan Wei Loong `L2`
| Field | Value |
|-------|-------|
| IC | 681203-10-5123 |
| Username | tan.weiloong |
| Age / Gender | 58, Male, Chinese |
| Weight / Height / BMI | 78.0 kg / 165 cm / 28.7 |
| Conditions | Hypertension, Hypercholesterolaemia, Type 2 Diabetes |
| Medications | Metformin 1000mg BD, Perindopril 8mg OD, Rosuvastatin 10mg ON, Aspirin 75mg OD |
| Dietary Restrictions | Low sodium, Low simple carbohydrates, Low saturated fat, No pork (personal preference) |
| Allergies | Sulfa drugs (nursing reference only) |
| Notes | Retired civil servant. Eats hawker food 3x daily — char kway teow, economy rice. BP 155/95 mmHg, HbA1c 7.8%. Wife does all cooking; family-based counselling advised. |

---

### P6 — Nurul Ain binti Zulkifli `L0`
| Field | Value |
|-------|-------|
| IC | 990304-14-6218 |
| Username | nuraini.zulkifli |
| Age / Gender | 27, Female, Malay |
| Weight / Height / BMI | 56.0 kg / 162 cm / 21.3 |
| Conditions | — |
| Medications | — |
| Dietary Restrictions | Halal only |
| Allergies | — |
| Notes | Primary school teacher, active lifestyle — jogs 3x per week. No chronic conditions. Referred for general wellness and sports nutrition advice. Interested in optimising energy levels for long-distance running. |

---

### P7 — Rajendran a/l Muthu `L3`
| Field | Value |
|-------|-------|
| IC | 530818-07-5341 |
| Username | rajendran.muthu |
| Age / Gender | 73, Male, Indian |
| Weight / Height / BMI | 67.0 kg / 163 cm / 25.2 |
| Conditions | Post-CABG (3 months ago), Heart Failure (EF 35%), Type 2 Diabetes, Hypertension, CKD Stage 4 |
| Medications | Bisoprolol 5mg OD, Ramipril 2.5mg OD, Furosemide 80mg OD, Spironolactone 25mg OD, Insulin Glargine 20u ON, Aspirin 75mg OD, Clopidogrel 75mg OD, Atorvastatin 40mg ON |
| Dietary Restrictions | Cardiac diet, Fluid restriction ≤1.0L/day, Low sodium, Low potassium, Low phosphorus, Low simple carbohydrates |
| Allergies | ACE inhibitors (cough — tolerated at low dose, monitor) |
| Notes | Recent CABG with reduced ejection fraction. Any physical activity must be under cardiac rehab supervision only. High fall risk. BP 110/70 mmHg on current medications. eGFR 22 mL/min/1.73m². Family (wife and daughter) involved in all dietary decisions. |

---

## Personalization Levels Reference

| Level | Patient Profile | Content Scope |
|-------|----------------|---------------|
| L0 | No risk, no history, no limitations | Full spectrum including vigorous activity, performance goals |
| L1 | Emerging/moderate risk (early HTN, elevated BMI), no functional limits | Structured, safety-aware, moderation, do/don't boundaries |
| L2 | Established conditions, physical limitations, higher CV risk | Low-intensity, symptom monitoring, strict stop conditions |
| L3 | High clinical risk, recent cardiac events, disability | Medical oversight only, emergency education, minimal activity |
