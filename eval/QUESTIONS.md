# Eval Questions Catalog

Every question used in the two eval suites, for reference without reading
Python source. This is a generated snapshot of `eval/test_rag.py` (34 cases)
and `eval/test_extractor.py` (20 cases) as of 2026-07-29 — **regenerate this
doc after adding/editing cases**, it is not read by either suite.

No pass/fail results here — see `eval/results/EVAL_REPORT.md` and
`eval/results/rag.json` / `extractor.json` for that.

---

## RAG suite (`eval/test_rag.py`) — 34 cases

Checks: **Voice** = second-person, no patient name. **Personalization** =
level-appropriate caution framing (L1/L2/L3), judged by LLM. **Contraindication**
= answer's actual clinical stance (RESTRICT/PERMIT/MODERATE), judged by LLM
against a list of acceptable stances — this is what catches a "fine in
moderation" answer for a food that should be restricted outright.

### Core / smoke cases

| # | Patient | Question | Checks |
|---|---|---|---|
| 1 | P2 — CKD Stage 3 + HTN | "What should I avoid eating?" | Voice; keyword (potassium/phosphorus/sodium/fluid, min 3) |
| 2 | P2 — CKD Stage 3 + HTN | "Can I eat bananas?" | Voice; contraindication: banana + CKD → RESTRICT only |
| 3 | P1 — T2DM + HTN | "Can I eat white rice?" | Voice; keyword (carb/portion/glycemic/blood sugar/limit) |
| 4 | P11 — Post-CABG + HF, L3 | "Can I start exercising?" | Personalization L3; keyword (supervised/doctor/cardiac rehab) |
| 5 | P5 — HTN + Hypercholesterolaemia + T2DM | "What cooking oil should I use?" | Voice; keyword (olive/canola/saturated/trans fat) |
| 6 | P3 — PCOS + Insulin Resistance | "What foods help with insulin resistance?" | Voice; keyword (fibre/whole grain/glycemic/vegetable) |
| 7 | P4 — Dyslipidaemia + Obesity I | "How much should I eat per day?" | Voice; keyword (calorie/portion/weight/serving) |
| 8 | P10 — L0 general wellness | "What is a healthy breakfast?" | Keyword (whole grain/protein/fibre/fruit/vegetable, min 1); forbidden (no CKD-style restriction language) |
| 9 | P1 — T2DM + HTN | "Tell me what I should eat for breakfast." | Voice (second-person, no name) |
| 10 | P11 — CKD Stage 4 | "How much protein should I eat?" | Voice; keyword (protein/restrict/limit/kidney/CKD/g per kg) |

### Contraindication matrix — CKD

| # | Patient | Question | Checks |
|---|---|---|---|
| 11 | P2 — CKD Stage 3 + HTN | "Can I eat durian?" | Voice; contraindication: durian + CKD (potassium) → RESTRICT only |
| 12 | P2 — CKD Stage 3 + HTN | "Can I drink milk every day?" | Voice; contraindication: milk/dairy + CKD (phosphorus) → RESTRICT or MODERATE |
| 13 | P2 — CKD Stage 3 + HTN | "Can I eat tomatoes?" | Voice; contraindication: tomato + CKD (potassium) → RESTRICT or MODERATE |
| 14 | P11 — Post-CABG + HF + CKD4, L3 | "Can I eat salted fish (ikan masin)?" | Personalization L3; contraindication: salted fish + HF/CKD4 (sodium) → RESTRICT only |

### Contraindication matrix — Hypertension

| # | Patient | Question | Checks |
|---|---|---|---|
| 15 | P1 — T2DM + HTN | "I heard bananas are good for blood pressure, can I eat them?" | Voice; contraindication (positive control): banana + HTN (no kidney disease) → PERMIT or MODERATE |
| 16 | P1 — T2DM + HTN, L2 | "Can I eat instant noodles (Maggi)?" | Voice; Personalization L2; contraindication: instant noodles + HTN (sodium) → RESTRICT only |
| 17 | P5 — HTN + Hypercholesterol + T2DM, L2 | "Can I eat acar (pickled vegetables)?" | Voice; Personalization L2; contraindication: acar + HTN → RESTRICT or MODERATE |

### Contraindication matrix — Type 2 Diabetes

| # | Patient | Question | Checks |
|---|---|---|---|
| 18 | P1 — T2DM + HTN | "Can I eat white bread for breakfast?" | Voice; contraindication: white bread + T2DM (high GI) → RESTRICT or MODERATE |
| 19 | P5 — HTN + Hypercholesterol + T2DM | "Can I have Teh Tarik in the morning?" | Voice; contraindication: Teh Tarik + T2DM (sugar) → RESTRICT or MODERATE |
| 20 | P1 — T2DM + HTN | "Is it okay for me to eat oats?" | Voice; contraindication (positive control): oats + T2DM → PERMIT or MODERATE |

### Contraindication matrix — Dyslipidaemia

| # | Patient | Question | Checks |
|---|---|---|---|
| 21 | P4 — Dyslipidaemia + Obesity, L1 | "Can I cook with coconut milk (santan)?" | Voice; Personalization L1; contraindication: coconut milk + Dyslipidaemia (sat. fat) → RESTRICT or MODERATE |
| 22 | P4 — Dyslipidaemia + Obesity | "Can I eat fried chicken regularly?" | Voice; contraindication: deep-fried chicken + Dyslipidaemia → RESTRICT or MODERATE |
| 23 | P5 — HTN + Hypercholesterol + T2DM | "Is ikan kembung (mackerel) good for me?" | Voice; contraindication (positive control): mackerel + Dyslipidaemia → PERMIT or MODERATE |

### Contraindication matrix — Heart Failure

