# Post-Harvest Knowledge Scraper: Architecture & Implementation

## System Overview

A production-grade web scraping and content processing system designed to build an AI knowledge base for post-harvest practices in Uganda. Uses open-source AI (Llama 3.1 via Ollama) for intelligent content discovery, classification, and extraction.

---

## Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                       │
│  (Monitoring, Config, Manual Triggers, Results Explorer)    │
└───────────────┬─────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────┐
│                   Prefect Orchestration                      │
│  • Scheduled workflows                                       │
│  • Retry logic & error handling                              │
│  • Task dependencies                                         │
└───────────────┬─────────────────────────────────────────────┘
                │
        ┌───────┴───────┐
        │               │
┌───────▼──────┐ ┌─────▼──────────┐
│   Discovery  │ │   Processing   │
│   Pipeline   │ │    Pipeline    │
└───────┬──────┘ └─────┬──────────┘
        │               │
        │               │
┌───────▼───────────────▼──────────────────────────────────────┐
│                   Storage Layer                               │
│  • PostgreSQL (metadata, crawl state)                        │
│  • MinIO/S3 (raw documents, PDFs)                           │
│  • Qdrant/Chroma (vector embeddings)                        │
└───────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Core Infrastructure
- **Python 3.11+**
- **Prefect 2.x** - Workflow orchestration
- **PostgreSQL** - Metadata & crawl state
- **MinIO** (or S3-compatible) - Document storage
- **Qdrant** or **ChromaDB** - Vector database

### Scraping & Extraction
- **Playwright** - Dynamic content & JavaScript rendering
- **Scrapy** - Static content crawling (faster for simple sites)
- **Trafilatura** - HTML content extraction
- **PyMuPDF** - PDF text extraction
- **pdfplumber** - PDF table extraction
- **yt-dlp** - Video metadata/transcript extraction

### AI/LLM Stack
- **OpenAI API** - Primary LLM provider (GPT-4o-mini for cost efficiency, GPT-4o for complex tasks)
- **Ollama** - Fallback/local LLM serving (Llama 3.1 8B/70B) - Optional
- **LangChain** - LLM orchestration & prompting
- **OpenAI Embeddings** - text-embedding-3-small (default) or sentence-transformers (local fallback)

### Monitoring & UI
- **Streamlit** - Dashboard & admin interface
- **Prefect UI** - Workflow monitoring
- **Loguru** - Structured logging

---

## System Architecture Deep Dive

### 1. Discovery Pipeline

**Goal:** Intelligently crawl sites and identify relevant documents

```python
# Prefect Flow Structure
@flow(name="discovery_pipeline")
def discover_content(site_config: SiteConfig):
    """
    Main discovery workflow for a single site
    """
    # 1. Initial crawl
    urls = crawl_site(site_config)
    
    # 2. LLM-powered URL classification
    classified_urls = classify_urls_batch(urls)
    
    # 3. Document metadata extraction
    documents = extract_document_metadata(classified_urls)
    
    # 4. Store in PostgreSQL
    store_discovered_documents(documents)
    
    return documents

@task(retries=3, retry_delay_seconds=60)
def classify_urls_batch(urls: list[str]) -> list[ClassifiedURL]:
    """
    Use Llama 3.1 to classify URLs by relevance
    """
    # Batch URLs to LLM (50 at a time)
    # Prompt: Classify each URL for post-harvest relevance
    # Return: relevance_score, topic_tags, document_type
```

**Key Features:**
- **Smart crawling:** robots.txt compliance, rate limiting
- **LLM classification:** Score URLs before downloading (save bandwidth)
- **Deduplication:** Hash-based document fingerprinting
- **Incremental crawling:** Track processed URLs in PostgreSQL

**Site-Specific Strategies:**

```python
# config/site_configs.py
SITE_CONFIGS = {
    "naro": {
        "url": "https://naro.go.ug/",
        "strategy": "recursive_crawl",
        "max_depth": 4,
        "content_selectors": [
            "//a[contains(@href, 'publication')]",
            "//a[contains(@href, 'research')]",
            "//a[contains(@href, 'pdf')]"
        ],
        "llm_filter": True,
        "keywords": ["post-harvest", "storage", "drying", "pest"]
    },
    "ubos": {
        "url": "https://www.ubos.org/",
        "strategy": "search_focused",
        "search_terms": [
            "annual agricultural survey",
            "crop statistics",
            "post-harvest losses"
        ],
        "document_patterns": [
            r".*Annual.*Agricultural.*Survey.*\.pdf$",
            r".*Crop.*Statistics.*\.pdf$"
        ]
    },
    # ... agriculture.go.ug, extension.agriculture.go.ug
}
```

