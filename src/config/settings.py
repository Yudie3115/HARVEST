"""
Application settings using Pydantic Settings
"""
from typing import Literal
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Database
    database_url: PostgresDsn = Field(
        default="postgresql://scraper:ph_scraper_pass@localhost:5433/postharvest_scraper"
    )
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=0)
    
    # MinIO
    minio_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin123")
    minio_bucket: str = Field(default="postharvest-documents")
    minio_secure: bool = Field(default=False)
    
    # Vector database
    vector_db_provider: Literal["qdrant", "chroma"] = Field(default="qdrant")

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="postharvest_knowledge")

    # ChromaDB
    chroma_path: str = Field(default="./data/chroma")
    chroma_collection: str = Field(default="postharvest_knowledge")
    
    # LLM Provider Configuration
    llm_provider: Literal["openai", "ollama", "groq"] = Field(default="openai")

    # Groq
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    groq_temperature: float = Field(default=0.1)

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_temperature: float = Field(default=0.1)
    openai_max_tokens: int = Field(default=8192)
    
    # Ollama (fallback)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:8b")
    ollama_temperature: float = Field(default=0.1)
    ollama_max_tokens: int = Field(default=8192)
    
    # Embeddings
    embedding_provider: Literal["openai", "local"] = Field(default="openai")
    embedding_model: str = Field(default="text-embedding-3-small")  # OpenAI model
    embedding_model_local: str = Field(default="all-MiniLM-L6-v2")  # Local fallback
    embedding_dimension: int = Field(default=1536)  # For text-embedding-3-small
    embedding_batch_size: int = Field(default=32)
    
    # Prefect
    prefect_api_url: str = Field(default="http://localhost:4200/api")
    prefect_api_key: str = Field(default="")
    
    # Crawling
    crawl_user_agent: str = Field(
        default="PostHarvestBot/1.0 (+https://fourlanes.tech/bot)"
    )
    crawl_delay_seconds: float = Field(default=2.0)
    crawl_max_depth: int = Field(default=4)
    crawl_timeout_seconds: int = Field(default=30)
    crawl_max_retries: int = Field(default=3)
    crawl_unverify_ssl: str = Field(default="")
    
    # Processing
    relevance_threshold: float = Field(default=6.0)
    min_content_length: int = Field(default=100)
    max_content_length: int = Field(default=50000)
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=200)
    
    # Sites
    naro_enabled: bool = Field(default=True)
    agriculture_enabled: bool = Field(default=True)
    extension_enabled: bool = Field(default=True)
    ubos_enabled: bool = Field(default=True)
    aphlis_enabled: bool = Field(default=False)
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    log_file: str = Field(default="logs/scraper.log")
    log_rotation: str = Field(default="10 MB")
    log_retention: str = Field(default="30 days")
    
    # Admin panel
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="changeme")
    admin_jwt_secret: str = Field(default="change-this-secret-in-production")
    access_hash_secret: str = Field(
        default="change-this-access-hash-secret-in-production"
    )
    global_monthly_message_limit: int = Field(default=100000)
    redemption_max_attempts_per_hour: int = Field(default=5)

    # Translation (Sunbird AI)
    sunbird_api_key: str = Field(default="")
    sunbird_api_url: str = Field(default="https://api.sunbird.ai")
    translation_enabled: bool = Field(default=True)
    translation_min_confidence: float = Field(default=0.80)

    # BertScore (answer faithfulness)
    bertscore_enabled: bool = Field(default=True)
    bertscore_model: str = Field(default="distilbert-base-uncased")

    # WhatsApp (Meta Cloud API)
    whatsapp_token: str = Field(default="")
    whatsapp_phone_number_id: str = Field(default="")
    whatsapp_verify_token: str = Field(default="")
    whatsapp_app_secret: str = Field(default="")

    # Chat retrieval
    chat_score_threshold: float = Field(default=0.3)
    # Disabled until Phase 5 score/outcome evidence supports a deployment value.
    chat_min_top_score: float | None = Field(default=None)

    # Q&A catalogue
    catalogue_collection_name: str = Field(default="postharvest_catalogue")
    catalogue_mode: Literal["manual", "auto"] = Field(default="manual")
    catalogue_min_faithfulness: float = Field(default=0.60)
    catalogue_min_score: float = Field(default=0.70)
    catalogue_duplicate_threshold: float = Field(default=0.90)
    catalogue_match_threshold: float = Field(default=0.82)
    catalogue_match_observation_threshold: float = Field(default=0.0)
    catalogue_match_rate_limit: str = Field(default="30/hour")
    catalogue_helpful_rate_limit: str = Field(default="30/hour")
    catalogue_job_max_attempts: int = Field(default=5)
    catalogue_auto_min_reviewed_samples: int = Field(default=50)

    # API
    api_rate_limit_web: int = Field(default=20)       # requests per hour per IP
    api_rate_limit_whatsapp: int = Field(default=30)  # messages per hour per phone
    api_cors_origins: list[str] = Field(default=["*"])

    # Development
    debug: bool = Field(default=False)
    environment: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    
    @property
    def enabled_sites(self) -> list[str]:
        """Return list of enabled sites"""
        sites = []
        if self.naro_enabled:
            sites.append("naro")
        if self.agriculture_enabled:
            sites.append("agriculture")
        if self.extension_enabled:
            sites.append("extension")
        if self.ubos_enabled:
            sites.append("ubos")
        if self.aphlis_enabled:
            sites.append("aphlis")
        return sites

    @property
    def crawl_unverify_ssl_sites(self) -> set[str]:
        """Return site names that should skip SSL verification."""
        return {
            site.strip().lower()
            for site in self.crawl_unverify_ssl.split(",")
            if site.strip()
        }

    def verify_ssl_for_site(self, site_name: str | None) -> bool:
        """Return whether HTTP clients should verify SSL for a site."""
        if not site_name:
            return True
        return site_name.lower() not in self.crawl_unverify_ssl_sites


# Global settings instance
settings = Settings()
