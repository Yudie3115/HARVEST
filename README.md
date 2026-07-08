# PostHarvest AI

An AI-powered knowledge base for post-harvest practices in Uganda. Automatically scrapes, classifies, and indexes content from agricultural sources — then exposes it through a multilingual chatbot (web + WhatsApp) and a semantic search API.

Built by **[Fourlanes](https://fourlanes.tech)**.

---

## What it does

**Scraper & knowledge pipeline** — crawls agricultural websites (NARO, Ministry of Agriculture, Extension Portal, UBOS, APHLIS), extracts and classifies content using LLMs, stores documents in a vector database for semantic retrieval.

**Public chatbot** — farmers, extension workers, and researchers can ask questions in English or five Ugandan languages (Luganda, Acholi, Runyankole, Ateso, Lugbara) via web browser or WhatsApp. Answers are grounded in the indexed documents with citations.

**Internal admin dashboard** — Streamlit app for monitoring crawl runs, browsing documents, running semantic search, and manually ingesting documents.

---

## Architecture

```
  Web browser            WhatsApp
      │                      │
      ▼                      ▼
React SPA             Meta Cloud API
(chat.domain.com)          │
      │                     │
      └──────────┬──────────┘
                 ▼
         FastAPI  (api.domain.com)
         ├── Language detection (Sunbird AI)
         ├── Query translation → English
         ├── Semantic search (Qdrant)
         ├── Answer synthesis (OpenAI)
         └── Answer translation → user language
                 │
         ┌───────┴────────────────────┐
         ▼                            ▼
    PostgreSQL               Qdrant + MinIO
  (metadata, sessions)    (vectors, documents)
                 ▲
    Prefect + Scrapers
    (crawl & index pipeline)
                 ▲
    Streamlit dashboard (internal)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Chatbot API | FastAPI, uvicorn, slowapi |
| Chatbot frontend | React 18, Vite, Tailwind CSS |
| WhatsApp | Meta Cloud API |
| Scraping | Playwright, Scrapy, Trafilatura |
| Extraction | PyMuPDF, pdfplumber, yt-dlp |
| LLM | OpenAI (primary), Ollama / Gemma4 E2b (local alternative) |
| Embeddings | OpenAI text-embedding-3-small / sentence-transformers |
| Vector DB | Qdrant |
| Database | PostgreSQL 15 |
| Object storage | MinIO |
| Orchestration | Prefect 2 |
| Translation | Sunbird AI (5 Ugandan languages + English) |
| Admin UI | Streamlit |
| Infrastructure | Docker Compose (dev), Dokku on DigitalOcean (prod) |

---

## Documentation

| Doc | Contents |
|---|---|
| [Quick Start](docs/QUICKSTART.md) | Local development setup — scraper, API, frontend |
| [Deployment](docs/DEPLOYMENT.md) | Production deployment on Dokku/DigitalOcean |
| [Architecture](docs/ARCHITECTURE.md) | System design and component overview |
| [Project Structure](docs/PROJECT_STRUCTURE.md) | File tree and module descriptions |

---

## Local setup (short version)

```bash
# 1. Clone and install
git clone <repo-url> && cd post-harvest-knowledge-scraper
make install-local

# For Ollama / local LLM support:
# poetry install --extras ollama

# 2. Configure environment
cp .env.example .env   # set LLM_PROVIDER, model, and admin credentials

# 3. Start infrastructure
docker compose up -d                 # full Docker stack
# or run PostgreSQL, Qdrant, and MinIO locally/externally for non-Docker app development

# 4. Initialise database
make init-db

# 5. Start services
make local                                  # non-Docker API + chatbot UI
poetry run streamlit run dashboard/app.py                  # admin dashboard → http://localhost:8501
```

For a one-command non-Docker first run after configuring `.env` and starting
local PostgreSQL, Qdrant, and MinIO, use `make dev-local`.

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full guide including testing, crawling, and troubleshooting.

---

## Service ports (local)

| Service | URL |
|---|---|
| Chatbot UI | http://localhost:5173 |
| Chatbot API | http://localhost:8000 |
| Admin dashboard | http://localhost:8501 |
| Prefect UI | http://localhost:4200 |
| MinIO console | http://localhost:9001 |
| Qdrant | http://localhost:6333 |
| PostgreSQL | localhost:5433 |

---

## Contact

**Fourlanes Digital Studio**
Website: https://fourlanes.tech · Email: edwinm@fourlanes.tech

---

*Built for sustainable agriculture in Uganda* 🌾
