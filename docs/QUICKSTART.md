# Quick Start Guide

## Prerequisites

- **Python 3.11+** and **Poetry**
- **Node.js 20+** and **npm** (for the chatbot frontend)
- **Docker & Docker Compose**
- **Git**
- **OpenAI API Key** (recommended) OR **Ollama** running on an accessible host with `gemma4:e2b` pulled
- **100 GB+ disk space** for documents and vector database

Optional:
- **NVIDIA GPU** (only if running Ollama — improves inference speed; not required for Gemma4 E2b at 2B scale)

---

## Installation

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd post-harvest-knowledge-scraper

# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install Python dependencies
poetry install

# If using Ollama as LLM provider (includes the `ollama` Python client):
poetry install --extras ollama

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Start infrastructure

```bash
# Start all services (PostgreSQL on 5433, MinIO, Qdrant, Prefect, API, Frontend)
docker compose up -d

# Check that services are healthy
docker compose ps
```

Expected output:

```
NAME                      STATUS
postharvest-postgres      Up (healthy)
postharvest-minio         Up (healthy)
postharvest-qdrant        Up
postharvest-prefect       Up
postharvest-api           Up
postharvest-frontend      Up
```

> PostgreSQL runs on host port **5433** (not 5432) so it can coexist with any local PostgreSQL instance.

> Ollama is optional. Uncomment the Ollama service in `docker-compose.yml` if you
> prefer a fully local, zero-cost LLM setup.

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and add your OpenAI key and admin credentials:
# OPENAI_API_KEY=sk-...
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=<strong-password>
# ADMIN_JWT_SECRET=<output of: openssl rand -hex 32>
```

The admin panel is available at **http://localhost:5173/admin** once the stack is running. Log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

**Optional: Translation (Ugandan local languages)**

To enable bidirectional translation between English and Luganda, Acholi, Runyankole, Ateso, or Lugbara, add a [Sunbird AI](https://sunbird.ai) API key:

```dotenv
SUNBIRD_API_KEY=your_sunbird_api_key_here
```

If `SUNBIRD_API_KEY` is empty, the translation feature is automatically disabled — no warnings or errors.

For a **fully local, no-cost** setup using Ollama (with Gemma4 E2b) instead:

```bash
# 1. Install the Ollama extras (if not done during poetry install):
poetry install --extras ollama

# 2. In .env, set:
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://<ollama-host>:11434   # or http://localhost:11434
OLLAMA_MODEL=gemma4:e2b
EMBEDDING_PROVIDER=local

# 3. Ensure the model is pulled on your Ollama host:
#    ollama pull gemma4:e2b

# 4. If running Ollama via Docker Compose (optional — skip if Ollama is on another machine):
docker compose up -d ollama
docker exec postharvest-ollama ollama pull gemma4:e2b
```

> **Remote Ollama**: if your Ollama instance is on a different machine, set `OLLAMA_BASE_URL` to its network address (e.g. `http://192.168.1.50:11434`). No other changes are needed.

### 4. Initialise the database

```bash
poetry run python scripts/init_db.py
```

Expected output:
```
✓ Connected to PostgreSQL
✓ Created tables: crawl_runs, documents, document_classifications, ...
✓ Database initialized successfully
```

---

## Running the chatbot

### Chatbot API (FastAPI)

```bash
# Development — auto-reloads on file changes
poetry run uvicorn src.api.main:app --reload --port 8000

# Verify it's up
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0"}
```

Key endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/session/new` | Start a new chat session |
| `POST` | `/chat` | Send a message, get an answer |
| `GET` | `/session/{id}/history` | Retrieve message history |
| `GET/POST` | `/webhook/whatsapp` | WhatsApp webhook (Meta Cloud API) |

### Chatbot frontend (React)

```bash
cd frontend
npm run dev
# Open http://localhost:5173
```

The frontend reads `VITE_API_URL` from the environment. It defaults to `http://localhost:8000` if not set.

To point it at a different API:

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

### Running both without Docker

If you prefer running the API and frontend outside Docker during development:

```bash
# Terminal 1 — infrastructure only
docker compose up -d postgres qdrant minio prefect-server

# Terminal 2 — API
poetry run uvicorn src.api.main:app --reload --port 8000

# Terminal 3 — frontend
cd frontend && npm run dev

# Terminal 4 — admin dashboard (optional)
poetry run streamlit run dashboard/app.py
```

---

## Testing

### All-in-one feature smoke test

Once all services are running (`docker compose up -d`) and the database is
initialised, run the smoke test to verify every feature works end-to-end:

```bash
poetry run python scripts/smoke_test.py
```

This will run through **6 sections** in order, printing `✓ PASS` or `✗ FAIL`
for each check:

```
🌾  Post-Harvest Scraper – Feature Smoke Test
════════════════════════════════════════════════════════════

──────────────────────────────────────────────────────────────
  1 / 6  Infrastructure Connectivity
──────────────────────────────────────────────────────────────
  ✓ PASS  PostgreSQL connection
  ✓ PASS  MinIO connection
  ✓ PASS  Qdrant connection
  ✓ PASS  LLM connection
  ✓ PASS  Embedding service
           → dimension: 1536

──────────────────────────────────────────────────────────────
  2 / 6  Content Extraction
──────────────────────────────────────────────────────────────
  ✓ PASS  HTML extraction (trafilatura/BS4)
  ✓ PASS  Text chunking
           → 4 chunks produced

──────────────────────────────────────────────────────────────
  3 / 6  LLM Classification
──────────────────────────────────────────────────────────────
  ✓ PASS  URL classification
           → top relevance score: 8.5/10
  ✓ PASS  Content classification
           → relevance score: 9.0/10

──────────────────────────────────────────────────────────────
  4 / 6  Vector DB Roundtrip (embed → store → search)
──────────────────────────────────────────────────────────────
  ✓ PASS  Embed + upsert + search + delete
           → 5 results returned

──────────────────────────────────────────────────────────────
  5 / 6  Discovery Pipeline (live crawl of NARO)
──────────────────────────────────────────────────────────────
  ✓ PASS  Crawl + LLM classify + DB store
           → 152 URLs, 43 stored

──────────────────────────────────────────────────────────────
  6 / 6  Processing Pipeline (download → extract → embed → store)
──────────────────────────────────────────────────────────────
  ✓ PASS  Process one document end-to-end
           → status: processed, chunks: 8

Results: 11/11 passed (0 skipped, 0 failed)

  All checks passed!
```

Flags:

| Flag | Effect |
|------|--------|
| `--skip-crawl` | Skip the live crawl (sections 1–4 only, ~10 s) |
| `--skip-process` | Skip the processing pipeline test |

For the fastest infrastructure-only check:

```bash
poetry run python scripts/smoke_test.py --skip-crawl --skip-process
```

---

### Step-by-step (for onboarding / debugging)

The smoke test above runs everything automatically. If you prefer to validate
each layer manually, use the steps below.

### Unit tests (no services required)

The test suite runs entirely with mocks – no live database, LLM API, or Docker
services needed.

```bash
poetry run pytest tests/ -v
```

Expected output:
```
107 passed in ~3s
```

Test coverage by module:

| File | What is tested |
|------|---------------|
| `tests/test_utils.py` | Hashing, text cleaning, chunking, keyword matching |
| `tests/test_extractors.py` | HTML extraction, PDF parsing, VTT parsing, video metadata |
| `tests/test_llm.py` | URL classification, content classification, prompt builders, embeddings |
| `tests/test_storage.py` | VectorDBClient (Qdrant), PostgresClient – all with mocks |
| `tests/test_translation_client.py` | TranslationClient: translate, detect_language, check_connection, retry logic, text chunking – all with mocked HTTP |
| `tests/test_manual_ingestion.py` | PostgresClient helpers, `ingest_manual_document` (file + URL paths, relevance gate, exception handling), CLI flags including folder ingestion (`--dir`, `--recursive`) and exit codes – all with mocks |

Run a single test file:

```bash
poetry run pytest tests/test_utils.py -v
```

Run a single test by name:

```bash
poetry run pytest tests/test_llm.py::TestLLMClient::test_classify_urls_returns_list -v
```

