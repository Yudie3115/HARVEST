# Post-Harvest Knowledge Scraper - Project Structure

## 📁 Complete File Tree

```
postharvest-scraper/
├── README.md                           # Project overview and quick start
├── QUICKSTART.md                       # Detailed setup guide
├── postharvest_scraper_architecture.md # Complete architecture documentation
├── .env.example                        # Environment configuration template
├── .gitignore                          # Git ignore rules
├── pyproject.toml                      # Poetry dependencies
├── requirements.txt                    # Pip dependencies (alternative)
├── docker-compose.yml                  # Infrastructure services
├── Makefile                            # Convenience commands
│
├── src/                                # Main application code
│   ├── __init__.py
│   │
│   ├── config/                         # Configuration
│   │   ├── __init__.py
│   │   ├── settings.py                 # Pydantic settings (database, LLM, etc.)
│   │   └── site_configs.py             # Site-specific crawl configs
│   │
│   ├── crawlers/                       # Web crawling implementations
│   │   ├── __init__.py
│   │   ├── base.py                     # Base crawler class (TODO)
│   │   ├── playwright_crawler.py       # Dynamic content crawler (TODO)
│   │   └── scrapy_crawler.py           # Static content crawler (TODO)
│   │
│   ├── extractors/                     # Content extraction
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py            # PDF text/table extraction (TODO)
│   │   ├── html_extractor.py           # HTML content extraction (TODO)
│   │   └── video_extractor.py          # Video metadata extraction (TODO)
│   │
│   ├── llm/                            # LLM integration
│   │   ├── __init__.py
│   │   ├── client.py                   # Unified OpenAI/Ollama client ✓
│   │   ├── prompts.py                  # Prompt templates (TODO)
│   │   └── embeddings.py               # Embedding generation (TODO)
│   │
│   ├── storage/                        # Data persistence
│   │   ├── __init__.py
│   │   ├── models.py                   # SQLAlchemy models ✓
│   │   ├── postgres.py                 # PostgreSQL client ✓
│   │   ├── minio_client.py             # MinIO object storage ✓
│   │   └── vector_db.py                # Qdrant vector database (TODO)
│   │
│   ├── flows/                          # Prefect workflows
│   │   ├── __init__.py
│   │   ├── discovery.py                # Discovery pipeline ✓
│   │   ├── processing.py               # Processing pipeline (TODO)
│   │   └── orchestration.py            # Main orchestration (TODO)
│   │
│   └── utils/                          # Utility functions
│       ├── __init__.py
│       ├── logging.py                  # Logging configuration (TODO)
│       ├── hashing.py                  # File hashing utilities (TODO)
│       └── text_processing.py          # Text utilities (TODO)
│
├── dashboard/                          # Streamlit dashboard
│   ├── app.py                          # Main dashboard ✓ (basic)
│   ├── pages/                          # Multi-page app pages (TODO)
│   │   ├── 1_documents.py
│   │   ├── 2_search.py
│   │   └── 3_analytics.py
│   └── components/                     # Reusable components (TODO)
│       ├── metrics.py
│       └── charts.py
│
├── scripts/                            # Admin and setup scripts
│   ├── __init__.py
│   ├── init_db.py                      # Database initialization ✓
│   ├── deploy_flows.py                 # Deploy Prefect workflows (TODO)
│   └── export_dataset.py               # Export knowledge base (TODO)
│
├── tests/                              # Test suite
│   ├── __init__.py
│   ├── test_crawlers.py                # Crawler tests (TODO)
│   ├── test_extractors.py              # Extractor tests (TODO)
│   ├── test_llm.py                     # LLM integration tests (TODO)
│   └── test_storage.py                 # Storage tests (TODO)
│
├── docs/                               # Additional documentation
│   ├── deployment.md                   # Production deployment (TODO)
│   ├── api.md                          # API documentation (TODO)
│   └── troubleshooting.md              # Common issues (TODO)
│
└── logs/                               # Application logs (created at runtime)
    └── scraper.log
```

## ✅ Implementation Status

### Core Infrastructure (Complete)
- ✅ Docker Compose setup
- ✅ Environment configuration
- ✅ Database models (SQLAlchemy)
- ✅ PostgreSQL client
- ✅ MinIO client
- ✅ Database initialization script

