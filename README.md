# Post-Harvest Knowledge Scraper

An AI-powered web scraping and knowledge extraction system for building a comprehensive post-harvest practices knowledge base for Uganda. Uses open-source LLMs (Llama 3.1 via Ollama), Prefect orchestration, and a Streamlit dashboard.

## 🎯 Project Goals

Intelligently scrape and process content from:
- **NARO** (National Agricultural Research Organisation)
- **Ministry of Agriculture Uganda**
- **Agricultural Extension Portal**
- **Uganda Bureau of Statistics**

Extract and organize:
- Post-harvest strategy documents
- Advisory and extension materials
- Project reports (ATAAS, etc.)
- Policy updates
- Best practices
- Research papers
- Videos and training content

## 🏗️ Architecture Overview

```
Streamlit Dashboard (Monitoring & Control)
           ↓
    Prefect Orchestration (Workflows)
           ↓
    ┌──────┴──────┐
    ↓             ↓
Discovery     Processing
Pipeline       Pipeline
    ↓             ↓
    └──────┬──────┘
           ↓
    Storage Layer
    • PostgreSQL (Metadata)
    • MinIO (Documents)
    • Qdrant (Vectors)
```

### Key Features

✅ **Intelligent Discovery**
- LLM-powered URL classification (pre-download)
- Site-specific crawling strategies
- Deduplication via content hashing

✅ **Multi-Format Processing**
- PDF extraction (text + tables)
- HTML content extraction
- Video metadata/transcripts
- OCR for scanned documents

✅ **AI-Powered Classification**
- Content categorization by topic
- Crop and region tagging
- Relevance scoring
- Key practice extraction

✅ **Production-Ready**
- Prefect orchestration
- Retry logic & error handling
- Real-time monitoring dashboard
- Scheduled workflows

✅ **Open-Source Stack**
- Llama 3.1 via Ollama (local inference)
- No API keys required
- Full data control

## 📦 Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Orchestration** | Prefect 2.x | Workflow management, scheduling |
| **LLM** | OpenAI (primary), Ollama (optional) | Content classification, extraction |
| **Embeddings** | OpenAI or sentence-transformers | Semantic search |
| **Database** | PostgreSQL | Metadata, crawl state |
| **Object Storage** | MinIO | Document storage |
| **Vector DB** | Qdrant | Semantic search |
| **Web Scraping** | Playwright, Scrapy | Content discovery |
| **Extraction** | PyMuPDF, Trafilatura | Multi-format parsing |
| **UI** | Streamlit | Dashboard & monitoring |

## 🚀 Quick Start

See **[QUICKSTART.md](QUICKSTART.md)** for detailed setup instructions.

### TL;DR

```bash
# 1. Start infrastructure
docker-compose up -d

# 2. Install dependencies
poetry install

# 3. Initialize database
poetry run python scripts/init_db.py

# 4. Run discovery
poetry run python -c "from src.flows.discovery import discover_content; discover_content('naro')"

# 5. Start dashboard
poetry run streamlit run dashboard/app.py
```

## 📚 Documentation

- **[Architecture Document](postharvest_scraper_architecture.md)** - Detailed system design
- **[Quick Start Guide](QUICKSTART.md)** - Setup and usage instructions
- **API Documentation** - Coming soon
- **Deployment Guide** - Coming soon

## 🎛️ Configuration

### Site Configuration

Edit `src/config/site_configs.py` to:
- Add new sites
- Adjust crawl depth
- Configure URL patterns
- Set rate limits

### Environment Variables

Key settings in `.env`:
```bash
# LLM Provider
LLM_PROVIDER=openai  # or ollama
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o-mini

# Embeddings
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# Crawling
CRAWL_MAX_DEPTH=4
CRAWL_DELAY_SECONDS=2.0

# Processing
RELEVANCE_THRESHOLD=6.0
CHUNK_SIZE=1000
```

## 📊 Monitoring

### Prefect UI
- **URL**: http://localhost:4200
- View workflow runs
- Monitor task execution
- Check error logs

### Streamlit Dashboard
- **URL**: http://localhost:8501
- Real-time metrics
- Document explorer
- Semantic search
- System configuration

### MinIO Console
- **URL**: http://localhost:9001
- Browse stored documents
- Monitor storage usage

## 🔧 Development

### Project Structure

```
postharvest-scraper/
├── src/
│   ├── config/          # Settings & site configs
│   ├── crawlers/        # Web crawling logic
│   ├── extractors/      # Content extraction
│   ├── llm/             # Ollama client
│   ├── storage/         # DB & object storage
│   ├── flows/           # Prefect workflows
│   └── utils/           # Helpers
├── dashboard/           # Streamlit UI
├── scripts/             # Setup & admin scripts
├── tests/               # Unit tests
└── docs/                # Documentation
```

### Running Tests

```bash
poetry run pytest tests/
```

### Code Quality

```bash
# Format code
poetry run black src/

# Lint
poetry run ruff src/

# Type checking
poetry run mypy src/
```

## 🔄 Workflows

### Discovery Pipeline

1. Crawl site (respecting robots.txt)
2. Extract URLs
3. LLM classification (relevance scoring)
4. Store metadata in PostgreSQL

### Processing Pipeline

1. Download document
2. Extract content (PDF/HTML/video)
3. LLM classification (topics, crops, regions)
4. Chunk content
5. Generate embeddings
6. Store in vector database

### Scheduled Runs

- **Daily**: Full site crawl (2 AM)
- **Hourly**: Incremental updates
- **Weekly**: Reprocess failed documents

## 🎯 Use Cases

### 1. RAG Application
```python
from src.storage.vector_db import VectorDB

vector_db = VectorDB()
results = vector_db.search(
    query="best practices for maize storage",
    top_k=5
)
```

### 2. Content API
```python
from src.storage.postgres import PostgresClient

db = PostgresClient()
documents = db.get_documents(
    topics=["storage", "drying"],
    crops=["maize"],
    min_relevance=7.0
)
```

### 3. Export Dataset
```bash
# Export all processed content
poetry run python scripts/export_dataset.py \
    --format jsonl \
    --output postharvest_knowledge.jsonl
```

## 📈 Performance

### Targets

- **Crawl**: 100-200 pages/hour per site
- **Processing**: 50-100 documents/hour
- **LLM Classification**: 100-200 URLs/minute
- **Search Latency**: <500ms

### Scaling

- Add Prefect workers for parallel processing
- Use GPU for faster LLM inference
- Deploy Qdrant cluster for search
- Implement caching for frequently accessed content

## 🐛 Troubleshooting

See [QUICKSTART.md](QUICKSTART.md#troubleshooting) for common issues.

Quick checks:
```bash
# Verify services
docker-compose ps

# Check Ollama
curl http://localhost:11434/api/tags

# Test database
docker exec -it postharvest-postgres psql -U scraper -d postharvest_scraper -c "SELECT COUNT(*) FROM documents;"
```

## 🤝 Contributing

Built by **[Fourlanes](https://fourlanes.tech)** for agricultural knowledge systems in Africa.

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📝 License

[Add your license here]

## 🙏 Acknowledgments

- **NARO** - National Agricultural Research Organisation
- **Ministry of Agriculture, Uganda**
- **Anthropic** - Claude AI assistance in architecture design
- **Ollama** - Local LLM serving
- **Prefect** - Workflow orchestration

## 📧 Contact

**Fourlanes Digital Studio**
- Website: https://fourlanes.tech
- Email: edwinm@fourlanes.tech

---

**Built with ❤️ for sustainable agriculture in Uganda** 🌾