### Smoke tests (services must be running)

These commands verify each component end-to-end. Run `docker compose up -d` first.

**1. LLM connection**

```bash
# OpenAI
poetry run python -c "
from src.llm.client import LLMClient
llm = LLMClient()
print('Connected:', llm.check_connection())
"

# Ollama (if configured) — verify the server is reachable and model is available
poetry run python -c "
from src.llm.client import LLMClient
llm = LLMClient(provider='ollama')
print('Connected:', llm.check_connection())
"
# Or check directly:
curl -s http://<ollama-host>:11434/api/tags | python3 -m json.tool
```

**2. Embedding generation**

```bash
poetry run python -c "
from src.llm.embeddings import EmbeddingClient
embedder = EmbeddingClient()
vec = embedder.embed('Post-harvest storage of maize')
print(f'Embedding dim: {len(vec)}')  # 1536 (OpenAI) or 384 (local)
"
```

**3. Database connectivity**

```bash
poetry run python -c "
from src.storage.postgres import PostgresClient
db = PostgresClient()
stats = db.get_crawl_stats()
print('DB stats:', stats)
"

# Direct psql
docker exec -it postharvest-postgres psql -U scraper -d postharvest_scraper -c '\dt'
```

**4. MinIO (object storage)**

```bash
poetry run python -c "
from src.storage.minio_client import MinIOClient
m = MinIOClient()
print('Bucket objects:', m.list_objects()[:5])
"

# Browser: http://localhost:9001  (user: minioadmin / pass: minioadmin123)
```

**5. Qdrant (vector database)**

```bash
# REST health check
curl -s http://localhost:6333/collections | python3 -m json.tool

poetry run python -c "
from src.storage.vector_db import VectorDBClient
vdb = VectorDBClient()
vdb.ensure_collection()
print('Connected:', vdb.check_connection())
print('Collection info:', vdb.get_collection_info())
"
```

**6. Dashboard connection checker**

```bash
poetry run streamlit run dashboard/app.py
# Open http://localhost:8501 → Configuration tab → "Check Connections"
```

### Component integration smoke tests

After the database is initialised you can run a full discovery pass against a
single site without needing all services:

```bash
# Single-site discovery (requires DB + internet access + LLM)
poetry run python -c "
from src.flows.discovery import discover_content
result = discover_content('naro')
print(result)
"
# Expected: {'urls_discovered': ~150, 'documents_stored': ~40, 'status': 'completed'}
```

Process a single document (requires DB + MinIO + Qdrant + LLM):

```bash
poetry run python -c "
from src.flows.processing import process_document
# Use a real document_id from your DB, e.g.:
from src.storage.postgres import PostgresClient
from src.storage.models import DocumentStatus
db = PostgresClient()
docs = db.get_documents(status=DocumentStatus.DISCOVERED, limit=1)
if docs:
    doc = docs[0]
    result = process_document(str(doc.id), doc.url)
    print(result)
"
```

---

## Running Full Workflows

### Option A: Prefect UI (recommended)

1. Open **http://localhost:4200** (Prefect UI, started by docker compose)

2. Deploy the flows with their schedules:
   ```bash
   poetry run python scripts/deploy_flows.py
   # For a non-production environment:
   poetry run python scripts/deploy_flows.py --env development
   ```

3. Start a Prefect worker to execute flows:
   ```bash
   poetry run prefect worker start --pool postharvest-pool
   ```

4. Trigger manually from the UI or CLI:
   ```bash
   poetry run prefect deployment run 'post_harvest_scraper/daily-scraper-production'
   ```

### Option B: Command line

```bash
# Discover all sites
poetry run python -c "
from src.flows.discovery import discover_all_sites
results = discover_all_sites()
for r in results:
    print(f\"{r['site_name']}: {r['documents_stored']} docs stored\")
"

# Process all pending documents
poetry run python -c "
from src.flows.orchestration import main_scraper_flow
summary = main_scraper_flow(run_discovery=False, run_processing=True)
print(summary)
"

# Full pipeline (discovery + processing + quality check)
poetry run python -c "
from src.flows.orchestration import main_scraper_flow
summary = main_scraper_flow()
print(summary)
"
```

