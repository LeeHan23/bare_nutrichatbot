# Nutribot Dynamic Data Collection — Cardiac eNCPT Schema (v2)

**Specialty:** Cardiology
**Based on:** eNCPT 2020 + cardiac dietitian consultation (May 2026)
**Total fields:** 34 (4 new since v1)
**Languages:** English + Bahasa Malaysia

This document lists the patient information the chatbot will dynamically collect during conversation, 
specialized for **cardiac patients**. Each field is mapped to a standard **eNCPT 2020** code so the data 
can integrate with clinical workflows and electronic health records. Fields are organized by priority tier 
(cardiac-adjusted from the general eNCPT schema).

## Summary

| Tier | Description | Field Count |
|------|-------------|-------------|
| **Tier 1 — Critical** | Must collect for safe cardiac dietary advice. Bot should not give nutritional recommendations without these fields. | 7 |
| **Tier 2 — Important** | Significantly improves the quality and personalization of cardiac advice. Collect during the first few sessions. | 17 |
| **Tier 3 — Nice to Have** | Adds context and supports long-term care. Collect opportunistically during conversation. | 10 |

## Changes for Cardiac Focus (v2 vs v1)

### New fields added (per dietitian)

| Code | Field | Tier |
|------|-------|------|
| `FH-1.5.1.1` | Total fat intake (qualitative estimate from food sources) | tier1 |
| `FH-3.1.1.1` | Medication compliance | tier2 |
| `FH-1.5.1.2` | Fat type sources (raw food sources mentioned) | tier2 |
| `FH-7.3.1.1` | Type of physical activity | tier2 |

### Promoted fields (more critical for cardiac)

- `FH-1.5.6.1` **Sodium intake / awareness** — Promoted from T2 → T1 for cardiac focus

### Demoted fields (less critical for cardiac)

- `FH-3.2.1` **Vitamin/mineral supplement intake** — Demoted from T1 → T3 for cardiac focus per dietitian

## How to Read This Schema

- **eNCPT Code**: Standardized terminology code from the Academy of Nutrition and Dietetics.
- **Field Description**: What the bot is trying to learn about the patient.
- **Data Type**: Format the field is stored in. `allowed_values` show valid options where applicable.
- **Example Question (EN/MS)**: How the bot might naturally ask, in English and Bahasa Malaysia.
- **Example Patient Answer**: Typical response the extractor should be able to handle.
- **Most Relevant For**: Clinical conditions where this field is especially important.
- **Clinical Relevance**: Why this matters for cardiac care.

## Tier 1 — Critical

_Must collect for safe cardiac dietary advice. Bot should not give nutritional recommendations without these fields._

| eNCPT Code | Field | Data Type | Most Relevant For |
|------------|-------|-----------|-------------------|
| `FH-1.2.1.1.1` | Total fluid estimated intake in 24 hours | Number (mL) | Heart Failure, CKD, Hypertension |
| `FH-1.4.1.1` | Alcohol intake in one week | Number (drinks) | All patients |
| `CH-1.1.10` | Tobacco use | Free text — values: `Never smoked, Current smoker, Former smoker` | Cardiac, Hypertension, Dyslipidemia |
| `FH-1.5.1.1` | Total fat intake (qualitative estimate from food sources) 🆕 | Free text — values: `low, moderate, high` | Cardiac, Dyslipidemia |
| `FH-1.5.6.1` | Sodium intake / awareness | Free text — values: `low_awareness_high_intake, moderate, actively_restricting` | Cardiac, Hypertension, Heart Failure, CKD |
| `FH-1.6` | Food allergies and intolerances | List of strings | All patients |
| `CH-3.1.7` | Religion (affects diet) | Free text | All patients |

### Tier 1 — Critical — Detailed Cards

#### `FH-1.2.1.1.1` — Total fluid estimated intake in 24 hours

**Clinical relevance:** Heart failure patients have fluid restriction; over-intake worsens edema and dyspnea

> **Bot (EN):** About how much fluid do you drink in a typical day?
>
> **Bot (MS):** Berapa banyak cecair (air, kopi, teh, dll) yang anda minum dalam sehari?
>
> **Patient:** "I drink about 6 glasses of water plus 2 cups of coffee"

#### `FH-1.4.1.1` — Alcohol intake in one week

**Clinical relevance:** Alcohol elevates BP and triglycerides; affects warfarin and antiarrhythmics