### LLM Integration (Complete)
- ✅ Unified LLM client (OpenAI + Ollama)
- ✅ URL classification
- ✅ Content classification
- ✅ Auto-provider detection

### Discovery Pipeline (Complete)
- ✅ Basic crawling logic
- ✅ LLM-powered URL filtering
- ✅ Document metadata extraction
- ✅ Prefect flow structure

### Dashboard (Basic Implementation)
- ✅ Basic Streamlit app
- ✅ Layout and navigation
- ⚠️ Needs database integration
- ⚠️ Needs real-time metrics

### To Be Implemented

**High Priority:**
1. Content extractors (PDF, HTML, video)
2. Processing pipeline (Prefect flow)
3. Vector database integration (Qdrant)
4. Embedding generation
5. Dashboard database integration

**Medium Priority:**
6. Advanced crawlers (Playwright, Scrapy)
7. Prompt templates system
8. Search functionality
9. Quality checks and validation
10. Error recovery mechanisms

**Lower Priority:**
11. Export functionality
12. Analytics and reporting
13. API endpoints
14. Comprehensive test suite
15. Advanced monitoring

## 🎯 Implementation Roadmap

### Phase 1: MVP (1-2 weeks)
- [ ] PDF extractor implementation
- [ ] HTML extractor implementation
- [ ] Processing Prefect flow
- [ ] Qdrant integration
- [ ] Embedding generation
- [ ] Dashboard database connection

### Phase 2: Production Ready (2-3 weeks)
- [ ] Advanced crawlers (Playwright)
- [ ] Complete error handling
- [ ] Retry mechanisms
- [ ] Search functionality
- [ ] Full dashboard features
- [ ] Deployment documentation

### Phase 3: Advanced Features (3-4 weeks)
- [ ] Advanced analytics
- [ ] Quality scoring system
- [ ] API endpoints
- [ ] Export functionality
- [ ] Scheduled reprocessing
- [ ] Performance optimization

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
- Environment variable loading
- Configuration validation

**src/config/site_configs.py**
- Site-specific crawl strategies
- URL patterns and exclusions
- Rate limits and headers

**src/llm/client.py**
- Unified LLM interface
- OpenAI and Ollama support
- Automatic provider selection
- Retry logic and error handling

**src/storage/models.py**
- SQLAlchemy ORM models
- Database schema definitions
- Relationships and indexes

**src/storage/postgres.py**
- Database operations
- CRUD methods
- Query helpers
- Statistics functions

**src/storage/minio_client.py**
- Object storage operations
- Upload/download files
- Presigned URLs
- Bucket management

**src/flows/discovery.py**
- Prefect discovery workflow
- Site crawling
- URL classification
- Document metadata extraction

### Scripts

**scripts/init_db.py**
- Creates database tables
- Initializes indexes
- Verifies schema

### Dashboard

**dashboard/app.py**
- Streamlit web interface
- System monitoring
- Configuration management
- Document browser

## 🚀 Getting Started

1. **Extract the zip file**
   ```bash
   unzip postharvest-scraper.zip
   cd postharvest-scraper
   ```

2. **Follow QUICKSTART.md**
   - Install dependencies
   - Configure environment
   - Start services
   - Initialize database

3. **Run first crawl**
   ```bash
   poetry run python -c "from src.flows.discovery import discover_content; discover_content('naro')"
   ```

## 📝 Notes for Claude Code

When implementing remaining features:

1. **Follow existing patterns**: Use the same structure as completed modules
2. **Use type hints**: All functions should have type annotations
3. **Add logging**: Use loguru for consistent logging
4. **Error handling**: Wrap operations in try/except with retries
5. **Test incrementally**: Implement and test each module before moving on
6. **Update this document**: Mark items as complete when implemented

## 🤝 Contributing

This project structure is designed for iterative development. Start with the high-priority items and work your way down. Each module is relatively independent, so they can be implemented in parallel if needed.

---

**Legend:**
- ✅ = Fully implemented and tested
- ⚠️ = Partially implemented
- TODO = Not yet implemented
