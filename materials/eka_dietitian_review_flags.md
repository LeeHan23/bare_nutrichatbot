# EKA Content — Dietitian Review Flags

> **2026-09-28 status:**
> - Reviewer flags and comments now live in the review UI
>   (`docs-api.computationalrd.com/eka-review`, "Notes" per item, stored in
>   `content_materials.review_notes`), not in this file.
> - Reviewed weeks are exported on expiry to
>   `materials/eka_week{N}_reviewed.xlsx`; weeks 35–38 exist so far.
> - From 2026-09-08 they are also merged into one cumulative
>   `materials/eka_archive.xlsx`. It is created on the first expiry
>   cleanup after that change: week 35, due in the Monday 2026-09-28
>   06:00 run.
> - The id=68 flag below is historical, from the pre-retirement generator.

Items below are **live (`is_active=True`)** but flagged for a clinical accuracy double-check.
Approved on 2026-06-11 alongside the rest of the Week 22-24 EKA batch (63 items total) so
delivery isn't blocked, but this specific item should be reviewed and corrected if needed.

---

## Material id=68 — Week 24, CKD, Knowledge — "Slowing CKD Progression"

**Learning point: "Adopt a Low-Protein Diet"**

> Reduce your protein intake to lessen the workload on your kidneys. Focus on plant-based
> proteins like lentils and beans, which are common in Malaysian cuisine.

**Concern:** Lentils and beans (legumes) are typically high in potassium and phosphorus,
which are usually *restricted* for CKD patients (especially Stage 3-4, see patients like
Lim Siew Ching / Rajendran). Recommending them as a go-to low-protein swap may conflict
with the potassium/phosphorus guidance given elsewhere in the content library (e.g. the
W22 CKD "diet_kidneys" item, which correctly flags high-potassium foods to limit).

**Suggested fix:** Replace "lentils and beans" with a CKD-appropriate low-protein,
low-potassium/phosphorus example (e.g. egg white, or a smaller portion of lean meat/fish),
or add a caveat about portion size and consulting a dietitian before increasing legume intake.
