# Nutribot EKA API Schema for MHC

As of 2026-11-17

This is everything the My Heart Coach app receives from Nutribot's EKA feed, field by field, so both sides build against the same shape. Content currently served is week 42, the latest approved week.

## 1. Request

One GET call per user, keyed by the phone number stored in the MHC `users` table.

```
GET https://nutribot.computationalrd.com/content/patient-feed?phone_number=%2B60123456789
X-API-Key: <MHC_API_KEY>
```

| Parameter | Required | Type | Notes |
| --- | --- | --- | --- |
| `phone_number` | Yes | string | `+60...` or `60...`, both match. URL-encode the `+` as `%2B`. |
| `week_number` | No | int | ISO week. Leave it out to get the current week, or the latest approved week if the current one isn't approved. |
| `is_active` | No | bool | Default `true` (approved content only). Leave as default. |

| Status | Meaning |
| --- | --- |
| `200` | Feed returned. `total` can be `0` if no item matches the user's groups and level. |
| `401` | Missing or wrong `X-API-Key`. |
| `403` | The key is valid but isn't the My Heart Coach key. |
| `404` | No user with that phone number in the MHC database. |

## 2. Response envelope

The user's profile is read live from the MHC database on every call. Nothing is copied to Nutribot.

| Field | Type | Example | Notes |
| --- | --- | --- | --- |
| `phone_number` | string | `+60173362070` | As normalised by Nutribot. |
| `patient_name` | string | `Ali` | From MHC `users`. |
| `condition_groups` | string[] | `["General"]` | MHC conditions mapped to Nutribot content groups. |
| `personalization_level` | string or null | `L0` | `L0`-`L3`, after safety floors: HF, MI, stroke or CKD raise it to L3; hypertension or diabetes to L2. |
| `onboarding_stage` | string or null | `null` | `OB1`-`OB3` while onboarding is unfinished, else `null`. |
| `week_number` | int | `42` | The week actually served. |
| `fallback_from_week` | int or null | `47` | Set when the current week isn't approved yet and an older week was served instead. |
| `is_active` | bool | `true` | Echo of the request filter. |
| `feed` | object | `{"E": [...], "K": [...], "A": [...]}` | Always all three keys; each is a list of items (section 3). |
| `total` | int | `3` | Number of items across E, K and A. |

Content groups: T2DM, HTN, CKD, Cardiac, PCOS, Dyslipidaemia, Heart Failure, Atrial Fibrillation, CVD Risk Management, Mental Health, Stress Management, Sleep, General.

## 3. Item fields

Every item in `feed.E`, `feed.K` and `feed.A` has the same wrapper. Only `content` differs by type.

| Field | Type | Example | Notes |
| --- | --- | --- | --- |
| `id` | int | `1736` | Stable Nutribot id. Use it as the task id for completion tracking. |
| `content_type` | string | `E` | `E`, `K` or `A`. |
| `content_type_label` | string | `Exercise` | `Exercise`, `Knowledge` or `Activity`. |
| `condition_group` | string | `T2DM` | One of the content groups above. |
| `condition_tags` | string[] | `["Type 2 Diabetes"]` | Conditions the item was written for. |
| `personalization_level` | string or null | `L1` | Set XOR `onboarding_stage`. |
| `onboarding_stage` | string or null | `null` | `OB1`-`OB3`. |
| `week_number` | int | `42` | ISO week the item was generated for. |
| `day_offset` | int or null | `null` | Always `null` for EKA. |
| `topic` | string | `resistance_basics` | Machine slug. |
| `title` | string | `Week 42 — Resistance Training for Insulin Sensitivity` | Display title. |
| `is_active` | bool | `true` | Approved by the dietitian team. |
| `content` | object | see sections 4-6 | Type-specific body. |
| `review_notes` | object[] | `[]` | Internal reviewer comments. Not for display. |
| `created_at` | ISO datetime | `2026-10-11T22:00:44` | UTC. |
| `expires_at` | ISO datetime | `2026-11-10T22:00:44` | UTC. |
| `is_expired` | bool | `true` | Week 42 is past expiry but is still served as the fallback week. Don't filter on it. |

