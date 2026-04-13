# Chatbot Design Spec
**Date:** 2026-04-13
**Status:** Approved

## Overview

Add a public-facing multilingual chatbot to the PostHarvest Knowledge Scraper. The chatbot exposes the existing RAG pipeline (retrieval + LLM synthesis + Sunbird AI translation) through two channels: a web UI and WhatsApp. The internal Streamlit dashboard remains unchanged as an admin tool.

---

## Decisions Made

| Question | Decision |
|---|---|
| Users | Mixed: farmers, extension workers, researchers |
| Channels | Web browser + WhatsApp (Meta Cloud API) |
| Conversation history | Within-session only for web (localStorage-bound); WhatsApp sessions persist by phone number but context window is still last 10 messages |
| Deployment | Dokku on DigitalOcean, monorepo with separate Dockerfiles |
| Internal dashboard | Kept as-is (Streamlit, internal only) |
| Language handling | Auto-detect via Sunbird AI, user can override |
| Access control | Rate-limited, no login required |
| Web UI layout | Clean & minimal (full-screen chat, no sidebar) |

---

## Architecture

Two new public-facing services alongside the existing stack:

```
[Web Browser] ──HTTPS──▶ React SPA (chat.domain.com)
                              │
                              └──REST──▶ FastAPI (api.domain.com) ──▶ RAG pipeline
                                              ▲
[WhatsApp] ──webhook──────────────────────────┘

RAG pipeline (unchanged):
  Sunbird AI (detect + translate)
  → Qdrant (vector search)
  → OpenAI / Ollama (answer synthesis)
  → Sunbird AI (translate answer back)
  → PostgreSQL (session + message storage)
```

**Dokku apps:**
- `postharvest-api` → `api.domain.com` — FastAPI
- `postharvest-chat` → `chat.domain.com` — React SPA (nginx static)

Both live on the same DigitalOcean droplet. Existing infrastructure (PostgreSQL, Qdrant, MinIO, Prefect) is unchanged.

---

## Backend — FastAPI (`src/api/`)

### Directory structure

```
src/api/
├── main.py                  # FastAPI app, CORS, rate limiter init
├── routes/
│   ├── chat.py              # POST /chat
│   ├── session.py           # POST /session/new, GET /session/{id}/history
│   ├── whatsapp.py          # POST + GET /webhook/whatsapp
│   └── health.py            # GET /health
├── services/
│   ├── chat_service.py      # RAG pipeline orchestration
│   └── whatsapp_service.py  # Meta Cloud API client (send replies)
└── models/
    ├── requests.py          # Pydantic request schemas
    └── responses.py         # Pydantic response schemas
```

### Key endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/session/new` | Create session, return `session_id` (UUID) |
| `GET` | `/session/{id}/history` | Return messages for a session |
| `POST` | `/chat` | Send message, get answer + sources + detected language |
| `GET` | `/webhook/whatsapp` | Meta verification challenge |
| `POST` | `/webhook/whatsapp` | Receive WhatsApp message, reply via Meta Cloud API |
| `GET` | `/health` | Service health check |

### Chat request/response

```python
# Request
class ChatRequest(BaseModel):
    session_id: str
    message: str
    language_override: str | None = None  # e.g. "lug", "ach"

# Response
class ChatResponse(BaseModel):
    answer: str
    detected_language: str      # e.g. "eng", "lug"
    sources: list[SourceRef]    # [{title, url, site_name}]
    session_id: str
```

### Chat service flow

1. Load session history from `chat_messages` (last 10 messages / 5 turns for context)
2. Detect language via Sunbird AI (skip if `language_override` set)
3. Translate message to English if non-English
4. Embed translated message (OpenAI `text-embedding-3-small`)
5. Search Qdrant (top 10 chunks, cosine similarity)
6. Synthesize answer with `LLMClient.answer_question()` (existing)
7. Translate answer back to detected/selected language
8. Persist user message + assistant answer to `chat_messages`
9. Return answer, sources, detected language

### Rate limiting (slowapi)

