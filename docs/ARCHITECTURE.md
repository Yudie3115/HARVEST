# Architecture

## System overview

PostHarvest AI has two distinct parts that share the same infrastructure:

1. **The knowledge pipeline** — crawls agricultural websites, processes documents, and indexes them into a vector database. Runs on a schedule via Prefect.
2. **The chatbot layer** — exposes the indexed knowledge through a public API consumed by a React web app and WhatsApp.

```
┌──────────────────────────────────────────────────────────┐
│                   Public-facing (chatbot)                 │
│                                                          │
│   Web browser ──→ React SPA ──→ FastAPI ──→ RAG pipeline │
│   WhatsApp ──────────────────→ FastAPI ──→ RAG pipeline  │
└──────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│                   Shared infrastructure                   │
│                                                          │
│   PostgreSQL  ·  Vector DB  ·  MinIO                     │
└─────────────────────────▲────────────────────────────────┘
                          │
┌─────────────────────────┴────────────────────────────────┐
│                   Knowledge pipeline (internal)           │
│                                                          │
│   Prefect ──→ Scrapers ──→ Extractors ──→ LLM classify   │
│                                    └──→ Embed ──→ Vector DB│
│   Streamlit dashboard (monitoring + manual ingestion)    │
└──────────────────────────────────────────────────────────┘
```

---

## Chatbot layer

### Request flow

```
User message (any language)
  │
  ▼
FastAPI /chat
  ├─ 1. Detect language          Sunbird AI /tasks/language_id
  ├─ 2. Translate to English     Sunbird AI /tasks/translate
  ├─ 3. Embed query              OpenAI text-embedding-3-small (1536d)
  ├─ 4. Vector search            ChromaDB or Qdrant cosine similarity, top-10
  ├─ 5. Synthesise answer        OpenAI GPT-4o-mini + retrieved chunks
  ├─ 6. Translate answer back    Sunbird AI /tasks/translate
  └─ 7. Persist + return         chat_messages → PostgreSQL
```

### Components

**`src/api/`** — FastAPI application

| File | Purpose |
|---|---|
| `main.py` | App factory, CORS, rate limiter, lifespan (clients created once at startup) |
| `dependencies.py` | FastAPI `Depends()` injectables for DB session and service clients |
| `routes/chat.py` | `POST /chat` — main Q&A endpoint |
| `routes/session.py` | `POST /session/new`, `GET /session/{id}/history` |
| `routes/whatsapp.py` | `GET/POST /webhook/whatsapp` — Meta Cloud API webhook |
| `routes/health.py` | `GET /health` |
| `services/chat_service.py` | RAG pipeline orchestration |
| `services/whatsapp_service.py` | Sends replies via Meta Cloud API |
| `models/requests.py` | Pydantic request schemas |
| `models/responses.py` | Pydantic response schemas |

**Rate limiting (slowapi)**
- Web: 20 requests / hour / IP address
- WhatsApp: 30 messages / hour / phone number

**Session management**
- Web: UUID stored in browser `localStorage`, maps to a `chat_sessions` row
- WhatsApp: phone number maps to a persistent `chat_sessions` row
- Context window: last 10 messages (5 turns) loaded per request

**`frontend/`** — React SPA (Vite + Tailwind CSS)

| Component | Purpose |
|---|---|
| `App.jsx` | Root — composes all panels, manages session and chat state |
| `Header.jsx` | Logo, language picker (auto-detect or explicit override) |
| `ChatWindow.jsx` | Scrollable message list, auto-scrolls on new messages |
| `MessageBubble.jsx` | User / assistant bubbles with avatar |
| `SourceChips.jsx` | Tappable citation chips below assistant answers |
| `LanguageBar.jsx` | "Responding in X · auto-detected" status strip |
| `InputBar.jsx` | Expanding textarea, Enter to send |
| `hooks/useSession.js` | Creates / restores session from localStorage |
| `hooks/useChat.js` | Message state, loading state, calls API |

---

## Knowledge pipeline

### Discovery pipeline

```
crawl_site(site_config)
  └─ extract all URLs from site
       └─ classify_urls_batch(urls)  ← LLM scores relevance 0-10
            └─ store relevant documents in PostgreSQL (status: DISCOVERED)
```

### Processing pipeline

```
process_document(doc_id, url)
  ├─ download_document()     → MinIO (raw file)
  ├─ extract_content()       → text (PDF/HTML/video)
  ├─ classify_content()      → topics, crops, regions, relevance (LLM)
  ├─ chunk_text()            → 1000-token chunks, 200-token overlap
  ├─ embed_chunks()          → OpenAI / sentence-transformers
  └─ upsert_to_vector_db()   → vectors with payload metadata
```

### Scheduling

| Schedule | What runs |
|---|---|
| Daily 02:00 | Full crawl of all sites + process queue |
| Hourly | Incremental discovery only |
| Weekly | Reprocess failed documents |

---

## Database schema

### Knowledge pipeline tables

| Table | Purpose |
|---|---|
| `crawl_runs` | One row per crawl execution (site, status, counters) |
| `documents` | Discovered documents (URL, status, file hash, metadata) |
| `document_classifications` | LLM-generated metadata (topics, crops, regions, relevance) |
| `content_chunks` | Text chunks linked to vector DB IDs |

### Chatbot tables

| Table | Purpose |
|---|---|
| `chat_sessions` | One row per conversation (channel, identifier, timestamps) |
| `chat_messages` | All messages (role, content, detected language, sources JSONB) |

---

## Infrastructure

All services run as Docker containers. Local development uses `docker-compose.yml`. Production runs on a single DigitalOcean droplet managed by Dokku.

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | postgres:15-alpine | 5433 (host) | All persistent data |
| `qdrant` | qdrant/qdrant | 6333, 6334 | Vector search for Docker/production |
| `minio` | minio/minio | 9000, 9001 | Document object storage |
| `prefect-server` | prefecthq/prefect | 4200 | Workflow orchestration UI |
| `api` | (built locally) | 8000 | FastAPI chatbot backend |
| `frontend` | (built locally) | 5173→80 | React chat UI (nginx in prod) |

> PostgreSQL is exposed on host port **5433** (not 5432) to avoid conflict with any local PostgreSQL instance.

> Non-Docker local development can use embedded ChromaDB instead of Qdrant by setting `VECTOR_DB_PROVIDER=chroma`.

---

## Translation

Sunbird AI provides bidirectional translation between English and five Ugandan languages.

| Code | Language |
|---|---|
| `eng` | English |
| `lug` | Luganda |
| `ach` | Acholi |
| `nyn` | Runyankole |
| `teo` | Ateso |
| `lgg` | Lugbara |

Translation is automatically disabled if `SUNBIRD_API_KEY` is not set — the system falls back to English-only with no errors.

---

## LLM configuration

| Setting | Default | Notes |
|---|---|---|
| Provider | OpenAI | Falls back to Ollama if no API key |
| Model | `gpt-4o-mini` | Sufficient for classification and Q&A |
| Embeddings | `text-embedding-3-small` | 1536 dimensions |
| Temperature | 0.1 | Low randomness for factual answers |
| Max tokens | 8192 | Per response |

Local (zero-cost) alternative: set `LLM_PROVIDER=ollama`, `EMBEDDING_PROVIDER=local`. Point `OLLAMA_BASE_URL` at your Ollama host and set `OLLAMA_MODEL=gemma4:e2b`. Install the extras with `poetry install --extras ollama`. See QUICKSTART for the full walkthrough.

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full production deployment guide (Dokku on DigitalOcean).
