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
        # Returns a language code or None if undetected/low confidence

    def translate(self, text: str, source_lang: str, target_lang: str) -> str
        # Returns original text unchanged if source == target
        # Raises TranslationError on permanent failure
        # Chunks input exceeding 512 tokens automatically

    def translate_to_english(self, text: str, source_lang: str) -> str
    def translate_from_english(self, text: str, target_lang: str) -> str
```

- Reads `settings.sunbird_api_key` and `settings.sunbird_api_url`
- Retries up to 3 times with exponential backoff on transient errors (429, 503, 504)
- Raises `TranslationError` (a typed exception) on permanent failure

### Modified: `src/config/settings.py`

Three new fields added to the `Settings` class:

```python
# Translation (Sunbird AI)
sunbird_api_key: str = Field(default="")
sunbird_api_url: str = Field(default="https://api.sunbird.ai")
translation_enabled: bool = Field(default=True)
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

**Q&A tab display** — additions:
- Badge above answer: `st.caption("Detected: Luganda — answering in Luganda")`
- Answer rendered as today (inside `st.info`)
- Sources remain in English

**`_semantic_search()`** — no signature change; query translation handled in the Search tab block before calling this function.

**Search tab** — addition:
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
| `src/config/settings.py` | Add 3 fields |
| `.env.example` | Add translation section |
| `dashboard/app.py` | Wrap Q&A and Search with translation layer |

---

## Out of Scope / Future Work

- TTS: reading answers aloud in local languages (Sunbird `/tasks/tts` is ready when needed)
- STT: voice query input (Sunbird `/tasks/stt`)
- Translating source document content at ingest time
- Language selector UI override (auto-detect is sufficient for now)