### 2. Processing Pipeline

**Goal:** Extract, classify, and chunk content for knowledge base

```python
@flow(name="processing_pipeline")
def process_documents(document_batch: list[Document]):
    """
    Process discovered documents into knowledge base format
    """
    for doc in document_batch:
        # 1. Download & store raw document
        raw_path = download_document(doc)
        
        # 2. Extract content based on type
        content = extract_content(doc, raw_path)
        
        # 3. LLM-powered classification & tagging
        metadata = classify_content(content)
        
        # 4. Intelligent chunking
        chunks = chunk_content(content, metadata)
        
        # 5. Generate embeddings
        embeddings = generate_embeddings(chunks)
        
        # 6. Store in vector DB
        store_in_vector_db(chunks, embeddings, metadata)

@task
def extract_content(doc: Document, path: str) -> ExtractedContent:
    """
    Multi-format content extraction
    """
    if doc.type == "pdf":
        text = extract_pdf_text(path)  # PyMuPDF
        tables = extract_pdf_tables(path)  # pdfplumber
        images = extract_pdf_images(path)
        return ExtractedContent(text=text, tables=tables, images=images)
    
    elif doc.type == "html":
        text = extract_html_content(path)  # Trafilatura
        return ExtractedContent(text=text)
    
    elif doc.type == "video":
        metadata = extract_video_metadata(path)  # yt-dlp
        transcript = extract_transcript(path)
        return ExtractedContent(text=transcript, metadata=metadata)

@task
def classify_content(content: ExtractedContent) -> ContentMetadata:
    """
    Use Llama 3.1 for intelligent classification
    """
    prompt = f"""
    Analyze this agricultural extension document and extract:
    
    1. Primary topics (from: post-harvest practices, storage, drying, 
       pest management, contamination, marketing, handling)
    2. Crop types mentioned
    3. Geographic relevance (districts/regions)
    4. Document type (research paper, extension guide, policy, report, etc.)
    5. Key recommendations or best practices
    6. Target audience (farmers, extension workers, researchers)
    7. Relevance score (0-10) for post-harvest knowledge base
    
    Content: {content.text[:4000]}
    
    Return as JSON.
    """
    
    response = ollama_client.generate(
        model="llama3.1:8b",
        prompt=prompt,
        format="json"
    )
    
    return ContentMetadata.parse_raw(response)

@task
def chunk_content(content: ExtractedContent, 
                 metadata: ContentMetadata) -> list[ContentChunk]:
    """
    Semantic chunking with LLM assistance
    """
    # Use LangChain's semantic chunker or custom implementation
    # Aim for 500-1000 token chunks with overlap
    # Preserve document structure (sections, subsections)
    
    chunks = semantic_chunker.split(content.text)
    
    # Enrich each chunk with metadata
    enriched_chunks = []
    for chunk in chunks:
        enriched_chunks.append(ContentChunk(
            text=chunk,
            document_id=content.document_id,
            topics=metadata.topics,
            crops=metadata.crops,
            regions=metadata.regions,
            source_url=content.source_url,
            chunk_metadata={
                "relevance_score": metadata.relevance_score,
                "document_type": metadata.document_type
            }
        ))
    
    return enriched_chunks
```

**Processing Strategies by Content Type:**

| Content Type | Extraction Tool | Special Handling |
|-------------|----------------|------------------|
| PDF Reports | PyMuPDF + pdfplumber | Extract tables separately, OCR for scanned docs |
| HTML Pages | Trafilatura | Remove navigation, ads, preserve semantic structure |
| Videos | yt-dlp | Extract metadata, auto-generated subtitles if available |
| Word Docs | python-docx | Convert to markdown, preserve structure |
| Excel | openpyxl | Extract as structured data, not just text |

### 3. Storage Layer

**PostgreSQL Schema:**