> **Bot (EN):** How much alcohol do you drink in a typical week?
>
> **Bot (MS):** Berapa banyak alkohol yang anda minum dalam seminggu?
>
> **Patient:** "Maybe 2-3 beers on weekends"

#### `CH-1.1.10` — Tobacco use

**Clinical relevance:** Major modifiable risk factor for ischemic heart disease

> **Bot (EN):** Do you currently smoke or use any tobacco?
>
> **Bot (MS):** Adakah anda merokok atau menggunakan tembakau?
>
> **Patient:** "I quit 5 years ago"

#### `FH-1.5.1.1` — Total fat intake (qualitative estimate from food sources) 🆕 NEW

**Clinical relevance:** Total fat affects LDL and overall cardiovascular risk

**Extractor note:** Estimate qualitative level (low/moderate/high) from food sources mentioned. Don't ask patients for grams.

> **Bot (EN):** How often do you eat fried foods, fatty meats, or oily curries?
>
> **Bot (MS):** Berapa kerap anda makan makanan goreng, daging berlemak, atau kari berminyak?
>
> **Patient:** "Most days I have nasi lemak or fried chicken"

#### `FH-1.5.6.1` — Sodium intake / awareness

**Clinical relevance:** Direct driver of hypertension and fluid retention in heart failure

**Note:** Promoted from T2 → T1 for cardiac focus

> **Bot (EN):** How salty do you like your food, and do you ever check labels for sodium?
>
> **Bot (MS):** Adakah anda suka makanan masin, dan adakah anda memeriksa kandungan garam pada label?
>
> **Patient:** "I add salt to almost everything, never check labels"

#### `FH-1.6` — Food allergies and intolerances

**Clinical relevance:** Required to ensure dietary recommendations are safe

> **Bot (EN):** Do you have any food allergies or foods that make you feel unwell?
>
> **Bot (MS):** Adakah anda alah kepada makanan atau ada makanan yang membuat anda tidak sihat?
>
> **Patient:** "I'm allergic to shellfish and dairy gives me stomach issues"

#### `CH-3.1.7` — Religion (affects diet)

**Clinical relevance:** Required to ensure dietary recommendations are culturally acceptable

> **Bot (EN):** Are there foods you avoid for religious or cultural reasons?
>
> **Bot (MS):** Adakah ada makanan yang anda elak atas sebab agama atau budaya?
>
> **Patient:** "I'm Muslim so I only eat halal, no pork"

---

## Tier 2 — Important

_Significantly improves the quality and personalization of cardiac advice. Collect during the first few sessions._

| eNCPT Code | Field | Data Type | Most Relevant For |
|------------|-------|-----------|-------------------|
| `FH-3.1.1.1` | Medication compliance 🆕 | Free text — values: `good, variable, poor` | Cardiac, Hypertension, Heart Failure |
| `FH-1.5.1.2` | Fat type sources (raw food sources mentioned) 🆕 | List of strings | Cardiac, Dyslipidemia |
| `FH-7.3.1` | Physical activity frequency | Free text | All patients |
| `FH-7.3.2` | Physical activity duration | Number (minutes) | All patients |
| `FH-7.3.1.1` | Type of physical activity 🆕 | List of strings | Cardiac, Heart Failure |
| `FH-7.3.3` | Physical activity intensity | Free text — values: `light, moderate, vigorous` | Cardiac, Heart Failure |
| `FH-1.4.3.1` | Total caffeine estimated intake in 24 hours | Number (mg) | Cardiac, Hypertension, Atrial Fibrillation |
| `FH-1.2.2.3.1.1` | Number of meals estimated in 24 hours | Number | Diabetes, Hypertension |
| `FH-1.2.2.3.1.2` | Number of snacks estimated in 24 hours | Number | Diabetes, Obesity |
| `FH-1.2.2.2.5` | Processed food intake | Free text | Cardiac, Hypertension, Dyslipidemia, Obesity |
| `FH-1.2.2.2.6` | Quick service food intake | Free text | Cardiac, Hypertension, Dyslipidemia, Obesity, Diabetes |
| `FH-1.2.2.2.7` | Self prepared food intake | Free text | All patients |
| `FH-1.2.1.1.1.3` | Sugar sweetened beverage estimated oral intake in 24 hours | Number (mL) | Diabetes, Obesity, Cardiac |
| `FH-5.2.1` | Food avoidance | List of strings | All patients |
| `FH-5.4.1` | Cultural/religious eating practices | Free text | All patients |
| `FH-4.1.3` | Nutrition knowledge of individual client | 1–5 scale | All patients |
| `FH-4.2.8` | Readiness to change nutrition-related behaviors | Behavior change stage — values: `precontemplation, contemplation, preparation, action, maintenance` | All patients |

