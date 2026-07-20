# Knowledge Library (Browse-First Web Experience) Design

**Date:** 2026-07-20
**Status:** Approved
**Goal:** Reduce over-reliance on the chat feature for a knowledge base that is finite and well-classified, by giving web users (primarily extension workers and researchers) a browsable Topic/Crop/Region library backed entirely by existing Postgres data — no LLM calls, no translation, no vector search — while keeping chat available as a secondary tab. Additionally, tighten the chat pipeline's existing relevance gate so off-topic questions are rejected before the costly LLM synthesis step.

---

## Overview

Today `/` is the chat interface and there is no way to browse the knowledge base directly — every interaction, including ones a user could answer themselves by reading a document, goes through the full RAG pipeline (language detection → translation → embedding → vector search → LLM synthesis → translation back). The pipeline already produces rich per-document metadata (`topics`, `crops`, `regions`, `document_category`, `target_audience`, `summary`, `key_practices`) via `DocumentClassification`, but nothing in the frontend surfaces it.

This design adds a **Library**: a set of public, read-only, LLM-free pages that let users browse by Topic/Crop/Region or search by keyword, and read a document's summary, key practices, and full extracted text directly. Chat moves from the default landing experience to a secondary tab, and its existing no-results shortcut is tightened so genuinely off-topic questions are rejected earlier and more reliably.

This only covers the web frontend. WhatsApp and the admin dashboard are unaffected.

---

## Backend: Library API (`src/api/routes/library.py`)