## 4. Exercise (E) content

E items frame exercises picked from the approved Exercise Video catalog for the user's level. Each highlight carries its catalog YouTube link in `video_url`.

| Field | Type | Notes |
| --- | --- | --- |
| `framing` | string | 1-2 sentences on this week's focus. |
| `catalog_highlights` | object[] | Always 2 catalog exercises allowed for the item's level. If an item was generated with none (14 of 77 in week 42), the API fills 2 from the catalog at serve time, within the level's type and intensity limits (L3: cool-down, Light only). |
| `catalog_highlights[].title` | string | Exact title from the catalog, e.g. `0032 – Walking Calf Raise`. |
| `catalog_highlights[].why_it_helps` | string | One sentence. |
| `catalog_highlights[].type` | string | e.g. `Warm Up/Aerobic`, `Strength/Resistance`. |
| `catalog_highlights[].intensity_tier` | string | `Light`, `Moderate` or `Vigorous`. |
| `catalog_highlights[].body_focus` | string | e.g. `Lower Body (Calf)`. |
| `catalog_highlights[].video_duration` | string | `m:ss`. |
| `catalog_highlights[].video_url` | string | YouTube link for that exercise, from the approved catalog. Each catalog title has exactly one link. |
| `catalog_highlights[].explanation` | string | How the exercise is done, from the approved catalog (Malay). Describes what the video at `video_url` shows. |
| `catalog_highlights[].auto_filled` | bool (optional) | `true` when the API filled the exercise from the catalog. Its `why_it_helps` is the catalog's own explanation, in Malay. |
| `general_safety_note` | string | Stop conditions and care-team check. |
| `malaysian_context` | string | Local practicality tip. |

```json
{
  "framing": "This week, we focus on simple resistance exercises that can improve insulin sensitivity. Gentle movement is key for managing T2DM effectively.",
  "catalog_highlights": [
    {
      "title": "0032 – Walking Calf Raise",
      "why_it_helps": "Strengthens calf muscles, promoting better blood flow and muscle tone.",
      "type": "Strength/Resistance",
      "intensity_tier": "Moderate",
      "body_focus": "Lower Body (Calf)",
      "video_duration": "0:30",
      "video_url": "https://youtu.be/7j87b4dVk2c",
      "explanation": "Pergerakan berjalan dengan mengangkat tumit secara bergilir semasa langkah. Pergerakan melibatkan sendi buku lali serta penggunaan otot bahagian bawah kaki semasa pergerakan kaki."
    }
  ],
  "general_safety_note": "Always stop if you experience chest pain, severe breathlessness, or dizziness. Check with your care team before starting any new exercise.",
  "malaysian_context": "Exercises can be done indoors to avoid the heat, making them practical for all weather conditions."
}
```

## 5. Knowledge (K) content

K items are a short lesson. Every week-42 K item has exactly 6 learning points.

| Field | Type | Notes |
| --- | --- | --- |
| `topic_summary` | string | 1-2 sentence intro. |
| `learning_points` | object[] | 6 items. |
| `learning_points[].point` | string | Short heading, e.g. `What is GI?`. |
| `learning_points[].explanation` | string | 1-2 sentences. |
| `learning_points[].why_it_matters` | string | One sentence. |
| `key_takeaway` | string | One sentence. |
| `local_context` | string | Malaysian food or lifestyle angle. |

```json
{
  "topic_summary": "Understanding how common Malaysian foods like nasi, roti, mee and kuih affect blood sugar through their GI and GL can help manage T2DM.",
  "learning_points": [
    {
      "point": "What is GI?",
      "explanation": "Glycaemic Index (GI) measures how quickly a food raises blood sugar levels.",
      "why_it_matters": "Choosing foods with lower GI helps maintain steady blood sugar levels."
    }
  ],
  "key_takeaway": "Choosing foods with lower GI and GL values helps manage blood sugar levels more effectively.",
  "local_context": "In Malaysia, understanding how traditional foods like nasi, roti, mee and kuih affect blood sugar is crucial for managing T2DM."
}
```