### Tier 2 — Important — Detailed Cards

#### `FH-3.1.1.1` — Medication compliance 🆕 NEW

**Clinical relevance:** Non-compliance with antihypertensives, statins, or anticoagulants directly worsens outcomes

> **Bot (EN):** Are you taking your medications as prescribed?
>
> **Bot (MS):** Adakah anda mengambil ubat seperti yang ditetapkan oleh doktor?
>
> **Patient:** "Sometimes I forget the evening dose"

#### `FH-1.5.1.2` — Fat type sources (raw food sources mentioned) 🆕 NEW

**Clinical relevance:** Saturated/trans fat sources matter more than total fat for cardiac patients

**Extractor note:** Capture raw food sources (palm oil, butter, ghee, olive oil, etc.); separate clinical layer maps to saturated/trans/unsaturated categories

> **Bot (EN):** What kinds of cooking oils, butter, or fatty foods do you usually have?
>
> **Bot (MS):** Jenis minyak masak atau makanan berlemak apa yang biasa anda makan?
>
> **Patient:** "I cook with palm oil and use butter on toast"

#### `FH-7.3.1` — Physical activity frequency

**Clinical relevance:** Frequency drives cardiac rehabilitation outcomes

> **Bot (EN):** How often do you exercise or do physical activity?
>
> **Bot (MS):** Berapa kerap anda bersenam atau melakukan aktiviti fizikal?
>
> **Patient:** "I walk for 30 minutes 3 times a week"

#### `FH-7.3.2` — Physical activity duration

**Clinical relevance:** Total weekly minutes determine training effect

> **Bot (EN):** About how long do your exercise sessions last?
>
> **Bot (MS):** Lama setiap sesi senaman anda berapa minit?
>
> **Patient:** "30 to 45 minutes each time"

#### `FH-7.3.1.1` — Type of physical activity 🆕 NEW

**Clinical relevance:** Aerobic vs resistance vs flexibility have different cardiac benefits

> **Bot (EN):** What kind of exercise do you do — walking, swimming, gym, sports?
>
> **Bot (MS):** Jenis senaman apa yang anda lakukan — berjalan, berenang, gim, atau sukan?
>
> **Patient:** "Mostly walking, sometimes I cycle on weekends"

#### `FH-7.3.3` — Physical activity intensity

**Clinical relevance:** Vigorous activity may be contraindicated in some cardiac conditions

> **Bot (EN):** Would you describe your exercise as light, moderate, or vigorous?
>
> **Bot (MS):** Senaman anda boleh dikatakan ringan, sederhana, atau cergas?
>
> **Patient:** "Moderate - I get a bit out of breath"

#### `FH-1.4.3.1` — Total caffeine estimated intake in 24 hours

**Clinical relevance:** Excess caffeine can trigger arrhythmias and elevate BP

> **Bot (EN):** How much coffee or tea do you drink a day?
>
> **Bot (MS):** Berapa banyak kopi atau teh yang anda minum sehari?
>
> **Patient:** "Two cups of coffee in the morning"

#### `FH-1.2.2.3.1.1` — Number of meals estimated in 24 hours

**Clinical relevance:** Meal pattern affects glycemic control and energy distribution

> **Bot (EN):** How many meals do you eat in a day?
>
> **Bot (MS):** Berapa kali anda makan dalam sehari?
>
> **Patient:** "Three main meals plus 2 snacks usually"

#### `FH-1.2.2.3.1.2` — Number of snacks estimated in 24 hours

**Clinical relevance:** Frequent snacking may reflect calorie excess

> **Bot (EN):** How many snacks do you have between meals?
>
> **Bot (MS):** Berapa kali anda makan snek antara waktu makan?
>
> **Patient:** "1 or 2 snacks usually"

#### `FH-1.2.2.2.5` — Processed food intake

**Clinical relevance:** Processed foods are major source of sodium and trans fats

> **Bot (EN):** How often do you eat processed or packaged foods?
>
> **Bot (MS):** Berapa kerap anda makan makanan diproses atau makanan dalam tin/bungkus?
>
> **Patient:** "Maybe once a week, mostly home-cooked"