- Web: 20 requests / hour / IP address
- WhatsApp: 30 messages / hour / phone number (keyed on sender's phone)

### WhatsApp specifics

- Meta requires `GET /webhook/whatsapp` returning the `hub.challenge` query param for verification
- Incoming messages arrive as JSON via `POST /webhook/whatsapp`
- Session is identified by sender's phone number — the same `chat_session` row is reused across conversations, but only the last 10 messages are used as context (older history is stored but not fed to the LLM)
- Replies sent back via Meta Cloud API using `httpx`
- `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` added to environment config

---

## Database — New Tables

Added to `src/storage/models.py` alongside existing tables.

### `chat_sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `channel` | enum | `web`, `whatsapp` |
| `identifier` | string, indexed | UUID (web) or phone number (WhatsApp) |
| `created_at` | timestamp | |
| `last_active_at` | timestamp | Updated on each message |

### `chat_messages`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `session_id` | UUID FK → chat_sessions | |
| `role` | enum | `user`, `assistant` |
| `content` | text | |
| `detected_language` | string | e.g. `eng`, `lug` |
| `sources` | JSONB | `[{title, url, site_name}]` |
| `created_at` | timestamp | |

---

## Frontend — React SPA (`frontend/`)

### Stack

- **React** with **Vite** (fast builds, simple config)
- **Tailwind CSS** (mobile-first styling, small bundle)
- No state management library — React `useState` / `useContext` is sufficient for chat

### Directory structure

```
frontend/
├── src/
│   ├── App.jsx
│   ├── components/
│   │   ├── ChatWindow.jsx       # scrollable message list
│   │   ├── MessageBubble.jsx    # user vs assistant styling
│   │   ├── SourceChips.jsx      # citation chips below answer
│   │   ├── InputBar.jsx         # text input + send button
│   │   └── LanguageBar.jsx      # "Responding in X · Switch language"
│   ├── hooks/
│   │   ├── useChat.js           # send message, manage history
│   │   └── useSession.js        # create/restore session from localStorage
│   └── api.js                   # fetch wrapper for FastAPI
├── index.html
├── vite.config.js
└── package.json
```

### UI layout (approved: Option A — clean & minimal)

```
┌─────────────────────────────────┐
│ 🌾 PostHarvest AI   🌐 English ▾ │  ← header (fixed)
├─────────────────────────────────┤
│                                 │
│  [assistant bubble]             │  ← scrollable message area
│              [user bubble]      │
│  [assistant bubble]             │
│  ① Source chip  ② Source chip   │
│                                 │
├─────────────────────────────────┤
│ ✓ Responding in English · Switch│  ← language status bar
├─────────────────────────────────┤
│ [ Ask about post-harvest... ] ➤ │  ← input bar (fixed)
└─────────────────────────────────┘
```

### Session handling

- On first load, `useSession` creates a session via `POST /session/new`, stores `session_id` in `localStorage`
- On return visits, restores existing `session_id` (within-session history only — if browser storage is cleared, a fresh session starts)
- Session history is not persisted across browser restarts by design

### Language flow

1. User submits message
2. API responds with `detected_language`
3. `LanguageBar` updates: "✓ Responding in Luganda · Switch language"
4. Clicking "Switch language" opens a dropdown of supported languages
5. Selected language is sent as `language_override` in subsequent requests

---

## Deployment

### New files

```
docker/
  api.Dockerfile       # python:3.12-slim, installs deps, runs uvicorn
  frontend.Dockerfile  # node:20-alpine build stage → nginx:alpine serve stage
Procfile               # web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

### docker-compose additions (local dev)

```yaml
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    networks:
      - scraper-network
    depends_on:
      postgres:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
    ports:
      - "5173:5173"
    environment:
      - VITE_API_URL=http://localhost:8000
```

### Dokku setup (one-time)

```bash
dokku apps:create postharvest-api
dokku apps:create postharvest-chat

dokku docker-options:add postharvest-api build '--file docker/api.Dockerfile'
dokku docker-options:add postharvest-chat build '--file docker/frontend.Dockerfile'

dokku config:set postharvest-api \
  DATABASE_URL=... OPENAI_API_KEY=... SUNBIRD_API_KEY=... \
  WHATSAPP_TOKEN=... WHATSAPP_PHONE_NUMBER_ID=...

# VITE_API_URL is baked in at Docker build time (not runtime), so pass it as a build arg:
dokku docker-options:add postharvest-chat build '--build-arg VITE_API_URL=https://api.yourdomain.com'

dokku domains:add postharvest-api api.yourdomain.com
dokku domains:add postharvest-chat chat.yourdomain.com
dokku letsencrypt:enable postharvest-api
dokku letsencrypt:enable postharvest-chat
```

### Deploy

```bash
git remote add dokku-api  dokku@your-droplet:postharvest-api
git remote add dokku-chat dokku@your-droplet:postharvest-chat

git push dokku-api main
git push dokku-chat main
```

---

## New Dependencies

### Python (add to `pyproject.toml`)

| Package | Purpose |
|---|---|
| `fastapi` | API framework |
| `uvicorn` | ASGI server |
| `slowapi` | Rate limiting for FastAPI |
| `httpx` | Meta Cloud API calls (already present) |
| `python-multipart` | Form data support for FastAPI |

### JavaScript (`frontend/package.json`)

| Package | Purpose |
|---|---|
| `react`, `react-dom` | UI framework |
| `vite` | Build tool |
| `@vitejs/plugin-react` | Vite React plugin |
| `tailwindcss` | Styling |
| `autoprefixer`, `postcss` | Tailwind support |

---

## What Is NOT Changing

- `src/llm/` — LLMClient, EmbeddingClient, prompts — untouched
- `src/storage/vector_db.py` — VectorDBClient — untouched
- `src/translation/client.py` — TranslationClient — untouched
- `src/storage/postgres.py` — PostgresClient — untouched (new tables added via models.py only)
- `dashboard/` — Streamlit app — untouched, stays internal
- `docker-compose.yml` — existing services unchanged, two new services added
- All existing scripts, flows, crawlers — untouched

---

## Out of Scope (this phase)

- User accounts / authentication
- Push notifications
- Analytics dashboard for chatbot usage
- Voice input
- SMS channel
- Admin controls for rate limit tuning
