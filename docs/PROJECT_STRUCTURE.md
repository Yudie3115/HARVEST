# Project Structure

## File tree

```
post-harvest-knowledge-scraper/
│
├── docker-compose.yml              # All services (local dev)
├── pyproject.toml                  # Python dependencies (Poetry)
├── Makefile                        # Convenience commands
├── .env.example                    # Environment variable template
│
├── src/                            # Python source
│   ├── api/                        # Public chatbot API (FastAPI)
│   │   ├── main.py                 # App factory, CORS, rate limiter, lifespan
│   │   ├── dependencies.py         # FastAPI Depends() injectables
│   │   ├── routes/
│   │   │   ├── chat.py             # POST /chat
│   │   │   ├── session.py          # POST /session/new, GET /session/{id}/history
│   │   │   ├── whatsapp.py         # GET/POST /webhook/whatsapp
│   │   │   └── health.py           # GET /health
│   │   ├── services/
│   │   │   ├── chat_service.py     # RAG pipeline orchestration
│   │   │   └── whatsapp_service.py # Meta Cloud API reply client
│   │   └── models/
│   │       ├── requests.py         # Pydantic request schemas
│   │       └── responses.py        # Pydantic response schemas
│   │
│   ├── config/                     # Configuration
│   │   ├── settings.py             # Pydantic settings (all env vars)
│   │   └── site_configs.py         # Site-specific crawl configs
│   │
│   ├── crawlers/                   # Web crawling
│   │   ├── base.py
│   │   ├── playwright_crawler.py
│   │   └── scrapy_crawler.py
│   │
│   ├── extractors/                 # Content extraction
│   │   ├── pdf_extractor.py        # PDF text and table extraction
│   │   ├── html_extractor.py       # HTML content extraction
│   │   └── video_extractor.py      # Video metadata extraction
│   │
│   ├── llm/                        # LLM integration
│   │   ├── client.py               # Unified OpenAI/Ollama client
│   │   ├── prompts.py              # Prompt templates
│   │   └── embeddings.py           # Embedding generation
│   │
│   ├── storage/                    # Data persistence
│   │   ├── models.py               # SQLAlchemy ORM models (all tables)
│   │   ├── postgres.py             # PostgreSQL client
│   │   ├── minio_client.py         # MinIO object storage
│   │   └── vector_db.py            # Qdrant vector database
│   │
│   ├── translation/                # Sunbird AI translation
│   │   ├── __init__.py             # Exports TranslationClient, SUPPORTED_LANGUAGES
│   │   └── client.py               # translate, detect_language, check_connection
│   │
│   ├── flows/                      # Prefect workflows
│   │   ├── discovery.py            # URL discovery and classification
│   │   ├── processing.py           # Document download, extract, embed
│   │   ├── orchestration.py        # Main orchestration flow
│   │   └── manual_ingestion.py     # Manual document ingestion (file/URL)
│   │
│   └── utils/                      # Utilities
│       ├── logging.py              # Loguru configuration
│       ├── hashing.py              # SHA-256 file hashing
│       └── text_processing.py      # Chunking, cleaning
│
├── frontend/                       # React SPA (chatbot UI)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── index.css               # Tailwind + custom animations
│   │   ├── api.js                  # fetch wrapper for FastAPI
│   │   ├── components/
│   │   │   ├── Header.jsx          # Logo + language picker
│   │   │   ├── ChatWindow.jsx      # Scrollable message list
│   │   │   ├── MessageBubble.jsx   # User / assistant bubbles
│   │   │   ├── SourceChips.jsx     # Citation chips
│   │   │   ├── LanguageBar.jsx     # Language status strip
│   │   │   ├── InputBar.jsx        # Expanding textarea + send button
│   │   │   └── TypingIndicator.jsx # Three-dot loading animation
│   │   └── hooks/
│   │       ├── useSession.js       # Session creation / localStorage
│   │       └── useChat.js          # Message state, API calls
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
│
├── dashboard/                      # Streamlit admin dashboard (internal only)
│   └── app.py                      # 6 tabs: Overview, Documents, Search, Q&A, Config, Add Document
│
├── docker/                         # Production Dockerfiles
│   ├── api.Dockerfile              # python:3.12-slim → uvicorn
│   ├── frontend.Dockerfile         # node:20 build → nginx:alpine serve
│   └── nginx.frontend.conf         # nginx config (SPA fallback + gzip)
│
├── scripts/                        # Admin and setup scripts
│   ├── init_db.py                  # Create/migrate database tables
│   ├── deploy_flows.py             # Deploy Prefect workflows with schedules
│   ├── smoke_test.py               # End-to-end feature verification
│   └── ingest_document.py          # CLI: manually add a file, URL, or folder (--dir)
│
├── tests/                          # Test suite
│   ├── test_extractors.py
│   ├── test_llm.py
│   ├── test_manual_ingestion.py
│   ├── test_storage.py
│   ├── test_translation_client.py
│   └── test_utils.py
│
└── docs/                           # Documentation
    ├── QUICKSTART.md               # Local development setup
    ├── DEPLOYMENT.md               # Production deployment (Dokku/DigitalOcean)
    ├── ARCHITECTURE.md             # System design and component overview
    ├── PROJECT_STRUCTURE.md        # This file
    └── postharvest_scraper_architecture.md  # Legacy deep-dive (scraper internals)
```