#### `FH-1.2.2.2.6` — Quick service food intake

**Clinical relevance:** Fast food typically high in saturated fat, sodium, and refined carbs

> **Bot (EN):** How often do you eat fast food or takeaway?
>
> **Bot (MS):** Berapa kerap anda makan makanan segera atau bawa pulang?
>
> **Patient:** "Twice a week or so"

#### `FH-1.2.2.2.7` — Self prepared food intake

**Clinical relevance:** Determines who needs nutrition education and meal control

> **Bot (EN):** Do you usually cook your own meals or does someone else?
>
> **Bot (MS):** Biasanya anda yang masak sendiri atau orang lain yang masak?
>
> **Patient:** "My wife cooks most days"

#### `FH-1.2.1.1.1.3` — Sugar sweetened beverage estimated oral intake in 24 hours

**Clinical relevance:** Liquid sugar contributes to obesity, insulin resistance, hypertriglyceridemia

> **Bot (EN):** Do you drink sweetened drinks like soda, juice, or sweetened tea?
>
> **Bot (MS):** Adakah anda minum minuman manis seperti air kotak, jus, atau teh manis?
>
> **Patient:** "I have one teh tarik a day"

#### `FH-5.2.1` — Food avoidance

**Clinical relevance:** Voluntary restrictions inform what dietary advice will be acceptable

> **Bot (EN):** Are there any foods you avoid eating, and why?
>
> **Bot (MS):** Adakah ada makanan yang anda elak makan, dan kenapa?
>
> **Patient:** "I avoid fatty foods because they upset my stomach"

#### `FH-5.4.1` — Cultural/religious eating practices

**Clinical relevance:** Cultural norms shape food choices; advice must be culturally adapted

> **Bot (EN):** Are there cultural or family traditions that shape what you eat?
>
> **Bot (MS):** Adakah amalan budaya atau tradisi keluarga yang mempengaruhi pemakanan anda?
>
> **Patient:** "We always have rice with every meal"

#### `FH-4.1.3` — Nutrition knowledge of individual client

**Clinical relevance:** Determines depth of education needed

> **Bot (EN):** How familiar are you with what foods to eat for your condition?
>
> **Bot (MS):** Sejauh mana anda tahu makanan yang sesuai untuk keadaan kesihatan anda?
>
> **Patient:** "I know I should eat less salt but not much else"

#### `FH-4.2.8` — Readiness to change nutrition-related behaviors

**Clinical relevance:** Stage of change determines intervention approach

> **Bot (EN):** How ready do you feel to make changes to your diet?
>
> **Bot (MS):** Sejauh mana anda bersedia untuk mengubah pemakanan anda?
>
> **Patient:** "I'm trying to eat less rice already"

---

## Tier 3 — Nice to Have

_Adds context and supports long-term care. Collect opportunistically during conversation._

| eNCPT Code | Field | Data Type | Most Relevant For |
|------------|-------|-----------|-------------------|
| `FH-3.2.1` | Vitamin/mineral supplement intake | List of strings | All patients |
| `FH-6.2.1` | Food availability | Free text | All patients |
| `FH-1.4.1.4` | Alcohol intake pattern on drinking days | Free text | Liver, Hypertension, Cardiac |
| `FH-6.2.3` | Access to food preparation equipment | Yes / No | All patients |
| `FH-5.4.2` | Eating environment (alone/with family/etc) | Free text | All patients |
| `CH-3.1.9` | Daily stress level | 1–10 scale | Cardiac, Hypertension |
| `CH-3.1.6` | Occupation | Free text | All patients |
| `CH-3.1.4` | Social and medical support | Free text | All patients |
| `FH-1.5.4.5` | Fiber estimated intake | Free text | Diabetes, Dyslipidemia, Cardiac, Obesity |
| `FH-8.1` | Nutrition quality of life | 1–5 scale | All patients |

### Tier 3 — Nice to Have — Detailed Cards

#### `FH-3.2.1` — Vitamin/mineral supplement intake

**Clinical relevance:** Common cardiac supplements (fish oil, CoQ10, K, Mg) interact with medications

**Note:** Demoted from T1 → T3 for cardiac focus per dietitian

> **Bot (EN):** Are you taking any vitamins, minerals, or other supplements?
>
> **Bot (MS):** Adakah anda mengambil sebarang vitamin, mineral, atau suplemen?
>
> **Patient:** "I take fish oil and CoQ10 daily"