| # | Patient | Question | Checks |
|---|---|---|---|
| 24 | P11 — Post-CABG + HF, L3 | "Can I have soup with my meals?" | Personalization L3; contraindication: soup/stock + HF (sodium) → RESTRICT or MODERATE |
| 25 | P11 — Post-CABG + HF, L3 | "Can I drink as much water as I want?" | Personalization L3; contraindication: unrestricted fluid + HF → RESTRICT or MODERATE |

### Contraindication matrix — PCOS / Insulin Resistance

| # | Patient | Question | Checks |
|---|---|---|---|
| 26 | P3 — PCOS + IR, L1 | "Can I eat white rice?" | Voice; Personalization L1; contraindication: white rice + PCOS/IR (high GI) → RESTRICT or MODERATE |
| 27 | P3 — PCOS + IR | "Is dhal (lentils) a good choice for me?" | Voice; contraindication (positive control): dhal + PCOS/IR → PERMIT or MODERATE |

### Contraindication matrix — Overweight / Pre-hypertension

| # | Patient | Question | Checks |
|---|---|---|---|
| 28 | P12 — Overweight + Pre-HTN, L1 | "Can I still eat mamak food like roti canai?" | Voice; Personalization L1; contraindication: roti canai (fried) + Overweight/Pre-HTN → RESTRICT or MODERATE |
| 29 | P12 — Overweight + Pre-HTN, L1 | "Is it okay to eat instant food often to save time?" | Voice; Personalization L1; contraindication: instant/processed food + Pre-HTN → RESTRICT or MODERATE |

### L0 general wellness control

| # | Patient | Question | Checks |
|---|---|---|---|
| 30 | P10 — L0 general wellness | "Can I eat bananas?" | Voice; contraindication (positive control): banana + no conditions → PERMIT or MODERATE; forbidden (no CKD-style restriction language) |

### Bilingual (Bahasa Malaysia)

| # | Patient | Question (BM) | Checks |
|---|---|---|---|
| 31 | P2 — CKD Stage 3 + HTN | "Bolehkah saya makan pisang?" (banana) | Contraindication: pisang + CKD → RESTRICT only |
| 32 | P1 — T2DM + HTN | "Bolehkah saya makan mi segera setiap hari?" (instant noodles, daily) | Contraindication: mi segera + HTN → RESTRICT only |
| 33 | P1 — T2DM + HTN | "Bolehkah saya makan nasi putih banyak-banyak?" (white rice, a lot) | Contraindication: nasi putih + T2DM → RESTRICT or MODERATE |
| 34 | P4 — Dyslipidaemia + Obesity, L1 | "Bolehkah saya makan gulai bersantan setiap hari?" (coconut milk curry, daily) | Personalization L1; contraindication: gulai bersantan + Dyslipidaemia → RESTRICT or MODERATE |

---

## Extractor suite (`eval/test_extractor.py`) — 20 cases

Checks: patient message → `extract_from_message()` → does the resulting
field dict match the expected fields/values (or, for negative cases, is it
empty)?

### English

| # | Message | Expected extraction |
|---|---|---|
| 1 | "I fry everything in palm oil and add lots of coconut milk to my curries every day." | `fat_intake_level: high`, `fat_sources: [palm oil]` |
| 2 | "I only cook with olive oil and mostly eat grilled fish and steamed vegetables." | `fat_intake_level: low`, `fat_sources: [olive oil]` |
| 3 | "I use butter and ghee daily when I cook." | `fat_intake_level: high`, `fat_sources: [butter, ghee]` |
| 4 | "I forgot to take my blood pressure medication twice this week." | `medication_compliance: variable` |
| 5 | "Honestly I stopped taking my statin about a month ago, I don't like side effects." | `medication_compliance: poor` |
| 6 | "I take all my tablets every morning without fail — I never miss a dose." | `medication_compliance: good` |
| 7 | "I go for a 30-minute brisk walk every morning." | `activity_types: [walking]`, `activity_freq: daily`, `activity_minutes: 30` |
| 8 | "I cycle to work on weekdays and swim on Saturday mornings." | `activity_types: [cycling, swimming]` |
| 9 | "I'm allergic to shellfish and tree nuts — I break out in hives." | `extractor_food_allergies: [shellfish, nuts]` |
| 10 | "I smoke about half a pack a day, have been doing it for 20 years." | `tobacco_status: Current smoker` |
| 11 | "I quit smoking 5 years ago." | `tobacco_status: Former smoker` |
| 12 | "I take fish oil and vitamin D every day." | `supplements: [fish oil, vitamin d]` |

### Bahasa Malaysia

| # | Message | Expected extraction |
|---|---|---|
| 13 | "Saya makan nasi lemak dengan banyak santan setiap pagi." | `fat_intake_level: high`, `fat_sources: [coconut milk]` (santan normalised) |
| 14 | "Kadang-kadang saya lupa ambil ubat darah tinggi saya." | `medication_compliance: variable` |
| 15 | "Saya alah dengan udang dan ketam, kalau makan terus gatal." | `extractor_food_allergies: [udang, ketam]` |
| 16 | "Saya tak pernah merokok langsung." | `tobacco_status: Never smoked` |
| 17 | "Saya main badminton dua kali seminggu, lebih kurang 45 minit." | `activity_types: [badminton]`, `activity_minutes: 45` |

### Manglish (mixed)

| # | Message | Expected extraction |
|---|---|---|
| 18 | "Aiyah, sometimes I forget lah my medication. Also I cook with coconut oil every day." | `medication_compliance: variable`, `fat_sources: [coconut oil]` |

### Negative (nothing to extract)

| # | Message | Expected extraction |
|---|---|---|
| 19 | "What foods are good for my heart?" | none (empty dict) |
| 20 | "Good morning! How are you today?" | none (empty dict) |
