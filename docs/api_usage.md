# Nutribot API — integration details

Three separate APIs, depending on what the calling application needs:

1. **Patient Chat API** — personalized nutrition advice tied to a patient profile (conditions, medications, restrictions). Public, hosted.
2. **Docs API** — plain document-grounded nutrition Q&A, no patient data, no mock database involved. Standalone service (`docs_api.py`), not yet publicly hosted.
3. **Weekly EKA Content API** — fetch/approve the Exercise/Knowledge/Activity content library. Mounted on the Patient Chat API host under `/content`.

All three are plain REST + JSON — no SDK needed.

**Keys below are placeholders** (`<NUTRIBOT_API_KEY>` / `<DOCS_API_KEY>`) — get the real values from `.env` (`NUTRIBOT_API_KEY`, `DOCS_API_KEY`), never commit or paste the real key into this file.

---

## 1. Patient Chat API

### Endpoint

```
POST https://nutribot.computationalrd.com/chat/get_response_sync
```

### Headers

```
Content-Type: application/json
X-API-Key: <NUTRIBOT_API_KEY>
```

### Request body

```json
{
  "question": "What should I eat for breakfast?",
  "patient_id": 2,
  "session_id": "your-app-session-1"
}
```

- `question` (string, required) — the user's message.
- `session_id` (string, required) — one per conversation; reused session IDs carry chat history.
- `patient_id` (int, optional) — loads that patient's clinical profile automatically for personalized answers. Omit both this and `profile` for plain, unpersonalized answers from the same endpoint.
- `profile` (object, optional) — pass an explicit profile dict instead of `patient_id` (legacy path, skip unless needed).
- `is_patient_self` (bool, optional) — defaults to `true` when `patient_id` is set.

### Response

```json
{
  "answer": "For breakfast, aim for around 10-15 grams of protein from low-phosphorus and low-sodium sources...",
  "session_id": "your-app-session-1"
}
```

### Timing

First call ~30-60s (cold start), warm calls ~10-30s. Set your client timeout to at least 100s.

### Integration — curl

```bash
curl -X POST https://nutribot.computationalrd.com/chat/get_response_sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <NUTRIBOT_API_KEY>" \
  -d '{"question":"What should I eat for breakfast?","patient_id":2,"session_id":"your-app-session-1"}'
```

### Integration — Python

```python
import requests

resp = requests.post(
    "https://nutribot.computationalrd.com/chat/get_response_sync",
    headers={"X-API-Key": "<NUTRIBOT_API_KEY>"},
    json={"question": "What should I eat for breakfast?", "patient_id": 2, "session_id": "your-app-session-1"},
    timeout=100,
)
print(resp.json()["answer"])
```

### Streaming variant

If you need token-by-token output instead of a single blocking response, use `POST /chat/get_response` (Server-Sent Events) instead of `get_response_sync` — same headers and body.

---

## 2. Docs API (patient-free)

Standalone FastAPI app in `docs_api.py`. Reuses the same PGVector document store (`base_knowledge` collection) and CLaRa-compress → Qwen-generate pipeline as the Patient Chat API, but never touches `patients`, `clients`, or `chat_messages` — no mock database dependency, no personalization, just document-grounded Q&A.

**Status:** live, publicly hosted as of 2026-07-23. Runs as `docs_api.service` (systemd, port 8100) on the same Han Server box, exposed via a Cloudflare tunnel ingress rule at `docs-api.computationalrd.com`.

### Endpoint

```
POST https://docs-api.computationalrd.com/ask
```

### Headers

```
Content-Type: application/json
X-API-Key: <DOCS_API_KEY>
```

Required as of 2026-07-23 — requests without a valid `X-API-Key` get `401 Invalid or missing X-API-Key`.

### Request body

```json
{
  "question": "What foods should someone with high blood pressure avoid?"
}
```