## 6. Activity (A) content

A items are a one-week habit task with a daily breakdown.

| Field | Type | Notes |
| --- | --- | --- |
| `task_name` | string | Short name, e.g. `Glucose Tracker`. |
| `description` | string | One sentence. |
| `instructions` | string[] | 3-4 steps. |
| `tracking_method` | string | How to log it. |
| `weekly_goal` | string | What counts as done for the week. |
| `micro_actions` | string[] | 6 entries: Monday to Friday, then Weekend. |
| `self_monitoring_prompts` | string[] | 2 reflection questions. |
| `success_looks_like` | string | One sentence. |

```json
{
  "task_name": "Glucose Tracker",
  "description": "Record your meals and blood glucose levels to identify patterns that affect your diabetes management.",
  "instructions": [
    "After each meal, note down what you ate in detail.",
    "Check your blood glucose level using your glucometer.",
    "Write down the time of measurement and the result in mg/dL.",
    "Reflect on how your meals might have influenced your readings."
  ],
  "tracking_method": "Use a dedicated app or a paper chart to log your meals and glucose levels daily.",
  "weekly_goal": "Complete at least one entry per meal for seven days straight without missing any entries.",
  "micro_actions": [
    "Monday: Start logging every meal and blood sugar reading.",
    "Tuesday: Review yesterday's logs, look for patterns or spikes.",
    "...",
    "Weekend: Keep up the logging, especially noting different meal patterns or special foods."
  ],
  "self_monitoring_prompts": [
    "Did I eat more of one type of food today that affected my glucose levels?",
    "How did my activity level today impact my blood sugar readings?"
  ],
  "success_looks_like": "Seven days of consistent logging with reflections on meal and activity patterns noted."
}
```

## 7. Gap vs the RulesPolicy EKA schema

Our content doesn't follow the RulesPolicy "Task Generation Engine" format yet. 6 schema fields have no equivalent, and the mandatory `stop_conditions[]` is a sentence inside `general_safety_note`, not a list.

| Type | RulesPolicy field | Nutribot field today | Status |
| --- | --- | --- | --- |
| All | `type` | `content_type` | Match |
| All | `title` | `title` | Match |
| E | `description` | `framing` | Renamed |
| E | `exercise_type` | `catalog_highlights[].type` | Per exercise, not per item |
| E | `intensity` | `catalog_highlights[].intensity_tier` | Per exercise, not per item |
| E | `duration` | `catalog_highlights[].video_duration` | Video length, not session length |
| E | `frequency` | — | Missing |
| E | `instructions[]` | — | Missing |
| E | `stop_conditions[]` (mandatory) | inside `general_safety_note` (string) | Not a list |
| E | `safety_note` (mandatory) | `general_safety_note` | Renamed |
| E | `progression` | — | Missing |
| E | (video link) | `catalog_highlights[].video_url` | Added |
| K | `topic` | `topic` (slug) + `topic_summary` | Partial |
| K | `key_points[]` (max 3) | `learning_points[]` (6 objects) | Too many, different shape |
| K | `actionable_tip` | `key_takeaway` | Closest match |
| K | `warning_signs` | — | Missing |
| A | `suggested_activity` | `task_name` + `description` | Split |
| A | `frequency` | — | Missing (`weekly_goal` is a target, not a frequency) |
| A | `reminder_or_nudge` | `micro_actions[]` | Partial |
| A | `adaptation_tip` | — | Missing |

Fields we add that the schema doesn't have: `malaysian_context`, `local_context`, `tracking_method`, `self_monitoring_prompts`, `success_looks_like`.

## 8. Open questions for the MHC team

1. Should Nutribot switch `content` to the RulesPolicy schema shape, or will the app map today's fields? Switching changes generation for the coming weeks; mapping needs no change on our side.
2. Will the app store the item `id` against its own completion logs (`user_exercise_logs` and the others), so finished tasks drop off the list?
3. Is phone number the right key long term, or will MHC send a stable user id?
4. How often will the app call: once per user per day, or on every screen open?
