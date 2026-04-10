# Post-Harvest Knowledge Scraper - Project Structure

## 📁 Complete File Tree

```
post-harvest-knowledge-scraper/
├── .env.example                        # Environment configuration template
├── .gitignore
├── pyproject.toml                      # Poetry dependencies
├── docker-compose.yml                  # Infrastructure services
├── Makefile                            # Convenience commands
│
├── src/                                # Main application code
│   ├── __init__.py
│   │
│   ├── config/                         # Configuration
│   │   ├── __init__.py
│   │   ├── settings.py                 # Pydantic settings (all env vars) ✓
│   │   └── site_configs.py             # Site-specific crawl configs ✓
│   │
│   ├── crawlers/                       # Web crawling (stubs)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── playwright_crawler.py
│   │   └── scrapy_crawler.py
│   │
│   ├── extractors/                     # Content extraction ✓
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py            # PDF text/table extraction ✓
│   │   ├── html_extractor.py           # HTML content extraction ✓
│   │   └── video_extractor.py          # Video metadata extraction ✓
│   │
│   ├── llm/                            # LLM integration ✓
│   │   ├── __init__.py
│   │   ├── client.py                   # Unified OpenAI/Ollama client ✓
│   │   ├── prompts.py                  # Prompt templates ✓
│   │   └── embeddings.py               # Embedding generation ✓
│   │
│   ├── storage/                        # Data persistence ✓
│   │   ├── __init__.py
│   │   ├── models.py                   # SQLAlchemy models ✓
│   │   ├── postgres.py                 # PostgreSQL client ✓
│   │   ├── minio_client.py             # MinIO object storage ✓
│   │   └── vector_db.py                # Qdrant vector database ✓
│   │
│   ├── translation/                    # Sunbird AI translation ✓
│   │   ├── __init__.py                 # Exports TranslationClient, TranslationError, SUPPORTED_LANGUAGES ✓
│   │   └── client.py                   # Sunbird API: translate, detect_language, check_connection ✓
│   │
│   ├── flows/                          # Prefect workflows ✓
│   │   ├── __init__.py
│   │   ├── discovery.py                # Discovery pipeline ✓
│   │   ├── processing.py               # Processing pipeline ✓
│   │   ├── orchestration.py            # Main orchestration ✓
│   │   └── manual_ingestion.py         # Manual document ingestion (file/URL) ✓
│   │
│   └── utils/                          # Utility functions ✓
│       ├── __init__.py
│       ├── logging.py                  # Loguru configuration ✓
│       ├── hashing.py                  # SHA-256 file hashing ✓
│       └── text_processing.py          # Chunking, cleaning ✓
│
├── dashboard/                          # Streamlit dashboard ✓
│   └── app.py                          # Overview, Documents, Search, Q&A, Config, Add Document tabs ✓
│
├── scripts/                            # Admin and setup scripts
│   ├── init_db.py                      # Database initialization ✓
│   ├── deploy_flows.py                 # Deploy Prefect workflows ✓
│   ├── smoke_test.py                   # End-to-end feature smoke test ✓
│   └── ingest_document.py              # CLI: manually add a file or URL ✓
│
├── tests/                              # Test suite (107 tests) ✓
│   ├── __init__.py
│   ├── test_extractors.py              # HTML, PDF, VTT extraction ✓
│   ├── test_llm.py                     # LLM client, classification, embeddings ✓
│   ├── test_manual_ingestion.py        # Manual ingestion, CLI (all services mocked) ✓
│   ├── test_storage.py                 # VectorDBClient, PostgresClient ✓
│   ├── test_translation_client.py      # TranslationClient (all HTTP mocked) ✓
│   └── test_utils.py                   # Hashing, text processing, chunking ✓
│
├── docs/                               # Documentation
│   ├── QUICKSTART.md                   # Setup and usage guide ✓
│   ├── PROJECT_STRUCTURE.md            # This file ✓
│   ├── postharvest_scraper_architecture.md  # Architecture overview ✓
│   └── superpowers/                    # Design specs and implementation plans
│       ├── specs/
│       └── plans/
│
└── logs/                               # Application logs (created at runtime)
    └── scraper.log
```

## ✅ Implementation Status

### Core Infrastructure
- ✅ Docker Compose setup (PostgreSQL, MinIO, Qdrant, Prefect)
- ✅ Environment configuration (Pydantic settings)
- ✅ Database models (SQLAlchemy)
- ✅ PostgreSQL client
- ✅ MinIO client
- ✅ Database initialization script

### LLM Integration
- ✅ Unified LLM client (OpenAI + Ollama with auto-detection)
- ✅ URL classification
- ✅ Content classification
- ✅ Prompt templates
- ✅ Embedding generation (OpenAI text-embedding-3-small / sentence-transformers fallback)

### Discovery Pipeline
- ✅ Crawling logic
- ✅ LLM-powered URL filtering
- ✅ Document metadata extraction
- ✅ Prefect flow structure

