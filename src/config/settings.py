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
    
    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="postharvest_knowledge")
    
    # LLM Provider Configuration
    llm_provider: Literal["openai", "ollama"] = Field(default="openai")
    
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
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    log_file: str = Field(default="logs/scraper.log")
    log_rotation: str = Field(default="10 MB")
    log_retention: str = Field(default="30 days")
    
    # Streamlit
    streamlit_server_port: int = Field(default=8501)
    streamlit_server_address: str = Field(default="0.0.0.0")

    # Translation (Sunbird AI)
    sunbird_api_key: str = Field(default="")
    sunbird_api_url: str = Field(default="https://api.sunbird.ai")
    translation_enabled: bool = Field(default=True)
    translation_min_confidence: float = Field(default=0.80)

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
        return sites


# Global settings instance
settings = Settings()
