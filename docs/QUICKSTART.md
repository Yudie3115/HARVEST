# Post-Harvest Knowledge Scraper - Quick Start Guide

## Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose**
- **Git**
- **OpenAI API Key** (recommended) OR
- **16GB RAM minimum** (if using Ollama locally)
- **100GB+ disk space** for documents and vector database

Optional:
- **NVIDIA GPU** with 8GB+ VRAM (only if using Ollama - significantly speeds up LLM inference)

---

## Installation

### 1. Clone and Setup

```bash
# Clone repository (or create new directory)
mkdir postharvest-scraper
cd postharvest-scraper

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Poetry (if not already installed)
pip install poetry

# Install dependencies
poetry install
```

### 2. Start Infrastructure

```bash
# Start core services (PostgreSQL, MinIO, Qdrant, Prefect)
docker-compose up -d

# Check services are running
docker-compose ps

# Expected output:
# NAME                     STATUS
# postharvest-postgres     Up (healthy)
# postharvest-minio        Up (healthy)
# postharvest-qdrant       Up
# postharvest-prefect      Up

# Note: Ollama is optional and commented out by default
# Uncomment Ollama services in docker-compose.yml if needed
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env

# IMPORTANT: Add your OpenAI API key
OPENAI_API_KEY=sk-...your-key-here...

# Or, if using Ollama:
# 1. Uncomment Ollama services in docker-compose.yml
# 2. Set LLM_PROVIDER=ollama in .env
# 3. Start Ollama: docker-compose up -d ollama
```

### 4. Initialize Database

```bash
# Create database schema
poetry run python scripts/init_db.py

# Expected output:
# ✓ Connected to PostgreSQL
# ✓ Created tables: crawl_runs, documents, document_classifications, ...
# ✓ Created indexes
# ✓ Database initialized successfully
```

### 5. Verify LLM Setup

**If using OpenAI (recommended):**

```bash
# Test OpenAI API connection
poetry run python -c "
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'test'}],
    max_tokens=5
)
print('✓ OpenAI connection successful')
"
```

**If using Ollama (optional):**

```bash
# Check Ollama is running and model is loaded
docker exec postharvest-ollama ollama list

# Should show: llama3.1:8b

# Test Ollama API
curl http://localhost:11434/api/tags

# If model isn't loaded, pull it:
docker exec postharvest-ollama ollama pull llama3.1:8b
```

---

## Quick Test Run

### Test 1: Single Site Discovery

```bash
# Activate virtual environment
source venv/bin/activate

# Run discovery for NARO site
poetry run python -c "
from src.flows.discovery import discover_content
result = discover_content('naro')
print(result)
"

# Expected output:
# Starting discovery flow for naro
# Crawl complete: 150 URLs discovered from NARO
# Classifying 150 URLs with LLM
# Filtered 45 relevant URLs (threshold: 6.0)
# Stored 45 documents in database
# Discovery complete: {'documents_stored': 45, ...}
```

### Test 2: Check Database

```bash
# Connect to PostgreSQL
docker exec -it postharvest-postgres psql -U scraper -d postharvest_scraper

# Query discovered documents
SELECT 
    site_name,
    COUNT(*) as doc_count,
    AVG((metadata->>'relevance_score')::float) as avg_relevance
FROM documents
GROUP BY site_name;

# Exit psql
\q
```

### Test 3: Check MinIO Storage

Open browser to: http://localhost:9001
- Username: `minioadmin`
- Password: `minioadmin123`

You should see the `postharvest-documents` bucket (will be created on first document download).

---

## Running Full Workflows

### Option A: Using Prefect UI (Recommended)

1. **Start Prefect Server** (if not already running via docker-compose)

```bash
poetry run prefect server start
```

2. **Open Prefect UI**: http://localhost:4200

3. **Deploy Flows**

```bash
poetry run python scripts/deploy_flows.py
```

4. **Run from UI**:
   - Navigate to "Flows" → "discover_all_sites"
   - Click "Run" → "Quick run"
   - Monitor progress in real-time

### Option B: Command Line