---

## Key modules

### `src/api/` — Public chatbot API

FastAPI application that wraps the RAG pipeline for external consumption. Handles web and WhatsApp channels, rate limiting, session management, and the full translate → embed → search → synthesise → translate cycle.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request flow.

### `src/config/settings.py`

Single source of truth for all configuration. Pydantic Settings model reads from `.env`. Adding a new setting: add a `Field()` here and a matching entry in `.env.example`.

### `src/storage/models.py`

All SQLAlchemy ORM models in one file. Knowledge pipeline tables (`crawl_runs`, `documents`, `document_classifications`, `content_chunks`) and chatbot tables (`chat_sessions`, `chat_messages`).

### `src/llm/client.py`

Unified LLM interface. Automatically selects OpenAI if `OPENAI_API_KEY` is set, falls back to Ollama. Used by the classification pipeline and the chat service.

### `src/translation/client.py`

Sunbird AI REST client. Handles chunking for long texts, exponential backoff on rate limits, and graceful fallback to English when the service is unavailable.

### `src/flows/`

Prefect workflows for the scraping pipeline. `discovery.py` finds and scores URLs; `processing.py` downloads, extracts, classifies, embeds, and stores documents; `orchestration.py` ties them together with scheduling.

### `frontend/`

React SPA built with Vite and Tailwind. Connects to the FastAPI backend via `VITE_API_URL`. Session ID stored in `localStorage`. Language detection auto-applied based on API response; user can override via the header dropdown.

### `dashboard/app.py`

Streamlit app for internal use. Not exposed publicly in production. Useful for monitoring crawl runs, browsing and searching the document index, running the Q&A pipeline interactively, and manually ingesting individual documents.

---

## Database tables

| Table | Owner | Purpose |
|---|---|---|
| `crawl_runs` | Pipeline | One row per crawl execution |
| `documents` | Pipeline | All discovered documents |
| `document_classifications` | Pipeline | LLM-generated metadata |
| `content_chunks` | Pipeline | Text chunks linked to Qdrant vector IDs |
| `chat_sessions` | Chatbot | One row per conversation |
| `chat_messages` | Chatbot | All messages with language and sources |

---

## Adding a new site to the scraper

1. Add a `SiteConfig` entry in `src/config/site_configs.py`
2. Add `<name>_enabled: bool = Field(default=False)` in `src/config/settings.py`
3. Add it to the `enabled_sites` property in `settings.py`
4. Add `<NAME>_ENABLED=true` to `.env`
5. Run discovery: `poetry run python -c "from src.flows.discovery import discover_content; discover_content('<name>')"`
