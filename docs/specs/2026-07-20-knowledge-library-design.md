# Knowledge Library & Q&A Catalogue (Browse-First Web Experience) Design

**Date:** 2026-07-20
**Status:** Approved
**Goal:** Reduce over-reliance on the chat feature for a knowledge base that is finite and well-classified. Two complementary, LLM-free-to-browse systems replace chat as the default web experience: a **document library** generated from existing classification metadata, and a **Q&A catalogue** that grows over time from real user questions judged worth reusing. Chat remains available — as the fallback when neither system has an answer, and as the mechanism that feeds the catalogue. Additionally, the chat pipeline's existing relevance gate is tightened so off-topic questions are rejected before the costly LLM synthesis step.

---

## Overview

Today `/` is the chat interface and every interaction — including ones a previous user has already asked, or ones answerable by reading a document directly — goes through the full RAG pipeline (language detection → translation → embedding → vector search → LLM synthesis → translation back). This design replaces that default with two browsable systems that cost nothing to serve:

1. **Document library** — pages generated directly from the `DocumentClassification` metadata (`topics`, `crops`, `regions`, `summary`, `key_practices`) that already exists for every processed document. Read-only, no LLM involved.
2. **Q&A catalogue** — a living FAQ built from real chat turns. When a chat answer is judged (by an independent quality signal, not just the answering LLM's self-report) to be worth reusing, it's queued for cataloguing, translated once it's confirmed good, and served to every future asker of a similar question — in any of the five supported languages — without a further LLM call.

A single **ask gate** ties them together: every new question a user types is checked against the catalogue *before* it ever reaches chat. A hit means an instant, free, previously-vetted answer. A miss falls through to live chat, which still benefits from the tightened relevance gate and, off its own critical path, feeds tomorrow's catalogue.

This only covers the web frontend. WhatsApp and the admin dashboard's existing pages are unaffected (the admin dashboard *gains* a catalogue review page).

---

## System 1: Document Library

### Backend (`src/api/routes/library.py`)

A new router, mounted without an auth dependency (unlike `admin.py`'s `require_admin`-gated routes), since this is public content. Every query filters to documents safe to show publicly:

```python
db.query(Document).join(DocumentClassification).filter(
    Document.status == DocumentStatus.PROCESSED,
    DocumentClassification.relevance_score >= settings.relevance_threshold,
)
```

This mirrors the bar `settings.relevance_threshold` already sets for manual ingestion (`src/flows/manual_ingestion.py`), so the library and the chatbot draw from the same trusted set of documents, just via different retrieval paths.

- **`GET /library/facets`** — distinct `topics`/`crops`/`regions` values with counts (`unnest()` + `GROUP BY` over the ARRAY columns), scoped by the filter above. Cached with a 5-minute in-process TTL — facet values only change when the crawl schedule finishes processing new documents.
- **`GET /library/documents`** — query params `topic`, `crop`, `region`, `q` (ILIKE over `title`/`summary`, no embeddings), `offset`, `limit`. Returns paginated cards (title, summary, tags, `document_category`, source `url`).
- **`GET /library/documents/{id}`** — adds `key_practices`, `actionable`, `has_data`, and a `full_text` field assembled from `ContentChunk` rows (`ORDER BY chunk_index`, joined). 404 uniformly for nonexistent, unprocessed, or below-threshold ids — no distinction, so nothing about unpublished content leaks.

### Frontend

| Route | Component | Purpose |
|---|---|---|
| `/library` | `LibraryHome` | Facet pill-grids (Topics/Crops/Regions) with counts; keyword search box |
| `/library/topic/:name`, `/library/crop/:name`, `/library/region/:name` | `FacetResultsPage` | Paginated document cards for the selected facet value |
| `/library/documents/:id` | `DocumentDetailPage` | Summary, `key_practices` bullets, tag pills, expandable full-text, link to source |

`summary`/`key_practices` render through the existing `lib/markdownComponents.jsx` pattern.

---

## System 2: Q&A Catalogue

### Data model (`src/storage/models.py`)

```python
class CatalogueStatus(str, enum.Enum):
    pending = "pending"      # awaiting admin review (manual gating mode only)
    approved = "approved"    # live — translated, indexed, servable by the ask gate
    rejected = "rejected"    # reviewed and declined; kept for audit
    retracted = "retracted"  # was approved, later pulled after being found wrong


class CatalogueEntry(Base):
    __tablename__ = "catalogue_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    status = Column(SQLEnum(CatalogueStatus), nullable=False, default=CatalogueStatus.pending, index=True)

    question_en = Column(Text, nullable=False)     # LLM-optimised, canonical English question
    answer_en = Column(Text, nullable=False)
    question_translations = Column(JSONB, default=dict)   # {lang_code: text} — populated at approval
    answer_translations = Column(JSONB, default=dict)

    embedding = Column(ARRAY(Float))               # stored for every entry, used for dedup scans
    embedding_vector_id = Column(String(100))      # id in the vector DB's catalogue collection, once indexed

    source_message_id = Column(UUID(as_uuid=True), ForeignKey("chat_messages.id"))
    sources = Column(JSONB)                        # citations, copied from the originating chat message

    llm_catalogue_score = Column(Float)            # LLM's own 0-10 "worth cataloguing" score
    faithfulness_score = Column(Float)             # bert_score.f1 at candidacy time

    hit_count = Column(Integer, default=0)         # times served as an ask-gate match

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at = Column(DateTime)
    reject_reason = Column(Text)
```

### Settings (`src/config/settings.py`)

```python
catalogue_gating_mode: Literal["auto", "manual"] = Field(default="manual")
catalogue_min_score: float = Field(default=7.0)          # LLM worth-cataloguing score (0-10) — manual mode only
catalogue_min_faithfulness: float = Field(default=0.5)   # BERTScore F1 floor — required in BOTH modes
catalogue_match_threshold: float = Field(default=0.85)   # cosine similarity to surface a match in the ask gate
catalogue_dedup_threshold: float = Field(default=0.90)   # cosine similarity to treat a candidate as a duplicate
catalogue_collection_name: str = Field(default="catalogue_questions")  # vector DB collection for approved entries
```

`catalogue_gating_mode` is the toggle requested: in **manual** mode (default), an entry must clear both `catalogue_min_score` (LLM self-report) and `catalogue_min_faithfulness` (independent BERTScore signal) to enter the pending queue, and still requires admin approval before going live. In **auto** mode, `catalogue_min_faithfulness` alone is sufficient — BERTScore's groundedness check is trusted on its own, the LLM's self-report is not required as a gate (though still computed and stored for visibility/audit), and a candidate goes straight to `approved` (translated + indexed immediately) with no human step. This makes the LLM-self-grading risk an operator choice rather than a hardcoded one: manual mode exists specifically because a same-model self-report shouldn't be trusted alone; auto mode is available once the faithfulness signal alone is trusted enough for a given deployment.

### Background cataloguing pipeline (`src/api/services/catalogue_service.py`, new)

Runs off the critical path, via `background_tasks.add_task`, the same pattern `score_message_background` already uses — after BERTScore for the turn is computed:

```python
def evaluate_for_catalogue_background(message_id, question_en, answer_en, chunks, sources, bert_f1):
    if bert_f1 < settings.catalogue_min_faithfulness:
        return  # fails the floor required in both modes

    result = llm_client.evaluate_for_catalogue(question_en, answer_en)
    # result: {"worth_cataloguing_score": 0-10, "optimised_question": "..."}

    if settings.catalogue_gating_mode == "manual" and result["worth_cataloguing_score"] < settings.catalogue_min_score:
        return

    embedding = embedding_client.embed(result["optimised_question"])

    if _is_duplicate(embedding, settings.catalogue_dedup_threshold):
        _bump_hit_count(matched_entry)
        return

    status = CatalogueStatus.approved if settings.catalogue_gating_mode == "auto" else CatalogueStatus.pending
    entry = _create_entry(question_en=result["optimised_question"], answer_en=answer_en,
                           embedding=embedding, llm_catalogue_score=result["worth_cataloguing_score"],
                           faithfulness_score=bert_f1, sources=sources, status=status)

    if status == CatalogueStatus.approved:
        _publish(entry)  # translate + index — see below
```

`_is_duplicate` scans `embedding` across existing `pending` + `approved` rows via cosine similarity in Python (catalogue size stays modest for a finite knowledge base — a linear scan is fine); `approved` rows are additionally checked via the fast vector-DB collection used by the live gate.

`llm_client.evaluate_for_catalogue` is a new, small, JSON-mode LLM call — separate from `answer_question`/`stream_answer` because those stream raw tokens and can't return structured output mid-stream. Cost is negligible relative to the synthesis call it follows (short prompt, short output).

### Publishing (`_publish`, shared by admin-approve and auto-mode)

Runs exactly once per entry, whichever mode triggers it:
1. Translate `question_en`/`answer_en` into the five supported languages via the existing `TranslationClient`, store in `question_translations`/`answer_translations`.
2. Upsert the stored `embedding` into the vector DB's catalogue collection (reusing the existing `VectorDBClient` abstraction with a second collection, e.g. `settings.catalogue_collection_name`, mirroring how the documents collection is configured) — this is what the live ask gate searches.
3. Set `status = approved`, `approved_at = now()`.

Translation only happens here — never at candidacy time — so rejected entries never pay translation cost.

### Ask gate (`POST /catalogue/match`, public)

Called before a new question is allowed to start a chat turn:
1. Detect language, translate to English, embed (all reused from the chat pipeline).
2. Search the catalogue vector collection (approved entries only), top-k with `catalogue_match_threshold`.
3. Match → return the entry's translated question/answer/citations. Frontend offers: *this answers it* (increments `hit_count`), *ask a follow-up* (starts a live chat session pre-seeded with `[question_en, answer_en]` as history, proceeds through the normal RAG pipeline for the follow-up), or *not what I meant* (falls through to 4).
4. No match, or declined → proceeds to a normal new chat turn, which still passes through the tightened relevance gate (below) and, off its own critical path, feeds the cataloguing pipeline above.

### Standalone browsing (`GET /catalogue`, `GET /catalogue/{id}`, public)

Independent of the gate — a paginated, keyword-searchable (`q` over `question_en`/`answer_en`) list of all `approved` entries, and a detail page per entry, in the same spirit as the document library. Built to the same level of completeness, not a side effect of the gate.

### Admin review (`src/api/routes/admin.py`, `require_admin`-gated)

- `GET /admin/catalogue/pending` — lists pending entries with `llm_catalogue_score` and `faithfulness_score` shown side by side, plus citations, so a reviewer isn't relying on the LLM's self-report alone.
- `POST /admin/catalogue/{id}/approve` — runs `_publish`.
- `POST /admin/catalogue/{id}/reject` — sets `status=rejected`, optional `reject_reason`; kept for audit, never surfaced.
- `POST /admin/catalogue/{id}/retract` — for a previously-`approved` entry found wrong later: removes it from the vector collection and sets `status=retracted`. Available regardless of gating mode, since even auto-published entries need a way to be pulled.

New admin page `frontend/src/admin/pages/Catalogue.jsx` with Pending/Approved tabs, approve/reject/retract actions.

### Frontend nav

Top-level nav becomes `Ask | Documents | Catalogue`:
- **Ask** (`/`) — the new default landing page: single question input implementing the ask-gate flow above, falling through to `/chat` when there's no match.
- **Documents** (`/library`) — System 1.
- **Catalogue** (`/catalogue`) — System 2's standalone browse.
- `/chat` still exists as a route (used internally by the ask gate's fallback and follow-up flow) but isn't a top-level nav link — chat is reached through asking, not chosen directly.

---

## Chat pipeline: tightened relevance gate

`src/api/services/chat_service.py` already short-circuits before LLM synthesis when zero chunks clear `settings.chat_score_threshold` (`process_chat` step 5b, and the equivalent block in `process_chat_stream`). The gap: it only checks whether *any* chunk passed a threshold meant for chunk *inclusion*, not whether the *best* match is actually a confident hit.

Add `chat_min_top_score`, checked against `search_results[0]["score"]` right after the vector search call, in both `process_chat` and `process_chat_stream`:

```python
if not chunks or (search_results and search_results[0]["score"] < settings.chat_min_top_score):
    # existing _NO_RESULTS_ANSWER shortcut path, reused as-is
    ...
```

Separate from `chat_score_threshold` (which still controls which chunks are *included* as context) — `chat_min_top_score` only controls whether synthesis happens at all. Starting value is conservative and tuned post-launch using existing BERTScore/chat-quality data; `_NO_RESULTS_ANSWER` copy is updated to point at `/library` and `/catalogue`.

---

## Error Handling & Edge Cases

- A facet or catalogue search with zero results renders an empty state, not an error.
- Documents below `relevance_threshold`, unclassified, or not `PROCESSED` are excluded at the SQL level from every library endpoint.
- `GET /library/documents/{id}` and `GET /catalogue/{id}` return 404 uniformly for nonexistent/unpublished ids — no information leak about what's excluded and why.
- A catalogue entry can be `approved` and later `retracted` — the ask gate and `/catalogue` browse must only ever query `status == approved`, never inferring "live" from the absence of `rejected`/`retracted`.
- If translation fails during `_publish`, the entry is not marked `approved` — retry, don't half-publish with missing language variants.
- Cold start: the catalogue is empty at launch. The ask gate's "no match" path is simply the normal chat flow, so there's no broken state — it just starts empty and grows.

---

## Testing

- New `tests/test_library_routes.py` — facet counts, filter combinations, pagination, exclusion rules.
- New `tests/test_catalogue_service.py` — candidacy logic in both gating modes (bert-floor-only in `auto`, both signals required in `manual`), dedup detection against existing pending/approved entries, `_publish` translating and indexing exactly once, retract removing an entry from the live gate without deleting the row.
- New `tests/test_catalogue_routes.py` — ask-gate matching/threshold behavior, standalone browse/search, admin approve/reject/retract endpoints and their auth gating.
- `tests/test_chat_service.py` gets new cases for the tightened gate: top hit above `chat_min_top_score` proceeds; below it short-circuits even when weaker chunks passed `chat_score_threshold`.
- Frontend: no test framework currently in place (per `AGENTS.md`); verify manually in-browser — ask-gate match/no-match/follow-up paths, both document and catalogue browsing, admin review actions, and `/chat` still working end-to-end.

---

## Files Changed

| File | Change |
|---|---|
| `src/api/routes/library.py` | New — `/library/facets`, `/library/documents`, `/library/documents/{id}` |
| `src/api/routes/catalogue.py` | New — `/catalogue/match`, `/catalogue`, `/catalogue/{id}` |
| `src/api/routes/admin.py` | Add `/admin/catalogue/pending`, `approve`, `reject`, `retract` |
| `src/api/main.py` | Mount `library` and `catalogue` routers |
| `src/api/services/catalogue_service.py` | New — candidacy evaluation, dedup, `_publish` |
| `src/llm/client.py` | Add `evaluate_for_catalogue` (JSON-mode scoring + optimised question) |
| `src/storage/models.py` | Add `CatalogueEntry`, `CatalogueStatus` |
| `src/storage/vector_db.py` | Support a second ("catalogue") collection alongside the documents collection |
| `src/config/settings.py` | Add `chat_min_top_score`, `catalogue_gating_mode`, `catalogue_min_score`, `catalogue_min_faithfulness`, `catalogue_match_threshold`, `catalogue_dedup_threshold`, `catalogue_collection_name` |
| `src/api/services/chat_service.py` | Top-score check in both process functions; schedule `evaluate_for_catalogue_background`; update `_NO_RESULTS_ANSWER` copy |
| `frontend/src/App.jsx` | `/` → ask-gate home; `/chat` unchanged internally; add `/library/*` and `/catalogue/*` routes |
| `frontend/src/components/Header.jsx` | `Ask \| Documents \| Catalogue` nav |
| `frontend/src/AskGate.jsx` | New — question input, match display, follow-up/fallback actions |
| `frontend/src/library/LibraryHome.jsx`, `FacetResultsPage.jsx`, `DocumentDetailPage.jsx` | New — System 1 pages |
| `frontend/src/catalogue/CatalogueBrowse.jsx`, `CatalogueDetail.jsx` | New — System 2 standalone browse pages |
| `frontend/src/admin/pages/Catalogue.jsx` | New — Pending/Approved review tabs |
| `tests/test_library_routes.py`, `test_catalogue_service.py`, `test_catalogue_routes.py` | New |
| `tests/test_chat_service.py` | New cases for the tightened gate |

---

## Out of Scope

- WhatsApp: remains pure chat; no interactive menu/list redesign in this pass.
- Editorial/curated content for the document library: fully auto-generated from existing classification data, no authoring UI.
- Full document file serving (PDF/HTML from MinIO): the library detail page shows assembled extracted text, linking out to the source `url`.
- Redis or other external cache: the in-process TTL cache on `/library/facets` is enough at current data volume.
- Auto-promotion of pending entries based on repeated independent candidacy hits (the `hit_count`/demand signal is recorded but doesn't yet drive any automatic behavior beyond dedup).
- A UI for switching `catalogue_gating_mode` at runtime — it's a deployment-level setting (`.env`), not an in-app admin toggle, for this pass.