```bash
# Run discovery for all sites
poetry run python -c "
from src.flows.discovery import discover_all_sites
results = discover_all_sites()
for r in results:
    print(f\"{r['site_name']}: {r['documents_stored']} docs\")
"

# Run processing pipeline (after discovery)
poetry run python -c "
from src.flows.processing import process_documents_flow
process_documents_flow()
"
```

### Option C: Scheduled Runs

```bash
# Start Prefect agent to handle scheduled runs
poetry run prefect agent start -q default

# Deploy with schedule (runs daily at 2 AM)
poetry run python scripts/deploy_flows.py --schedule
```

---

## Using the Streamlit Dashboard

### Start Dashboard

```bash
poetry run streamlit run dashboard/app.py

# Or with custom port
poetry run streamlit run dashboard/app.py --server.port 8502
```

### Access Dashboard

Open browser to: http://localhost:8501

**Dashboard Features:**

1. **Overview Tab**
   - Real-time crawl statistics
   - Document count by topic
   - Recent activity timeline

2. **Documents Tab**
   - Browse discovered documents
   - Filter by site, topic, status
   - Download individual documents
   - Queue for reprocessing

3. **Search Tab**
   - Semantic search across knowledge base
   - View relevant chunks with sources
   - Test retrieval quality

4. **Analytics Tab**
   - Topic coverage visualization
   - Site comparison statistics
   - Quality metrics

5. **Config Tab**
   - Adjust LLM settings
   - Configure crawl parameters
   - Set relevance thresholds

---

## Common Tasks

### Add a New Site

1. Edit `src/config/site_configs.py`:

```python
SITE_CONFIGS["new_site"] = SiteConfig(
    name="New Site Name",
    url="https://example.go.ug/",
    strategy="recursive_crawl",
    max_depth=3,
    url_patterns=[r".*publication.*", r".*\.pdf$"],
    keywords=["post-harvest", "storage"],
    llm_filter=True,
    rate_limit=2.0
)
```

2. Enable in `.env`:

```bash
NEW_SITE_ENABLED=true
```

3. Run discovery:

```bash
poetry run python -c "
from src.flows.discovery import discover_content
discover_content('new_site')
"
```

### Reprocess Failed Documents

```bash
# Via Streamlit dashboard: Documents Tab → Filter by "Failed" → Select → "Reprocess"

# Or via Python:
poetry run python -c "
from src.flows.processing import reprocess_failed_flow
reprocess_failed_flow()
"
```

### Check System Health

```bash
# Check all services
docker-compose ps

# Check LLM connection (OpenAI)
poetry run python -c "from src.llm.client import LLMClient; client = LLMClient(); client.check_connection()"

# Check LLM connection (Ollama - if using)
curl http://localhost:11434/api/tags

# Check PostgreSQL
docker exec -it postharvest-postgres pg_isready

# Check MinIO
curl http://localhost:9000/minio/health/live

# Check Qdrant
curl http://localhost:6333/collections
```

### View Logs

```bash
# View all logs
docker-compose logs -f

# Specific service
docker-compose logs -f ollama
docker-compose logs -f postgres

# Application logs (if running locally)
tail -f logs/scraper.log
```

---

## Troubleshooting

### Issue: LLM connection errors

**For OpenAI:**
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test connection
poetry run python -c "
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
print(client.models.list())
"
```

**For Ollama:**
```bash
# Check if container is running
docker-compose ps ollama

# Pull model manually
docker exec postharvest-ollama ollama pull llama3.1:8b

# Check available models
docker exec postharvest-ollama ollama list

# If GPU not detected, Ollama will use CPU (slower but works)
```

### Issue: PostgreSQL connection refused

**Solution:**
```bash
# Check if container is running
docker-compose ps postgres

# Restart container
docker-compose restart postgres

# Check logs
docker-compose logs postgres