```sql
-- Crawl state tracking
CREATE TABLE crawl_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_name VARCHAR(100) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20),
    urls_discovered INTEGER,
    documents_processed INTEGER,
    errors JSONB
);

-- Discovered documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT UNIQUE NOT NULL,
    site_name VARCHAR(100),
    discovered_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    document_type VARCHAR(50),
    title TEXT,
    file_hash VARCHAR(64),  -- SHA256
    file_path TEXT,  -- MinIO/S3 path
    file_size_bytes BIGINT,
    status VARCHAR(20),
    metadata JSONB,
    error_log TEXT
);

-- Content classification
CREATE TABLE document_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    topics TEXT[],  -- Array of topics
    crops TEXT[],
    regions TEXT[],
    relevance_score DECIMAL(3,2),
    document_category VARCHAR(100),
    target_audience TEXT[],
    classified_at TIMESTAMP DEFAULT NOW(),
    llm_metadata JSONB
);

-- Processing queue
CREATE TABLE processing_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    priority INTEGER DEFAULT 5,
    retries INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT NOW(),
    processing_started_at TIMESTAMP,
    status VARCHAR(20)
);

-- Create indexes
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_site ON documents(site_name);
CREATE INDEX idx_classifications_topics ON document_classifications USING GIN(topics);
CREATE INDEX idx_classifications_relevance ON document_classifications(relevance_score DESC);
```

**Vector Database (Qdrant/ChromaDB):**

```python
# Vector storage structure
{
    "collection_name": "postharvest_knowledge",
    "vector_config": {
        "size": 384,  # for all-MiniLM-L6-v2
        "distance": "Cosine"
    },
    "payload_schema": {
        "chunk_id": "uuid",
        "document_id": "uuid",
        "text": "string",
        "topics": "string[]",
        "crops": "string[]",
        "regions": "string[]",
        "source_url": "string",
        "document_type": "string",
        "relevance_score": "float",
        "created_at": "datetime"
    }
}
```

### 4. Prefect Workflows

**Main Orchestration:**

```python
# flows/main_orchestration.py
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
from datetime import timedelta

@flow(
    name="post_harvest_scraper",
    task_runner=ConcurrentTaskRunner()
)
def main_scraper_flow():
    """
    Main orchestration flow - runs daily
    """
    sites = ["naro", "agriculture", "extension", "ubos"]
    
    # Phase 1: Discovery (parallel)
    discovery_results = []
    for site in sites:
        result = discover_content.submit(site)
        discovery_results.append(result)
    
    # Wait for all discoveries to complete
    documents = []
    for result in discovery_results:
        documents.extend(result.result())
    
    # Phase 2: Processing (batched)
    process_documents_batch(documents)
    
    # Phase 3: Quality check
    run_quality_checks()
    
    # Phase 4: Update vector DB
    refresh_vector_index()

@flow(
    name="incremental_crawl",
    retries=2,
    retry_delay_seconds=300
)
def incremental_crawl_flow(site: str):
    """
    Lightweight incremental crawl - runs hourly
    """
    # Check for new content only
    # Process high-priority documents immediately
    pass

@flow(name="reprocessing_flow")
def reprocess_failed_documents():
    """
    Retry failed extractions - runs weekly
    """
    # Query documents with status='failed'
    # Retry with updated prompts/logic
    pass

# Scheduled deployments
if __name__ == "__main__":
    # Daily full crawl at 2 AM
    main_scraper_flow.serve(
        name="daily-scraper",
        cron="0 2 * * *",
        tags=["production", "scheduled"]
    )
    
    # Hourly incremental checks
    incremental_crawl_flow.serve(
        name="incremental-scraper",
        cron="0 * * * *",
        tags=["production", "incremental"]
    )
```

**Error Handling & Resilience:**

```python
@task(
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # Exponential backoff
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=24)
)
def download_document(url: str) -> str:
    """
    Download with retries and caching
    """
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        
        # Store in MinIO
        file_path = store_raw_document(response.content, url)
        return file_path
        
    except httpx.HTTPError as e:
        logger.error(f"Failed to download {url}: {e}")
        raise  # Prefect will retry
```

### 5. Streamlit Dashboard

**Features:**