### Option C: Scheduled runs (production)

```bash
# Deploy with default schedules (daily 02:00, hourly incremental, weekly retry)
poetry run python scripts/deploy_flows.py

# Start worker – keep this running (e.g. in a systemd service or screen)
poetry run prefect worker start --pool postharvest-pool
```

---

## Dashboard

```bash
poetry run streamlit run dashboard/app.py
# Open http://localhost:8501
```

Tabs available:

| Tab | Contents |
|-----|----------|
| Overview | Live document counts, processing rate, vectors indexed, crawl activity chart |
| Documents | Searchable/filterable table of all discovered documents |
| Search | Semantic search across processed chunks in Qdrant; auto-translates queries from local Ugandan languages |
| Knowledge Base Q&A | Ask questions in English or a local Ugandan language; get grounded answers translated back to your language |
| Configuration | LLM/crawl settings, service connection health checker (PostgreSQL, MinIO, Qdrant, LLM, Prefect, Sunbird AI) |
| Add Document | Manually add a PDF, Word document, or HTML page by file upload or URL; LLM relevance check applied automatically |

---

## Makefile shortcuts

```bash
make help          # Show all available commands
make setup         # Install deps + start Docker + init DB
make start         # docker compose up -d
make stop          # docker compose down
make init-db       # Re-run database initialisation
make db-shell      # Open psql shell
make dashboard     # Start Streamlit dashboard
make crawl-naro    # Run discovery for NARO site only
make crawl-all     # Run discovery for all sites
make test          # Run full test suite (pytest)
make clean         # Remove __pycache__, .pyc, log files
```

---

## Common Tasks

### Add a new site

1. Edit `src/config/site_configs.py`:

```python
SITE_CONFIGS["new_site"] = SiteConfig(
    name="New Site",
    url="https://example.go.ug/",
    strategy="recursive_crawl",
    max_depth=3,
    url_patterns=[r".*publication.*", r".*\.pdf$"],
    keywords=["post-harvest", "storage"],
    llm_filter=True,
    rate_limit=2.0,
)
```

2. Enable it in `.env`:

```
NEW_SITE_ENABLED=true
```

3. Run discovery:

```bash
poetry run python -c "from src.flows.discovery import discover_content; discover_content('new_site')"
```

### Add a document manually

Bypass the crawl pipeline and ingest a single file or URL directly. The full LLM
classification and relevance check still apply — documents that score below the
threshold are rejected and will not appear in search results.

**From the dashboard** — open the **Add Document** tab, choose "Upload File" or
"From URL", optionally set a title and source label, then click the button.

**From the CLI:**

```bash
# Add a local PDF
poetry run python -m scripts.ingest_document --file /path/to/report.pdf

# Add a local file with a title and source label
poetry run python -m scripts.ingest_document \
  --file /path/to/guide.pdf \
  --title "Maize Drying Best Practices" \
  --site fao

# Download and ingest a remote document
poetry run python -m scripts.ingest_document --url https://example.org/guide.pdf

# Ingest every supported file in a folder as one source (top-level only)
poetry run python -m scripts.ingest_document --dir /path/to/guides --site fao

# ...including files in subfolders
poetry run python -m scripts.ingest_document --dir /path/to/guides --recursive --site fao
```

With `--dir`, every file whose extension is `.pdf`, `.docx`, `.doc`, `.html`, or
`.htm` is ingested; other files are ignored (and counted in the summary). Each
document is titled by its filename, so `--title` is not allowed with `--dir`. All
files share the same `--site` label, giving you a folder-as-one-source grouping.

Exit codes for `--file` / `--url`: `0` = processed successfully, `1` = rejected
(low relevance / no content) or failed. For `--dir`: `0` unless a file hard-fails
(extraction/embedding error) or the folder has no matching files — low-relevance
skips are expected in a bulk import and do not fail the run (each is still
reported per file).

The ingested document is stored with `site_name = "manual"` (or whatever you
pass with `--site`) and is immediately searchable in the dashboard and via the
Q&A tab.

### Reprocess failed documents

