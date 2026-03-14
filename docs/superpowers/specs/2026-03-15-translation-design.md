# Translation Feature Design

**Date:** 2026-03-15
**Status:** Approved
**Scope:** Bidirectional translation for the Q&A and Search tabs, supporting Ugandan local languages via Sunbird AI's API.

---

## Problem

The knowledge base is entirely in English. Farmers and extension workers in Uganda who are more comfortable in Luganda, Acholi, Runyankole, Ateso, or Lugbara cannot effectively use the Q&A or Search interfaces. Adding translation support makes the system accessible to its primary audience.

---

## Goals

- Users can type queries in a local Ugandan language and receive answers in that same language.
- Language detection is automatic — no language selector UI required.
- The existing RAG pipeline (embeddings, vector search, LLM synthesis) is unchanged.
- The feature can be disabled via a flag with zero runtime overhead.

## Non-Goals

- Translating scraped source documents into local languages (out of scope).
- Translating chunk previews in search results (high latency, low value).
- Speech input or output (TTS/STT endpoints exist in Sunbird API but are deferred).
- Supporting languages outside Sunbird's six supported codes.

---

## Supported Languages

| Code  | Language    |
|-------|-------------|
| `eng` | English     |
| `lug` | Luganda     |
| `ach` | Acholi      |
| `nyn` | Runyankole  |
| `teo` | Ateso       |
| `lgg` | Lugbara     |

---

## Architecture

Translation is a **thin wrapper** around the existing RAG pipeline. All core components (embeddings, Qdrant, LLM) continue to operate on English text.

### Q&A Flow

```
User query (any language)
        │
        ▼
  Language detection          ← Sunbird /tasks/language_id
        │
   local lang?
   ┌────┴────┐
  YES       NO
   │         │
   ▼         │
Translate    │               ← Sunbird /tasks/nllb_translate (→ English)
to English   │
   │         │
   └────┬────┘
        ▼
  Embed English query
        │
        ▼
  Qdrant vector search
        │
        ▼
  LLM answer synthesis        ← unchanged
        │
   local lang?
   ┌────┴────┐
  YES       NO
   │         │
   ▼         │
Translate    │               ← Sunbird /tasks/nllb_translate (→ local lang)
  answer     │
   │         │
   └────┬────┘
        ▼
  Display answer + "Answered in [language]" badge
```

### Search Flow

```
User query (any language)
        │
        ▼
  Language detection
        │
   local lang? → translate to English (silent)
        │
        ▼
  Embed English query → Qdrant search
        │
        ▼
  Display results in English
  + caption: "Searching in English (translated from [language])"
```

---

## Components

### New: `src/translation/__init__.py`

Exports `TranslationClient`, `TranslationError`, and:

```python
SUPPORTED_LANGUAGES = {
    "lug": "Luganda",
    "ach": "Acholi",
    "nyn": "Runyankole",
    "teo": "Ateso",
    "lgg": "Lugbara",
    "eng": "English",
}
```

### New: `src/translation/client.py`

```python
class TranslationClient:
    def detect_language(self, text: str) -> str | None
        # Returns a language code or None if confidence < settings.translation_min_confidence
        # or if the language is not in SUPPORTED_LANGUAGES.

    def translate(self, text: str, source_lang: str, target_lang: str) -> str
        # Evaluation order:
        #   1. If source_lang == target_lang: return text unchanged (no network call).
        #   2. If len(text) > 10,000: raise TranslationError("Input too long").
        #   3. If len(text) <= 500: send as a single request, no splitting.
        #   4. Otherwise: split on paragraph/sentence boundaries, translate each chunk,
        #      rejoin (see "Text chunking" below).
        # Raises TranslationError on permanent API failure.

    def translate_to_english(self, text: str, source_lang: str) -> str
    def translate_from_english(self, text: str, target_lang: str) -> str
        # Both are thin wrappers around translate().
        # TranslationError is propagated to the caller — not swallowed.
```

- Reads `settings.sunbird_api_key` and `settings.sunbird_api_url`
- If `sunbird_api_key` is empty, `detect_language` returns `None` and `translate` raises `TranslationError` immediately without making any network calls. This prevents noisy log warnings for deployments that have not configured the feature.
- Retries up to 3 times with exponential backoff on transient errors (429, 503, 504)
- Raises `TranslationError` (a typed exception) on permanent failure

**Text chunking:** Split on `\n\n` (paragraph) boundaries first, then sentence boundaries (`". "`) if a paragraph exceeds 500 characters. No tiktoken dependency — character count is sufficient. Join translated paragraph chunks with `"\n\n"` (preserving document structure); join sentence-split sub-chunks with `" "`. Hard limit: refuse inputs over 10,000 characters with `TranslationError("Input too long")`.