```python
# dashboard/app.py
import streamlit as st
import pandas as pd
from db import get_crawl_stats, get_recent_documents

st.set_page_config(page_title="Post-Harvest Scraper Dashboard", layout="wide")

# Sidebar - Configuration
with st.sidebar:
    st.title("🌾 Post-Harvest Scraper")
    
    if st.button("▶️ Run Full Crawl"):
        trigger_prefect_flow("main_scraper_flow")
    
    if st.button("🔄 Incremental Update"):
        trigger_prefect_flow("incremental_crawl_flow")
    
    st.divider()
    
    # Site selection
    selected_sites = st.multiselect(
        "Filter by site:",
        ["naro", "agriculture", "extension", "ubos"],
        default=["naro", "agriculture", "extension", "ubos"]
    )

# Main area - Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview", 
    "📄 Documents", 
    "🔍 Search", 
    "📈 Analytics",
    "⚙️ Config"
])

with tab1:
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    
    stats = get_crawl_stats()
    col1.metric("Total Documents", stats['total_documents'])
    col2.metric("Processed Today", stats['processed_today'])
    col3.metric("Avg Relevance", f"{stats['avg_relevance']:.2f}")
    col4.metric("Storage Used", f"{stats['storage_gb']:.2f} GB")
    
    # Recent activity chart
    st.subheader("Crawl Activity (Last 30 Days)")
    activity_df = get_activity_timeline()
    st.line_chart(activity_df, x='date', y=['discovered', 'processed'])
    
    # Topic distribution
    st.subheader("Document Topics")
    topic_df = get_topic_distribution()
    st.bar_chart(topic_df, x='topic', y='count')

with tab2:
    # Document explorer
    st.subheader("Recent Documents")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    topic_filter = col1.selectbox("Topic", ["All"] + get_all_topics())
    status_filter = col2.selectbox("Status", ["All", "processed", "pending", "failed"])
    sort_by = col3.selectbox("Sort by", ["Relevance", "Date", "Site"])
    
    # Documents table
    docs_df = get_documents(
        sites=selected_sites,
        topic=topic_filter,
        status=status_filter
    )
    
    # Display with actions
    for idx, row in docs_df.iterrows():
        with st.expander(f"{row['title']} ({row['document_type']})"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**URL:** {row['url']}")
                st.write(f"**Topics:** {', '.join(row['topics'])}")
                st.write(f"**Relevance:** {row['relevance_score']}/10")
                st.write(f"**Discovered:** {row['discovered_at']}")
            
            with col2:
                if st.button("📥 Download", key=f"dl_{idx}"):
                    download_document_from_storage(row['id'])
                
                if st.button("🔄 Reprocess", key=f"rp_{idx}"):
                    queue_for_reprocessing(row['id'])

with tab3:
    # Semantic search interface
    st.subheader("🔍 Search Knowledge Base")
    
    query = st.text_input("Search for post-harvest information:")
    
    if query:
        with st.spinner("Searching..."):
            results = semantic_search(query, top_k=10)
        
        st.write(f"Found {len(results)} relevant chunks")
        
        for result in results:
            with st.expander(
                f"[{result['score']:.2f}] {result['document_title']}"
            ):
                st.write(result['text'])
                st.caption(f"Source: {result['source_url']}")
                st.caption(f"Topics: {', '.join(result['topics'])}")

with tab4:
    # Analytics
    st.subheader("📈 System Analytics")
    
    # Coverage by topic
    coverage_df = get_topic_coverage()
    st.plotly_chart(
        create_sunburst_chart(coverage_df),
        use_container_width=True
    )
    
    # Site comparison
    site_stats = get_site_statistics()
    st.dataframe(site_stats)
    
    # Quality metrics
    st.subheader("Quality Metrics")
    quality_df = get_quality_metrics()
    st.metric("Avg Processing Time", f"{quality_df['avg_time']:.2f}s")
    st.metric("Success Rate", f"{quality_df['success_rate']:.1f}%")
    st.metric("Duplicate Rate", f"{quality_df['duplicate_rate']:.1f}%")

with tab5:
    # Configuration
    st.subheader("⚙️ System Configuration")
    
    # LLM settings
    st.write("**LLM Settings (Ollama)**")
    model = st.selectbox("Model", ["llama3.1:8b", "llama3.1:70b"])
    temperature = st.slider("Temperature", 0.0, 1.0, 0.1)
    
    # Crawl settings
    st.write("**Crawl Settings**")
    max_depth = st.number_input("Max Depth", 1, 10, 4)
    rate_limit = st.number_input("Rate Limit (req/s)", 1, 10, 2)
    
    # Relevance threshold
    relevance_threshold = st.slider(
        "Relevance Threshold (process only if above)", 
        0.0, 10.0, 6.0
    )
    
    if st.button("💾 Save Configuration"):
        save_config({
            "llm_model": model,
            "temperature": temperature,
            "max_depth": max_depth,
            "rate_limit": rate_limit,
            "relevance_threshold": relevance_threshold
        })
        st.success("Configuration saved!")
```

