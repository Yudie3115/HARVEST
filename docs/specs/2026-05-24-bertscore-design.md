# BertScore Integration — Design Spec

**Date:** 2026-05-24
**Status:** Approved

---

## Overview

Add automated answer-faithfulness scoring to the RAG chat pipeline using BertScore. Every chat turn produces a precision/recall/F1 score measuring how well the generated answer is grounded in the retrieved source chunks. Scores are stored on the `ChatMessage` row and surfaced in a new "Chat Quality" admin page.

---

## Architecture

Three layers, each with a single responsibility:

```
chat_service.process_chat()
  └─ after commit → registers FastAPI BackgroundTask
        └─ BertScorer.score(english_answer, chunk_texts)
              └─ writes {precision, recall, f1, model, scored_at}
                 to ChatMessage.bert_score (JSONB)

GET /admin/chat-quality        ←→   ChatQuality.jsx (new admin page)
GET /admin/chat-quality/stats
```

The user-facing chat path is **unchanged** — scoring runs off the critical path via `BackgroundTasks`. The React admin page reads two new protected endpoints.

---

## Data Model

One new nullable JSONB column on `chat_messages`:

```sql
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS bert_score JSONB;
```

Stored value shape:

```json
{
  "precision": 0.82,
  "recall":    0.74,
  "f1":        0.78,
  "model":     "distilbert-base-uncased",
  "scored_at": "2026-05-24T10:31:00Z"
}
```

Only assistant messages ever receive a score. Rows from before this feature, and any turns where scoring fails, remain `NULL`. The admin page exposes unscored count separately.

A migration script (`scripts/migrate_add_bert_score.py`) adds the column to existing deployments via `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.

---

## Scoring Module — `src/llm/bert_scoring.py`

A module-level lazy singleton (`_scorer`) that loads the HuggingFace model once on first use and reuses it across requests.

```python
class BertScorer:
    def score(self, candidate: str, references: list[str]) -> dict:
        ...
```

- Joins all reference chunk texts with `\n\n`, truncates to 3 000 chars to stay within token limits
- Calls `bert_score.score(cands=[candidate], refs=[joined_reference], ...)`
- Returns `{precision, recall, f1, model, scored_at}`
- Default model: `distilbert-base-uncased` (fast on CPU, ~66M params)
- Configurable via `BERTSCORE_MODEL` env var
- `BERTSCORE_ENABLED` env var (default `true`) allows disabling without code changes

---

## Background Task Wiring

`process_chat()` gains an optional `background_tasks: BackgroundTasks | None = None` parameter. After the DB commit at step 9:

```python
if background_tasks and settings.bertscore_enabled:
    background_tasks.add_task(
        _score_message_bg,
        message_id=str(assistant_msg.id),
        candidate=english_answer,
        references=[c["text"] for c in chunks],
    )
```

`_score_message_bg` opens its own `PostgresClient` session, calls `BertScorer().score()`, and writes the result back to `ChatMessage.bert_score`.

`src/api/routes/chat.py` injects `BackgroundTasks` (native FastAPI dependency) and passes it into `process_chat()`.

The WhatsApp route calls the same `process_chat()` and picks this up automatically once its handler also passes `BackgroundTasks`.

---

## Settings

Two new env vars added to `Settings` and `.env.example`:

| Var | Default | Notes |
|-----|---------|-------|
| `BERTSCORE_MODEL` | `distilbert-base-uncased` | Any HuggingFace model ID |
| `BERTSCORE_ENABLED` | `true` | Set `false` to disable scoring entirely |

---

## Admin API Endpoints

Both added to `src/api/routes/admin.py`, protected by `require_admin`.

### `GET /admin/chat-quality`

Paginated list of scored assistant messages, newest first. Each row includes the preceding user message text (via a PostgreSQL LATERAL JOIN).

Query params: `offset` (default 0), `limit` (default 20), `min_f1`, `max_f1`.

Response fields per item: `message_id`, `session_id`, `question`, `answer`, `bert_score`, `created_at`.

### `GET /admin/chat-quality/stats`

Aggregate stats over all assistant messages:

```json
{
  "total_scored":   142,
  "total_unscored": 3,
  "mean_f1":        0.71,
  "distribution": [
    { "range": "0.0–0.4", "count": 8 },
    { "range": "0.4–0.6", "count": 21 },
    { "range": "0.6–0.8", "count": 67 },
    { "range": "0.8–1.0", "count": 46 }
  ]
}
```

---

## React Admin Page — `ChatQuality.jsx`

**Route:** `/admin/chat-quality`

**Sidebar entry:** "Chat Quality" between Knowledge Q&A and Configuration, using a `BarChart2` (Lucide) icon.

### Layout

1. **Stat cards** (top row of 3): Mean F1 score (green accent), Total Scored, Unscored
2. **Bar chart** (recharts `BarChart`): four F1 distribution buckets, styled to match existing charts
3. **Messages table**: columns — Question (80-char truncation), Answer (80-char truncation), F1 badge, Precision, Recall, Timestamp. Rows expand on click to show full question + answer text.

### F1 Badge colours

| F1 range | Colour |
|----------|--------|
| ≥ 0.7    | Green `#22c55e` |
| 0.5–0.7  | Amber `#f59e0b` |
| < 0.5    | Red `#f43f5e`   |

---

## Dependencies

Add to `pyproject.toml`:

```toml
bert-score = "^0.3.13"
```

`bert-score` requires `torch` and `transformers`, which are already present transitively via `sentence-transformers ^2.2.0`.

---

## Out of Scope

- On-demand rescoring of historical messages
- WhatsApp-specific quality views
- Alerting when F1 drops below a threshold
- Non-English BertScore (all scoring is done on the English answer before translation)