A new router, mounted without an auth dependency (unlike `admin.py`'s `require_admin`-gated routes), since this is public content.

Every query in this router filters to documents that are safe to show publicly:

```python
db.query(Document).join(DocumentClassification).filter(
    Document.status == DocumentStatus.PROCESSED,
    DocumentClassification.relevance_score >= settings.relevance_threshold,
)
```

This mirrors the bar `settings.relevance_threshold` already sets for manual ingestion (`src/flows/manual_ingestion.py`), so the library and the chatbot draw from the same trusted set of documents, just via different retrieval paths.

### `GET /library/facets`

Returns distinct `topics`, `crops`, and `regions` values with document counts, e.g.:

```json
{
  "topics": [{"name": "aflatoxin control", "count": 8}, ...],
  "crops": [{"name": "maize", "count": 11}, ...],
  "regions": [{"name": "Uganda", "count": 14}, ...]
}
```

Computed with `unnest()` + `GROUP BY` over the ARRAY columns, scoped by the same PROCESSED/relevance filter above.

### `GET /library/documents`

Query params: `topic`, `crop`, `region`, `q`, `offset`, `limit`. `topic`/`crop`/`region` filter via `ANY(...)` against the ARRAY columns. `q` does an `ILIKE` match against `title` and `summary` — no embeddings involved. Returns paginated cards:

```json
{
  "items": [
    {"id": "...", "title": "...", "summary": "...", "topics": [...], "crops": [...],
     "regions": [...], "document_category": "...", "url": "..."}
  ],
  "total": 42, "offset": 0, "limit": 20
}
```

### `GET /library/documents/{id}`

Returns everything above plus `key_practices`, `actionable`, `has_data`, and a `full_text` field assembled from `ContentChunk` rows for that document (`ORDER BY chunk_index`, joined with `"\n\n"`). If the id doesn't exist, isn't `PROCESSED`, or falls below `relevance_threshold`, return `404` — same response whether it's missing or simply unpublished, so no information about unpublished/low-relevance content leaks.

### Caching

`GET /library/facets` uses a simple in-process TTL cache (5 minutes) — facet values only change when the daily/hourly crawl schedule finishes processing new documents, so a short TTL is enough and avoids adding Redis. `documents` and `documents/{id}` are not cached; they're already cheap indexed Postgres reads.

---

## Frontend: Library pages

New routes added to `frontend/src/App.jsx`, alongside the existing chat and admin routes:

| Route | Component | Purpose |
|---|---|---|
| `/` (was ChatApp) | `LibraryHome` | Facet pill-grids (Topics/Crops/Regions) from `GET /library/facets`, each pill showing a count; keyword search box at the top |
| `/library/topic/:name`, `/library/crop/:name`, `/library/region/:name` | `FacetResultsPage` | Paginated document cards for the selected facet value, using existing `card.jsx`/`badge.jsx` UI primitives |
| `/library/documents/:id` | `DocumentDetailPage` | Summary, `key_practices` bullet list, tag pills for its topics/crops/regions, expandable full-text section, link to original source `url` |
| `/chat` (was `/`) | `ChatApp` | Unchanged internally — only the route path moves |

`Header.jsx` gets a `Library | Chat` toggle so switching is always one click away. `ChatApp`'s `_NO_RESULTS_ANSWER` copy is updated to link to `/library` so a rejected chat question still lands the user somewhere useful.

`summary`/`key_practices` render through the existing `lib/markdownComponents.jsx` pattern already used elsewhere in the frontend.

---

## Chat pipeline: tightened relevance gate

`src/api/services/chat_service.py` already short-circuits before LLM synthesis when zero chunks clear `settings.chat_score_threshold` (`process_chat` step 5b, and the equivalent block in `process_chat_stream`). The gap: it only checks whether *any* chunk passed a threshold meant for chunk *inclusion*, not whether the *best* match is actually a confident hit — a query sharing vocabulary with post-harvest content (without sharing intent) can retrieve 1-2 weakly-similar chunks, clear the loose threshold, and trigger a full synthesis call that produces a mushy or partially hallucinated answer instead of a clean rejection.

### Change

Add a new setting, `chat_min_top_score`, checked against `search_results[0]["score"]` immediately after the vector search call, in both `process_chat` and `process_chat_stream`:

```python
if not chunks or (search_results and search_results[0]["score"] < settings.chat_min_top_score):
    # existing _NO_RESULTS_ANSWER shortcut path, reused as-is
    ...
```

This is a stricter, separate threshold from `chat_score_threshold` (which continues to control which chunks are *included* as context once the gate is passed) — `chat_min_top_score` only controls whether synthesis happens at all.

### Calibration

The starting value should be conservative and tuned using the BERTScore/chat-quality data already collected via the `ChatQuality` admin page and `chat_messages.bert_score` — this is a data/tuning exercise, not a design decision, and can be adjusted post-launch without further code changes.

---

## Error Handling & Edge Cases

- A facet value with zero remaining documents (e.g. an over-narrow filter combination) renders an empty state, not an error.
- Documents that are discovered but not yet classified, not yet `PROCESSED`, or below `relevance_threshold` are excluded at the SQL level from every Library endpoint — never partially shown.
- `GET /library/documents/{id}` returns 404 uniformly for nonexistent, unprocessed, and below-threshold ids.
- The tightened chat gate reuses the existing `_NO_RESULTS_ANSWER` response shape — no new response type for the frontend to handle.

---

## Testing

- New `tests/test_library_routes.py`, mirroring existing admin-route test patterns (`tests/test_*.py`): facet counts, filter combinations (`topic` + `crop` together), pagination, and the exclusion rules (unclassified/below-threshold/non-`PROCESSED` documents never appear in any endpoint).
- `tests/test_chat_service.py` gets new cases for the tightened gate: a top hit above `chat_min_top_score` proceeds to synthesis as before; a top hit below it short-circuits to `_NO_RESULTS_ANSWER` even when other weaker chunks passed `chat_score_threshold`.
- Frontend: no test framework currently in place (per `AGENTS.md`); verify manually in-browser per existing convention — Library navigation, facet filtering, search, document detail rendering, and the `/chat` route still working end-to-end.

---

## Files Changed

| File | Change |
|---|---|
| `src/api/routes/library.py` | New — `/library/facets`, `/library/documents`, `/library/documents/{id}` |
| `src/api/main.py` | Mount the new `library` router |
| `src/config/settings.py` | Add `chat_min_top_score` setting |
| `src/api/services/chat_service.py` | Add top-score check in `process_chat` and `process_chat_stream`; update `_NO_RESULTS_ANSWER` copy to link to `/library` |
| `frontend/src/App.jsx` | `/` → `LibraryHome`; `/chat` → `ChatApp`; add `/library/*` routes |
| `frontend/src/components/Header.jsx` | Add `Library \| Chat` nav toggle |
| `frontend/src/library/LibraryHome.jsx` | New — facet browser + search |
| `frontend/src/library/FacetResultsPage.jsx` | New — paginated document cards for a facet value |
| `frontend/src/library/DocumentDetailPage.jsx` | New — document detail view |
| `tests/test_library_routes.py` | New |
| `tests/test_chat_service.py` | New cases for the tightened gate |

---

## Out of Scope

- WhatsApp: remains pure chat; no interactive menu/list redesign in this pass.
- Editorial/curated content: the library is fully auto-generated from existing classification data; no authoring UI is added.
- Pre-computed FAQ caching for the chat tab (raised as an alternative during brainstorming): deferred until real chat query patterns from the tightened gate are observed.
- Full document file serving (PDF/HTML from MinIO): the detail page shows assembled extracted text, not the original file — linking out to the source `url` is sufficient for this pass.
- Redis or other external cache: the 5-minute in-process TTL cache on `/library/facets` is enough at current data volume.