### 6. LLM Integration (OpenAI + Ollama Fallback)

**Provider Strategy:**

The system uses a flexible LLM provider architecture:
- **Primary**: OpenAI API (GPT-4o-mini for speed/cost, GPT-4o for complex analysis)
- **Fallback**: Ollama with Llama 3.1 (if OpenAI unavailable or for local development)
- **Auto-detection**: Checks OpenAI API key availability at runtime

**Optimized Prompting:**

```python
# llm/prompts.py
URL_CLASSIFICATION_PROMPT = """
You are a content classifier for an agricultural knowledge base focused on post-harvest practices.

Analyze these URLs and determine their relevance:

URLs:
{urls}

For each URL, return:
- relevance_score (0-10): How relevant to post-harvest topics?
- topics: List of applicable topics (storage, drying, pest_management, contamination, marketing, handling)
- document_type: Type of content (research_paper, extension_guide, policy_doc, report, news, video)
- priority: Processing priority (high/medium/low)

Relevant indicators:
- Keywords: post-harvest, storage, drying, pest, loss, handling, preservation
- Government extension sites, research publications, ATAAS reports
- Agricultural surveys, policy documents

Return as JSON array.
"""

CONTENT_CLASSIFICATION_PROMPT = """
Analyze this agricultural document excerpt and extract structured metadata.

Document: {content}

Extract:
1. primary_topics: Main topics from [post-harvest practices, storage, drying, pest management, 
   contamination, marketing, handling, quality control, value addition]
2. crops_mentioned: Specific crops (maize, beans, coffee, etc.)
3. regions: Geographic areas (districts or regions in Uganda)
4. document_type: Category (research paper, extension guide, policy, training material, etc.)
5. key_practices: List of specific best practices or recommendations
6. target_audience: Who should read this (farmers, extension workers, researchers, traders)
7. language: Primary language (English, Luganda, etc.)
8. relevance_score: Rate 0-10 for post-harvest knowledge base
9. summary: 2-sentence summary
10. actionable: Boolean - contains practical, actionable advice?

Return as JSON.
"""

# llm/client.py
import ollama
from typing import List, Dict
import json

class OllamaClient:
    def __init__(self, model: str = "llama3.1:8b", host: str = "http://localhost:11434"):
        self.model = model
        self.client = ollama.Client(host=host)
    
    def classify_urls(self, urls: List[str]) -> List[Dict]:
        """
        Batch classify URLs for relevance
        """
        # Process in batches of 50
        results = []
        for i in range(0, len(urls), 50):
            batch = urls[i:i+50]
            prompt = URL_CLASSIFICATION_PROMPT.format(
                urls="\n".join(batch)
            )
            
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                format="json",
                options={
                    "temperature": 0.1,  # Low temp for classification
                    "num_predict": 2048
                }
            )
            
            batch_results = json.loads(response['response'])
            results.extend(batch_results)
        
        return results
    
    def classify_content(self, content: str, max_length: int = 4000) -> Dict:
        """
        Classify document content
        """
        # Truncate if too long
        truncated_content = content[:max_length]
        
        prompt = CONTENT_CLASSIFICATION_PROMPT.format(
            content=truncated_content
        )
        
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            format="json",
            options={"temperature": 0.2}
        )
        
        return json.loads(response['response'])
    
    def extract_key_info(self, text: str, query: str) -> str:
        """
        Extract specific information from text
        """
        prompt = f"""
        From this agricultural document, answer the following question:
        
        Question: {query}
        
        Document: {text[:3000]}
        
        Provide a concise, factual answer based only on the document.
        """
        
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            options={"temperature": 0.3}
        )
        
        return response['response']
```