# Verify connection
docker exec -it postharvest-postgres psql -U scraper -d postharvest_scraper -c "SELECT 1;"
```

### Issue: MinIO bucket not created

**Solution:**
```bash
# Create bucket manually via UI (http://localhost:9001)
# Or via Python:
poetry run python -c "
from src.storage.minio_client import MinIOClient
client = MinIOClient()
client.ensure_bucket()
print('Bucket created')
"
```

### Issue: Slow LLM inference

**Solutions:**
1. **Use OpenAI** (recommended): Fast API-based inference, no local resources
2. **Switch to faster OpenAI model**: `gpt-4o-mini` is optimized for speed
3. **If using Ollama**:
   - Use smaller model: Change to `llama3.1:7b` or `llama3.1:8b-q4` (quantized)
   - Use GPU: Add GPU support to docker-compose.yml
   - Increase timeout: Adjust `OLLAMA_MAX_TOKENS` in `.env`
4. **Batch processing**: Already implemented for efficiency

### Issue: Out of disk space

**Solutions:**
```bash
# Check disk usage
docker system df

# Clean up old images/volumes
docker system prune -a --volumes

# Archive old documents (move from MinIO to cheaper storage)
# Implement in your backup strategy
```

---

## Performance Tuning

### For Production (with OpenAI - Recommended)

```bash
# .env settings
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini  # Fast & cost-effective
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

CRAWL_DELAY_SECONDS=1.0
CRAWL_MAX_DEPTH=4
EMBEDDING_BATCH_SIZE=64
```

### For Development (Laptop/Desktop with OpenAI)

```bash
# .env settings
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai

CRAWL_DELAY_SECONDS=3.0
CRAWL_MAX_DEPTH=2
EMBEDDING_BATCH_SIZE=16
```

### For Local Development (Ollama - No API costs)

```bash
# .env settings
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1:8b
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL_LOCAL=all-MiniLM-L6-v2

CRAWL_DELAY_SECONDS=3.0
CRAWL_MAX_DEPTH=2
EMBEDDING_BATCH_SIZE=16

# Uncomment Ollama services in docker-compose.yml
# docker-compose up -d ollama
```

### Scaling Prefect Workers

```bash
# Start multiple workers for parallel processing
poetry run prefect agent start -q default &
poetry run prefect agent start -q default &
poetry run prefect agent start -q default &

# Or use Dask for distributed processing
poetry install --extras distributed
# Update flows to use DaskTaskRunner
```

---

## Next Steps

1. **Run Initial Discovery**
   - Test on one site first (NARO)
   - Verify data quality in dashboard
   - Adjust relevance threshold if needed

2. **Enable All Sites**
   - Run discovery for all 4 sites
   - Monitor crawl progress in Prefect UI
   - Check for errors and adjust configs

3. **Setup Processing Pipeline**
   - Run content extraction on discovered docs
   - Generate embeddings
   - Populate vector database

4. **Configure Scheduling**
   - Set up daily full crawls
   - Hourly incremental checks for new content
   - Weekly quality checks and reprocessing

5. **Integrate with Your Application**
   - Use vector DB for semantic search
   - Build RAG application
   - Create API endpoints

6. **Production Deployment**
   - Move to production server
   - Setup monitoring and alerting
   - Implement backup strategy
   - Add authentication to dashboards

---

## Useful Commands Cheat Sheet

```bash
# Start everything
docker-compose up -d && poetry run streamlit run dashboard/app.py

# Stop everything
docker-compose down

# Reset database (careful!)
docker-compose down -v
docker-compose up -d postgres
poetry run python scripts/init_db.py

# View Prefect flows
poetry run prefect deployment ls

# Manual crawl
poetry run python -c "from src.flows.discovery import discover_content; discover_content('naro')"

# Check logs
docker-compose logs -f | grep ERROR

# Database backup
docker exec postharvest-postgres pg_dump -U scraper postharvest_scraper > backup.sql

# Database restore
docker exec -i postharvest-postgres psql -U scraper postharvest_scraper < backup.sql
```

---

## Getting Help

- **Check logs**: `docker-compose logs -f`
- **Verify services**: `docker-compose ps`
- **Database queries**: Connect via `psql` and inspect tables
- **Test LLM**: Use `curl` to test Ollama API
- **Dashboard errors**: Check Streamlit terminal output

---

## What's Next?

Once you have data flowing, consider:

1. **Building a RAG application** with LangChain
2. **Creating an API** with FastAPI for your knowledge base
3. **Adding more data sources** (social media, forums, YouTube)
4. **Fine-tuning embeddings** for better search
5. **Implementing feedback loops** to improve classification

Enjoy building your post-harvest knowledge base! 🌾