**HTTP timeouts:** All Sunbird requests use `httpx.Timeout(connect=5.0, read=15.0)`. Timeout exceptions are treated as transient errors and follow the same retry/degradation path as 503/504.

**Language detection threshold:** `detect_language` returns `None` when the Sunbird response confidence is below `settings.translation_min_confidence` (default `0.80`). Short or ambiguous inputs (single words, proper nouns) commonly fall below this threshold and will correctly fall through to English.

### Modified: `src/config/settings.py`

Four new fields added to the `Settings` class:

```python
# Translation (Sunbird AI)
sunbird_api_key: str = Field(default="")
sunbird_api_url: str = Field(default="https://api.sunbird.ai")
translation_enabled: bool = Field(default=True)
translation_min_confidence: float = Field(default=0.80)
```

### Modified: `dashboard/app.py`

**`_answer_question()`** — updated signature and behaviour:

```python
def _answer_question(
    question: str, top_k: int, score_threshold: float
) -> tuple[str | None, list, str | None]:
    # Returns (answer, results, detected_lang)
    # detected_lang is None if English or detection failed
```

Steps added:
1. If `translation_enabled`: detect language
2. If local language detected: translate question → English
3. Run existing RAG pipeline
4. If local language detected: translate answer → local language
5. Return `(translated_answer, results, detected_lang)`

**Early-return statements inside `_answer_question()`** must all be updated from 2-tuples to 3-tuples:
- `return None, []` → `return None, [], None`
- `return None, results` → `return None, results, None`

**Q&A tab display** — additions:
- Badge above answer: `st.caption("Detected: Luganda — answering in Luganda")`
- Answer rendered as today (inside `st.info`)
- Sources remain in English

**`_answer_question()` call site** — line 368 unpacking changes from `answer, results = _answer_question(...)` to `answer, results, detected_lang = _answer_question(...)`.

**`_semantic_search()`** — no signature change; query translation handled in the Search tab block before calling this function.

**Search tab** — addition:
- Only attempt language detection and query translation if `settings.translation_enabled` is `True`
- Detect language and translate query to English before calling `_semantic_search()`
- Show `st.caption("Searching in English (translated from Luganda)")` when translation occurs

---

## Configuration

### `src/config/settings.py` additions

```python
# Translation (Sunbird AI)
sunbird_api_key: str = Field(default="")
sunbird_api_url: str = Field(default="https://api.sunbird.ai")
translation_enabled: bool = Field(default=True)
translation_min_confidence: float = Field(default=0.80)
```

### `.env.example` additions

```dotenv
# ── Translation (Sunbird AI) ──────────────────────────────────────────────────
# Enables bidirectional translation for Ugandan local languages in the dashboard.
# Supported languages: Luganda (lug), Acholi (ach), Runyankole (nyn),
#                      Ateso (teo), Lugbara (lgg)
# Get an API key at https://sunbird.ai
SUNBIRD_API_KEY=your_sunbird_api_key_here
SUNBIRD_API_URL=https://api.sunbird.ai
TRANSLATION_ENABLED=true
# Minimum confidence score (0–1) for language detection to trigger translation.
# Inputs below this threshold are treated as English.
TRANSLATION_MIN_CONFIDENCE=0.80
```

---

## Error Handling & Graceful Degradation

| Failure scenario | Behaviour |
|---|---|
| Sunbird API unreachable | Log warning; proceed in English; no badge shown |
| Language not detected / low confidence | Treat as English; proceed normally |
| Query translation fails | Proceed with original text; log warning |
| Answer translation fails | Return English answer with note: *"Could not translate answer — showing in English"* |
| `TRANSLATION_ENABLED=false` | Translation layer bypassed entirely; zero overhead |

All `TranslationError` exceptions are caught at the dashboard layer and never surface as unhandled exceptions.

---

## Files Changed

| File | Change |
|---|---|
| `src/translation/__init__.py` | New |
| `src/translation/client.py` | New |
| `src/config/settings.py` | Add 4 fields |
| `.env.example` | Add translation section (4 vars) |
| `dashboard/app.py` | Wrap Q&A and Search with translation layer; update `_answer_question` return type; update call-site unpacking at line 368 |
| `tests/test_translation_client.py` | New — unit tests with mocked HTTP for detect, translate, retry, degradation |

No new packages required. `httpx` (already a dependency) is used for Sunbird API calls.

---

## Out of Scope / Future Work

- TTS: reading answers aloud in local languages (Sunbird `/tasks/tts` is ready when needed)
- STT: voice query input (Sunbird `/tasks/stt`)
- Translating source document content at ingest time
- Language selector UI override (auto-detect is sufficient for now)