**Model Selection Strategy:**

**OpenAI Models (Primary):**
- **gpt-4o-mini** - Default for most tasks (classification, extraction)
  - Fast inference
  - Cost-effective (~$0.15 per 1M input tokens)
  - Good accuracy for structured tasks
  - No local resources required

- **gpt-4o** - For complex analysis (when needed)
  - Deep content understanding
  - Better at nuance and context
  - Use for difficult classification cases
  - Higher cost (~$2.50 per 1M input tokens)

**Ollama Models (Fallback/Local Development):**
- **llama3.1:8b** - Local development
  - Fast inference (~200 tokens/sec on decent GPU)
  - Good accuracy for structured tasks
  - Requires 8GB VRAM or runs on CPU

- **llama3.1:70b** - Local advanced analysis
  - Deep content understanding
  - Requires significant resources (80GB+ RAM or multi-GPU)

**Embedding Strategy:**

```python
# Primary: OpenAI embeddings
from openai import OpenAI

client = OpenAI()
response = client.embeddings.create(
    model="text-embedding-3-small",  # 1536 dimensions, $0.02 per 1M tokens
    input=["Your text here"]
)
embeddings = response.data[0].embedding

# Fallback: Local embeddings with sentence-transformers
from sentence_transformers import SentenceTransformer

# Option 1: Lightweight, fast
embedder = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dimensions

# Option 2: Better quality (if resources allow)
embedder = SentenceTransformer('all-mpnet-base-v2')  # 768 dimensions
```

---

## Project Structure

```
postharvest-scraper/
├── pyproject.toml              # Poetry dependencies
├── README.md
├── .env.example
├── docker-compose.yml          # PostgreSQL, MinIO, Qdrant (Ollama optional)
│
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py         # Pydantic settings
│   │   └── site_configs.py     # Site-specific crawl configs
│   │
│   ├── crawlers/
│   │   ├── __init__.py
│   │   ├── base.py             # Base crawler class
│   │   ├── playwright_crawler.py
│   │   ├── scrapy_crawler.py
│   │   └── sitemap_crawler.py
│   │
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py   # PyMuPDF + pdfplumber
│   │   ├── html_extractor.py  # Trafilatura
│   │   ├── video_extractor.py # yt-dlp
│   │   └── table_extractor.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py           # Unified LLM client (OpenAI + Ollama)
│   │   ├── prompts.py          # Prompt templates
│   │   └── embeddings.py       # Embedding generation
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── postgres.py         # SQLAlchemy models
│   │   ├── minio_client.py     # Object storage
│   │   └── vector_db.py        # Qdrant/ChromaDB
│   │
│   ├── flows/
│   │   ├── __init__.py
│   │   ├── discovery.py        # Discovery Prefect flows
│   │   ├── processing.py       # Processing Prefect flows
│   │   └── orchestration.py    # Main orchestration
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       ├── hashing.py
│       └── text_processing.py
│
├── dashboard/
│   ├── app.py                  # Main Streamlit app
│   ├── pages/
│   │   ├── 1_documents.py
│   │   ├── 2_search.py
│   │   ├── 3_analytics.py
│   │   └── 4_config.py
│   └── components/
│       ├── metrics.py
│       └── charts.py
│
├── scripts/
│   ├── init_db.py              # Database setup
│   ├── seed_data.py            # Test data
│   └── deploy_flows.py         # Deploy Prefect workflows
│
├── tests/
│   ├── test_crawlers.py
│   ├── test_extractors.py
│   └── test_llm.py
│
└── docs/
    ├── deployment.md
    ├── api.md
    └── troubleshooting.md
```

---

## Dependencies