- `question` (string, required) — the only field. No `patient_id`, no `profile`, no `session_id` — this API has no concept of a patient or a conversation.

### Response

```json
{
  "answer": "Someone with high blood pressure should limit or avoid foods high in sodium..."
}
```

### Integration — curl

```bash
curl -X POST https://docs-api.computationalrd.com/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <DOCS_API_KEY>" \
  -d '{"question":"What foods should someone with high blood pressure avoid?"}'
```

### Integration — Python

```python
import requests

resp = requests.post(
    "https://docs-api.computationalrd.com/ask",
    headers={"X-API-Key": "<DOCS_API_KEY>"},
    json={"question": "What foods should someone with high blood pressure avoid?"},
    timeout=100,
)
print(resp.json()["answer"])
```

---

## 3. Weekly EKA Content API

Read/approve interface over `content_materials` (`content_api_router.py`, mounted at `/content` on the same host/port as the Patient Chat API — `nutribot.computationalrd.com`). Same `<NUTRIBOT_API_KEY>` as section 1.

**There is no generation endpoint.** Content is produced by `scripts/generate_weekly_eka.py`, run by a Monday-06:00 cron (`scripts/weekly_eka_scheduler.py`), not triggerable via API. To generate on demand, run it directly on the server:
```bash
/home/han/Desktop/projects/bare_NutriChatbot/.venv/bin/python scripts/generate_weekly_eka.py --week 35
```
Everything it generates lands with `is_active=False` — nothing reaches a patient until approved (below).

### Headers (all endpoints)

```
X-API-Key: <NUTRIBOT_API_KEY>
```

### GET /content/weekly-feed

This week's approved Exercise + Knowledge + Activity items for a set of condition groups.

```bash
curl "https://nutribot.computationalrd.com/content/weekly-feed?conditions=T2DM,Cardiac" \
  -H "X-API-Key: <NUTRIBOT_API_KEY>"
```
Query params: `conditions` (required, comma-separated: `T2DM|HTN|CKD|Cardiac|PCOS|Dyslipidaemia|General`), `week_number` (optional, default current ISO week), `is_active` (optional, default `true`).

### GET /content/patient-feed/{patient_id}

Same as above, but condition groups are looked up from the patient's own record instead of passed in. Requires the patient to belong to your API client account (`403` otherwise).

```bash
curl "https://nutribot.computationalrd.com/content/patient-feed/2" \
  -H "X-API-Key: <NUTRIBOT_API_KEY>"
```

### GET /content/materials

List with filters — `content_type` (`E|K|A`), `week_number`, `condition_group`, `is_active`, `include_expired` (default excludes items older than `database.EKA_EXPIRY_DAYS`, 30 days as of 2026-09-08 — items are archived to `materials/eka_week{N}_reviewed.xlsx` before deletion, see `database.cleanup_expired_eka_materials()`), `limit`/`offset`.

### GET /content/materials/{id}

Single material, full content.

### GET /content/summary

Per-type (E/K/A) counts of active vs. pending materials for a given week — for dashboards.

### POST /content/materials/{id}/approve  /  .../unapprove

Admin actions — flip `is_active`. Require an extra header:
```
X-Admin-Password: <ADMIN_PASSWORD>
```
```bash
curl -X POST "https://nutribot.computationalrd.com/content/materials/123/approve" \
  -H "X-API-Key: <NUTRIBOT_API_KEY>" \
  -H "X-Admin-Password: <ADMIN_PASSWORD>"
```

### Reviewer UI (separate host, not the client-facing API above)

For the internal review workflow (not for client integration), `https://docs-api.computationalrd.com/eka-review` is a browser page backed by its own `X-API-Key`-gated endpoints (`GET /eka-review/data`, `POST /eka-review/materials/{id}/approve`, `.../unapprove`, `.../content`) on `docs_api.py` — reads/writes the same `content_materials` table, meant for the dietitian team to review generated drafts, not for downstream apps.