### Processing Pipeline
- ✅ HTML content extraction (Trafilatura)
- ✅ PDF extraction (PyMuPDF + pdfplumber)
- ✅ Video metadata extraction (yt-dlp)
- ✅ Text chunking
- ✅ Qdrant vector database integration
- ✅ End-to-end processing flow

### Translation
- ✅ Sunbird AI integration (Luganda, Acholi, Runyankole, Ateso, Lugbara)
- ✅ Automatic language detection
- ✅ Bidirectional translation (query → English → answer → local language)
- ✅ Graceful degradation (always falls back to English on failure)

### Manual Ingestion
- ✅ `ingest_manual_document()` — bypass crawl pipeline for a single file or URL
- ✅ LLM relevance gate applied (same threshold as the crawl pipeline)
- ✅ File upload path: PDF, DOCX, HTML; MIME detection via stdlib `mimetypes`
- ✅ URL path: delegates download to existing `download_document` task
- ✅ Classification stored even for rejected documents (audit trail)
- ✅ CLI: `scripts/ingest_document.py` with `--file` / `--url` / `--title` / `--site`
- ✅ Dashboard: "Add Document" tab with file uploader and URL input

### Dashboard
- ✅ Overview: document counts, processing rate, crawl activity chart
- ✅ Documents: filterable document browser with DB integration
- ✅ Search: semantic search with translation support
- ✅ Knowledge Base Q&A: RAG with translation support
- ✅ Configuration: LLM/crawl settings, connection health checker
- ✅ Add Document: manual file upload and URL ingestion with LLM relevance feedback

### Testing
- ✅ 107 unit tests across all modules (no live services required)

## 🔧 File Descriptions

### Configuration Files

**pyproject.toml**
- Poetry dependency management
- Python package metadata
- Development tool configuration

**.env.example**
- Environment variable template
- Database credentials
- API keys
- Service URLs

**docker-compose.yml**
- PostgreSQL database
- MinIO object storage
- Qdrant vector database
- Prefect server
- (Optional) Ollama LLM service

### Core Modules

**src/config/settings.py**
- Pydantic settings model
- Environment variable loading for all services (DB, LLM, MinIO, Qdrant, Prefect, Sunbird AI)

**src/config/site_configs.py**
- Site-specific crawl strategies for NARO, MoA, Extension, UBOS
- URL patterns, rate limits, and keyword filters

**src/llm/client.py**
- Unified LLM interface (OpenAI + Ollama)
- Automatic provider selection based on available API key
- URL classification and content classification

**src/llm/embeddings.py**
- Embedding generation (OpenAI text-embedding-3-small / sentence-transformers fallback)
- Batch embedding support

**src/storage/models.py**
- SQLAlchemy ORM models (documents, crawl_runs, classifications, processing_queue)

**src/storage/postgres.py**
- Document CRUD, crawl statistics, status queries

**src/storage/minio_client.py**
- Object storage for raw documents (PDFs, HTML snapshots)

**src/storage/vector_db.py**
- Qdrant client: upsert, search, collection management

**src/translation/client.py**
- Sunbird AI REST API client
- `translate()`: single or chunked translation with retry (429/503/504)
- `detect_language()`: confidence-threshold language detection
- `check_connection()`: connectivity probe for the status dashboard

**src/translation/__init__.py**
- Public exports: `TranslationClient`, `TranslationError`, `SUPPORTED_LANGUAGES`
- Supported codes: `eng`, `lug`, `ach`, `nyn`, `teo`, `lgg`

**src/flows/discovery.py** / **processing.py** / **orchestration.py**
- Prefect flows: daily full crawl, hourly incremental, weekly retry

**src/flows/manual_ingestion.py**
- `ingest_manual_document()`: accepts `content+filename` (file upload) or `url` (remote download)
- Uses sentinel `CrawlRun(site_name="manual")` as the FK anchor for all manual uploads
- Applies LLM relevance gate; documents below threshold are SKIPPED with classification stored

### Dashboard

**dashboard/app.py**
- Overview, Documents, Search, Knowledge Base Q&A, Configuration tabs
- Translation pre/post-processing in Search and Q&A tabs
- `_get_translator()` cached resource; graceful degradation on Sunbird failures

### Scripts

**scripts/init_db.py** — creates database tables and indexes
**scripts/deploy_flows.py** — deploys Prefect flows with schedules
**scripts/smoke_test.py** — end-to-end feature verification (6 sections, ~11 checks)
**scripts/ingest_document.py** — CLI for manually ingesting a file or URL (`--file`, `--url`, `--title`, `--site`)

## 🚀 Getting Started

See `docs/QUICKSTART.md` for the full setup guide.

```bash
git clone <repo-url>
cd post-harvest-knowledge-scraper
poetry install
docker compose up -d
poetry run python scripts/init_db.py
poetry run streamlit run dashboard/app.py
```

---

**Legend:**
- ✅ = Fully implemented and tested