```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.11"

# Orchestration
prefect = "^2.14"
prefect-dask = "^0.2"  # Optional: parallel processing

# Web scraping
playwright = "^1.40"
scrapy = "^2.11"
httpx = "^0.25"
beautifulsoup4 = "^4.12"

# Content extraction
trafilatura = "^1.6"
PyMuPDF = "^1.23"
pdfplumber = "^0.10"
python-docx = "^1.1"
openpyxl = "^3.1"
yt-dlp = "^2023.12"

# LLM & AI
ollama = "^0.1"
langchain = "^0.1"
sentence-transformers = "^2.2"

# Storage
psycopg2-binary = "^2.9"
sqlalchemy = "^2.0"
alembic = "^1.13"  # Migrations
minio = "^7.2"
qdrant-client = "^1.7"  # or chromadb

# UI
streamlit = "^1.29"
plotly = "^5.18"

# Utils
pydantic = "^2.5"
pydantic-settings = "^2.1"
loguru = "^0.7"
python-dotenv = "^1.0"
tenacity = "^8.2"  # Retry logic
```

---

## Deployment & Operations

### Local Development

```bash
# 1. Start infrastructure
docker-compose up -d

# 2. Install dependencies
poetry install

# 3. Initialize database
poetry run python scripts/init_db.py

# 4. Start Prefect server
poetry run prefect server start

# 5. Deploy flows
poetry run python scripts/deploy_flows.py

# 6. Start Streamlit dashboard
poetry run streamlit run dashboard/app.py
```

### Docker Compose Services

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: postharvest_scraper
      POSTGRES_USER: scraper
      POSTGRES_PASSWORD: changeme
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
  
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
  
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    # Pull model on startup
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        ollama serve &
        sleep 5
        ollama pull llama3.1:8b
        wait

volumes:
  postgres_data:
  minio_data:
  qdrant_data:
  ollama_data:
```

### Production Considerations

1. **Scaling:**
   - Use Prefect Cloud or self-hosted Prefect Server
   - Deploy workers on separate machines
   - Use Dask for parallel processing
   - Consider GPU instance for Ollama (NVIDIA A10/T4)

2. **Monitoring:**
   - Prefect UI for workflow monitoring
   - Loguru → structured logs → ELK stack
   - Sentry for error tracking
   - Custom Streamlit dashboard metrics

3. **Cost Optimization:**
   - Use MinIO on object storage (cheap)
   - Incremental crawls to minimize bandwidth
   - Cache LLM responses (PostgreSQL)
   - Compress stored documents

4. **Data Quality:**
   - Implement quality checks (Prefect tasks)
   - Manual review queue for low-confidence items
   - Feedback loop from end users
   - Regular re-classification with improved prompts

---

## Next Steps

1. **Phase 1:** Core infrastructure setup
   - Docker compose environment
   - Basic crawlers for each site
   - PostgreSQL schema implementation

2. **Phase 2:** LLM integration
   - Ollama setup with Llama 3.1
   - URL classification pipeline
   - Content extraction & classification

3. **Phase 3:** Storage & indexing
   - Vector database setup
   - Embedding generation
   - Search implementation

4. **Phase 4:** Dashboard & monitoring
   - Streamlit interface
   - Prefect workflow deployment
   - Alerting & error handling

5. **Phase 5:** Production hardening
   - Load testing
   - Error recovery
   - Documentation
   - Deployment automation

---

## Estimated Resource Requirements

### Development Environment
- **CPU:** 8 cores
- **RAM:** 16GB
- **Storage:** 100GB SSD
- **GPU:** Optional (faster LLM inference)

### Production Environment
- **Application Server:** 16 cores, 32GB RAM
- **Database:** 8 cores, 16GB RAM, 500GB SSD
- **Object Storage:** 1TB+ (expandable)
- **GPU Server (Ollama):** NVIDIA T4/A10, 16GB VRAM

### Estimated Costs (Cloud)
- **Compute:** $200-400/month
- **Storage:** $50-100/month
- **Data transfer:** $20-50/month
- **Total:** ~$300-550/month

---

## Performance Targets

- **Crawl speed:** 100-200 pages/hour per site
- **Processing:** 50-100 documents/hour
- **LLM classification:** 100-200 URLs/minute
- **Search latency:** <500ms for semantic search
- **Dashboard load time:** <2 seconds

---

## Success Metrics

1. **Coverage:** % of relevant documents discovered
2. **Quality:** Average relevance score of processed docs
3. **Freshness:** Time lag between publication and ingestion
4. **Completeness:** % of discovered docs successfully processed
5. **Search quality:** User feedback on search results