#### `FH-6.2.1` — Food availability

**Clinical relevance:** Affects feasibility of dietary recommendations

> **Bot (EN):** Is it easy for you to buy fresh fruit, vegetables, and lean proteins?
>
> **Bot (MS):** Adakah mudah untuk anda membeli buah-buahan, sayur-sayuran, dan protein yang sihat?
>
> **Patient:** "Yes, there's a market nearby"

#### `FH-1.4.1.4` — Alcohol intake pattern on drinking days

**Clinical relevance:** Binge pattern more harmful than equivalent spread intake

> **Bot (EN):** On days you drink, do you usually have one drink or several?
>
> **Bot (MS):** Pada hari anda minum, biasanya satu gelas atau beberapa gelas?
>
> **Patient:** "Usually 2-3 in one sitting"

#### `FH-6.2.3` — Access to food preparation equipment

**Clinical relevance:** Affects whether home-cooking advice is realistic

> **Bot (EN):** Do you have a kitchen with a stove and refrigerator?
>
> **Bot (MS):** Adakah anda mempunyai dapur dengan dapur masak dan peti sejuk?
>
> **Patient:** "Yes, just basic but it works"

#### `FH-5.4.2` — Eating environment (alone/with family/etc)

**Clinical relevance:** Social context affects portion control and food choices

> **Bot (EN):** Do you usually eat alone or with others?
>
> **Bot (MS):** Biasanya anda makan seorang diri atau bersama orang lain?
>
> **Patient:** "With my family for dinner, lunch is at work"

#### `CH-3.1.9` — Daily stress level

**Clinical relevance:** Stress drives BP elevation and unhealthy coping behaviors

> **Bot (EN):** How stressful would you say your daily life is, on a scale of 1 to 10?
>
> **Bot (MS):** Pada skala 1 hingga 10, sejauh mana stres dalam kehidupan harian anda?
>
> **Patient:** "About a 7, work has been intense"

#### `CH-3.1.6` — Occupation

**Clinical relevance:** Occupation influences activity level and meal patterns

> **Bot (EN):** What do you do for work?
>
> **Bot (MS):** Apakah pekerjaan anda?
>
> **Patient:** "I'm a teacher, mostly desk work"

#### `CH-3.1.4` — Social and medical support

**Clinical relevance:** Support network predicts adherence and outcomes

> **Bot (EN):** Do you have family or friends helping you manage your health?
>
> **Bot (MS):** Adakah keluarga atau kawan yang membantu anda menjaga kesihatan?
>
> **Patient:** "My daughter helps with my appointments"

#### `FH-1.5.4.5` — Fiber estimated intake

**Clinical relevance:** Fiber lowers LDL cholesterol; relevant for cardiac too

> **Bot (EN):** Do you eat whole grains, beans, or lots of fruits and vegetables?
>
> **Bot (MS):** Adakah anda makan bijirin penuh, kekacang, atau banyak buah dan sayur?
>
> **Patient:** "Some fruit daily, mostly white rice for grains"

#### `FH-8.1` — Nutrition quality of life

**Clinical relevance:** Predicts long-term adherence and satisfaction

> **Bot (EN):** How happy are you with the way you eat right now?
>
> **Bot (MS):** Sejauh mana anda berpuas hati dengan pemakanan anda sekarang?
>
> **Patient:** "Not really, I want to change but it's hard"

---

## Notes for Reviewing Dietitians

This v2 schema reflects the cardiac-focused priorities discussed. Please review:

1. **Cardiac tier assignments** — Are any fields in the wrong tier for cardiac patients?
2. **New fields** — Do `Total fat intake`, `Fat type sources`, `Medication compliance`, 
   and `Type of physical activity` capture what you intended?
3. **Bahasa Malaysia phrasing** — Are the BM questions natural for Malaysian patients? 
   Should some be more colloquial (e.g., using 'nak' instead of 'mahu')?
4. **Allowed values** — For fields like `medication compliance` (good/variable/poor) 
   and `fat intake` (low/moderate/high), are these the right buckets?
5. **Other cardiac sub-conditions** — When ready to differentiate (e.g., heart failure vs 
   ischemic heart disease vs valvular), what fields would shift in priority?

Please mark any suggested changes directly in this document or send feedback to Lee Yean Han.