```bash
# Prefect CLI
poetry run prefect deployment run 'reprocess_failed/reprocess-failed-production'

# Or directly
poetry run python -c "
from src.flows.orchestration import reprocess_failed_flow
result = reprocess_failed_flow(limit=50)
print(result)
"
```

### Check system health

```bash
# All services
docker compose ps

# Logs
docker compose logs -f                     # all services
docker compose logs -f postgres            # single service
tail -f logs/scraper.log                   # application log

# Quick health endpoints
curl -s http://localhost:6333/collections  # Qdrant
curl -s http://localhost:9000/minio/health/live  # MinIO
curl -s http://localhost:4200/api/health   # Prefect

# Database backup
docker exec postharvest-postgres pg_dump -U scraper postharvest_scraper > backup.sql
```

---

## Troubleshooting

### `ModuleNotFoundError` or `No module named 'src'`

Always run commands through Poetry so the virtualenv is used:

```bash
poetry run python ...
poetry run pytest ...
poetry run streamlit ...
```

Or activate the shell once:

```bash
poetry shell
# then: python ..., pytest ..., etc.
```

### LLM connection errors

```bash
# Verify the configured provider and model
poetry run python -c "from src.config.settings import settings; print(settings.llm_provider, settings.ollama_model or settings.openai_model)"

# Quick connection test
poetry run python -c "from src.llm.client import LLMClient; LLMClient().check_connection()"
```

For Ollama specifically: confirm the host is reachable and the model has been pulled.

```bash
curl -s http://<ollama-host>:11434/api/tags | python3 -m json.tool
# Should list gemma4:e2b under "models"
```

### PostgreSQL connection refused

```bash
docker compose ps postgres
docker compose logs postgres
docker compose restart postgres
docker exec -it postharvest-postgres pg_isready
```

### Qdrant errors

```bash
curl http://localhost:6333/collections
docker compose restart qdrant

# If collection is corrupt, recreate it:
poetry run python -c "
from src.storage.vector_db import VectorDBClient
VectorDBClient().ensure_collection(recreate=True)
"
```

### Slow LLM inference (Ollama)

- Confirm your Ollama host has enough RAM (Gemma4 E2b needs ~2–3 GB; larger models need more)
- Enable GPU acceleration on the Ollama host for a significant speed boost
- Tune `OLLAMA_MAX_TOKENS` down if you don't need long responses (reduces per-call latency)
- For production throughput, switch to OpenAI `gpt-4o-mini`

---

## Performance settings

### Production (OpenAI)

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
CRAWL_DELAY_SECONDS=1.0
EMBEDDING_BATCH_SIZE=64
```

### Development / laptop

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
CRAWL_DELAY_SECONDS=3.0
CRAWL_MAX_DEPTH=2
EMBEDDING_BATCH_SIZE=16
```

### Fully local (Ollama + Gemma4 E2b, no API costs)

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://<ollama-host>:11434
OLLAMA_MODEL=gemma4:e2b
OLLAMA_MAX_TOKENS=2048
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL_LOCAL=all-MiniLM-L6-v2
CRAWL_DELAY_SECONDS=3.0
CRAWL_MAX_DEPTH=2
```

---

## Cheat sheet

```bash
# Setup from scratch
make setup
cd frontend && npm install && cd ..

# Run tests
make test

# Start everything (infrastructure + API + frontend)
docker compose up -d

# Or run services manually
poetry run uvicorn src.api.main:app --reload --port 8000
cd frontend && npm run dev
poetry run streamlit run dashboard/app.py

# Full scraper pipeline
poetry run python -c "from src.flows.orchestration import main_scraper_flow; main_scraper_flow()"

# Deploy flows to Prefect
poetry run python scripts/deploy_flows.py

# Start scheduled worker
poetry run prefect worker start --pool postharvest-pool

# Reset database
docker compose down -v
docker compose up -d postgres
poetry run python scripts/init_db.py
```

---

## Production deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full guide to deploying on Dokku/DigitalOcean, configuring SSL, and setting up WhatsApp.

---

*Enjoy building your post-harvest knowledge base!* 🌾
