# Nutribot API — integration details

Two separate APIs, depending on what the calling application needs:

1. **Patient Chat API** — personalized nutrition advice tied to a patient profile (conditions, medications, restrictions). Public, hosted.
2. **Docs API** — plain document-grounded nutrition Q&A, no patient data, no mock database involved. Standalone service (`docs_api.py`), not yet publicly hosted.

Both are plain REST POST + JSON — no SDK needed.

---

## 1. Patient Chat API

### Endpoint

```
POST https://nutribot.computationalrd.com/chat/get_response_sync
```

### Headers

```
Content-Type: application/json
X-API-Key: nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3
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
  -H "X-API-Key: nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3" \
  -d '{"question":"What should I eat for breakfast?","patient_id":2,"session_id":"your-app-session-1"}'
```

### Integration — Python

```python
import requests

resp = requests.post(
    "https://nutribot.computationalrd.com/chat/get_response_sync",
    headers={"X-API-Key": "nbk_live_96cfcc81cf0da0791279b2c4c391b09bfeb4b574a434c83c79c7f286d5ec8dd3"},
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

**Status:** live, publicly hosted as of 2026-07-23. Runs as `docs_api.service` (systemd, port 8100) on the same RTX 3050 box, exposed via a Cloudflare tunnel ingress rule at `docs-api.computationalrd.com`.

### Endpoint

```
POST https://docs-api.computationalrd.com/ask
```

### Headers

```
Content-Type: application/json
X-API-Key: nbk_docs_5d1744c666134f94c38ebc015be12b7cf7b79e00a38b6493
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
  -H "X-API-Key: nbk_docs_5d1744c666134f94c38ebc015be12b7cf7b79e00a38b6493" \
  -d '{"question":"What foods should someone with high blood pressure avoid?"}'
```

### Integration — Python

```python
import requests

resp = requests.post(
    "https://docs-api.computationalrd.com/ask",
    headers={"X-API-Key": "nbk_docs_5d1744c666134f94c38ebc015be12b7cf7b79e00a38b6493"},
    json={"question": "What foods should someone with high blood pressure avoid?"},
    timeout=100,
)
print(resp.json()["answer"])
```
