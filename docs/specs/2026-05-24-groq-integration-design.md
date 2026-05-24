# GroqCloud Integration Design

**Date:** 2026-05-24  
**Status:** Approved  
**Goal:** Replace OpenAI as the LLM provider for chat and scraping with GroqCloud to reduce costs, while keeping OpenAI for embeddings and adding a UI model picker for users.

---

## Overview

GroqCloud is an OpenAI API-compatible inference provider running Llama models on LPU hardware. The integration adds `"groq"` as a first-class provider in `LLMClient` alongside the existing `"openai"` and `"ollama"` options. Because Groq uses the OpenAI SDK under the hood (different `base_url` + key), the diff is shallow — no changes to `_generate`, `stream_answer`, classification methods, or any service layer.

**Embeddings stay on OpenAI** (`text-embedding-3-small`). Groq does not offer an embeddings API, and the existing Qdrant collection does not need to be re-indexed.

---

## Settings (`src/config/settings.py`)

Three new fields:

```python
llm_provider: Literal["openai", "ollama", "groq"] = Field(default="openai")

groq_api_key: str = Field(default="")
groq_model: str = Field(default="llama-3.3-70b-versatile")
groq_temperature: float = Field(default=0.1)
```

`.env.example` gets a `GROQ_API_KEY=` placeholder.  
`GROQ_MODEL` and `GROQ_TEMPERATURE` are optional overrides with sensible defaults.

---

## LLMClient (`src/llm/client.py`)

A new `"groq"` branch in `__init__` uses the existing OpenAI SDK pointed at Groq's endpoint:

```python
elif self.provider == "groq":
    from openai import OpenAI
    if not settings.groq_api_key:
        raise ValueError("Groq API key required but not found in settings")
    self.client = OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    self.model = model or settings.groq_model
    self.temperature = temperature or settings.groq_temperature
```

All existing `_generate`, `stream_answer`, `classify_content`, `classify_urls`, `check_connection`, and `answer_question` code paths run **unchanged** — they already branch on `self.provider == "openai"`, which covers Groq since both use the same SDK.

`check_connection()` currently has `if self.provider == "openai": ... else: # ollama`. The Groq branch is added before the `else` so it hits the OpenAI check path correctly.

**JSON mode compatibility:** `llama-3.3-70b-versatile` supports `response_format={"type": "json_object"}` on GroqCloud. All classification methods continue working without modification.

---

## API Request Model (`src/api/models/requests.py`)

`ChatRequest` gains one optional field:

```python
from typing import Literal

class ChatRequest(BaseModel):
    session_id: str
    message: str
    language_override: str | None = None
    model_preference: Literal["openai", "groq"] | None = None
```

`None` means "use the server default" (`LLM_PROVIDER` from `.env`). WhatsApp never sets this field, so that path is unaffected.

---

## App Lifespan (`src/api/main.py`)

At startup, pre-warm up to two LLM clients on `app.state`:

```python
app.state.llm_client = LLMClient()  # server default (from LLM_PROVIDER)

if settings.groq_api_key:
    app.state.llm_client_groq = LLMClient(provider="groq")

if settings.openai_api_key:
    app.state.llm_client_openai = LLMClient(provider="openai")
```

Only clients with configured keys are initialised. If neither extra client is available for a requested `model_preference`, the route falls back to the default.

---

## Chat Routes (`src/api/routes/chat.py`)

Both `/chat` and `/chat/stream` resolve the active LLM client inline before passing to the service layer:

```python
# Select LLM client based on model_preference
if body.model_preference == "groq" and hasattr(request.app.state, "llm_client_groq"):
    active_llm = request.app.state.llm_client_groq
elif body.model_preference == "openai" and hasattr(request.app.state, "llm_client_openai"):
    active_llm = request.app.state.llm_client_openai
else:
    active_llm = llm_client  # Depends(get_llm_client) — server default
```

`process_chat` and `process_chat_stream` signatures and internals are **unchanged**.

---

## Frontend

### `useChat.js`

- Adds `modelPreference` state, defaulting to `"groq"` (or restored from `localStorage`).
- Persists selection to `localStorage` on change.
- Passes `modelPreference` into `streamMessage`.
- Exports `modelPreference` and `setModelPreference` from the hook.

### `api.js` — `streamMessage`

Adds `modelPreference` parameter included in the POST body:

```js
body: JSON.stringify({
  session_id: sessionId,
  message,
  language_override: languageOverride,
  model_preference: modelPreference,
})
```

### `ModelPicker` component (`src/components/ModelPicker.jsx`)

A compact 2-option inline toggle showing:
- **`GPT-4o Mini`** — OpenAI option
- **`Llama 3.3`** — Groq option (default)

The selected option is visually highlighted. The component is **always rendered** — both options always visible. If the user picks Groq but the server has no `GROQ_API_KEY`, the route silently falls back to the server default. No backend capability-check endpoint is needed.

### `LanguageBar.jsx`

`ModelPicker` is rendered on the right side of the `LanguageBar` row — that component is already the home for user preference controls.

### `ChatApp.jsx`

Receives `modelPreference` and `setModelPreference` from `useChat` and passes them to `LanguageBar` → `ModelPicker`.

---

## Scraping Pipeline

No changes required. The scraping pipeline instantiates `LLMClient()` with no arguments, picking up the provider from `settings.llm_provider`. Setting `LLM_PROVIDER=groq` in `.env` is sufficient to switch classification and summarisation to Groq.

---

## Default Model

`llama-3.3-70b-versatile` — strong quality for RAG answer synthesis and structured JSON classification. Cost on GroqCloud is a fraction of `gpt-4o-mini`.

---

## Error Handling

- If `GROQ_API_KEY` is not set and the user requests `model_preference: "groq"`, the route silently falls back to the server default. No error surfaced to the user.
- If Groq's API returns an error mid-stream, the existing `stream_answer` error handler catches it and the SSE layer yields a `{"type": "error"}` event — same behaviour as today.

---

## Files Changed

| File | Change |
|---|---|
| `src/config/settings.py` | Add `groq_api_key`, `groq_model`, `groq_temperature`; expand `llm_provider` Literal |
| `src/llm/client.py` | Add `"groq"` provider branch in `__init__` and `check_connection` |
| `src/api/models/requests.py` | Add `model_preference` field to `ChatRequest` |
| `src/api/main.py` | Pre-warm `llm_client_groq` and `llm_client_openai` on `app.state` |
| `src/api/routes/chat.py` | Resolve `active_llm` from `body.model_preference` in both handlers |
| `frontend/src/hooks/useChat.js` | Add `modelPreference` state + localStorage persistence |
| `frontend/src/api.js` | Thread `modelPreference` into `streamMessage` POST body |
| `frontend/src/components/ModelPicker.jsx` | New component — 2-option model toggle |
| `frontend/src/components/LanguageBar.jsx` | Render `ModelPicker` on the right side |
| `frontend/src/ChatApp.jsx` | Pass `modelPreference`/`setModelPreference` to `LanguageBar` |
| `.env.example` | Add `GROQ_API_KEY=` placeholder |

---

## Out of Scope

- Embeddings: remain on OpenAI (`text-embedding-3-small`). No re-indexing.
- WhatsApp: always uses server default provider. No UI picker for WhatsApp.
- Split 70B/8B model strategy: deferred — revisit if costs are still a concern after switching.
- Groq rate limit handling: existing `tenacity` retry logic in `_generate` covers transient errors.
