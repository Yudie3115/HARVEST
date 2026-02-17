"""
Database models for PostgreSQL
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Text,
    Boolean,
    ForeignKey,
    BigInteger,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum


Base = declarative_base()


class CrawlStatus(str, enum.Enum):
    """Crawl run status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class DocumentStatus(str, enum.Enum):
    """Document processing status"""
    DISCOVERED = "discovered"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CrawlRun(Base):
    """Crawl run tracking"""
    __tablename__ = "crawl_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_name = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(SQLEnum(CrawlStatus), nullable=False, default=CrawlStatus.PENDING)
    
    # Statistics
    urls_discovered = Column(Integer, default=0)
    documents_processed = Column(Integer, default=0)
    documents_failed = Column(Integer, default=0)
    
    # Configuration snapshot
    config = Column(JSONB)
    
    # Error tracking
    errors = Column(JSONB)
    
    # Relationships
    documents = relationship("Document", back_populates="crawl_run")


class Document(Base):
    """Discovered documents"""
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    crawl_run_id = Column(UUID(as_uuid=True), ForeignKey("crawl_runs.id"), index=True)
    
    # Source information
    url = Column(Text, unique=True, nullable=False, index=True)
    site_name = Column(String(100), nullable=False, index=True)
    
    # Timestamps
    discovered_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime, index=True)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Document metadata
    title = Column(Text)
    document_type = Column(String(50))
    
    # File information
    file_hash = Column(String(64), index=True)  # SHA256
    file_path = Column(Text)  # MinIO path
    file_size_bytes = Column(BigInteger)
    mime_type = Column(String(100))
    
    # Processing status
    status = Column(
        SQLEnum(DocumentStatus), 
        nullable=False, 
        default=DocumentStatus.DISCOVERED,
        index=True
    )
    
    # Storage for extracted content preview
    content_preview = Column(Text)  # First 500 chars
    
    # Metadata
    extra_metadata = Column("metadata", JSONB)

    # Error tracking
    error_log = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Relationships
    crawl_run = relationship("CrawlRun", back_populates="documents")
    classification = relationship(
        "DocumentClassification", 
        back_populates="document",
        uselist=False
    )
    chunks = relationship("ContentChunk", back_populates="document")


class DocumentClassification(Base):
    """LLM-generated document classifications"""
    __tablename__ = "document_classifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )
    
    # Classification results
    topics = Column(ARRAY(String))  # Post-harvest topics
    crops = Column(ARRAY(String))   # Mentioned crops
    regions = Column(ARRAY(String)) # Geographic regions
    
    relevance_score = Column(Float, index=True)  # 0-10
    document_category = Column(String(100))
    target_audience = Column(ARRAY(String))
    language = Column(String(10), default="en")
    
    # Extracted information
    summary = Column(Text)
    key_practices = Column(JSONB)  # List of practices
    
    # Quality indicators
    actionable = Column(Boolean, default=False)
    has_data = Column(Boolean, default=False)
    has_images = Column(Boolean, default=False)
    
    # LLM metadata
    llm_model = Column(String(50))
    llm_metadata = Column(JSONB)
    
    # Timestamps
    classified_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="classification")


class ContentChunk(Base):
    """Chunked content for vector database"""
    __tablename__ = "content_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Chunk information
    chunk_index = Column(Integer, nullable=False)  # Position in document
    text = Column(Text, nullable=False)
    token_count = Column(Integer)
    
    # Inherited metadata from document
    topics = Column(ARRAY(String))
    crops = Column(ARRAY(String))
    regions = Column(ARRAY(String))
    
    # Vector DB reference
    vector_id = Column(String(100))  # Qdrant point ID
    
    # Chunk metadata
    extra_metadata = Column("metadata", JSONB)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")


class ProcessingQueue(Base):
    """Queue for document processing"""
    __tablename__ = "processing_queue"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id"),
        nullable=False,
        index=True
    )
    
    # Queue management
    priority = Column(Integer, default=5, index=True)  # 1-10, higher = more urgent
    retries = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Timestamps
    added_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    
    # Status
    status = Column(
        SQLEnum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.QUEUED,
        index=True
    )
    
    # Error tracking
    last_error = Column(Text)


class SystemMetric(Base):
    """System performance metrics"""
    __tablename__ = "system_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Metric information
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_unit = Column(String(50))
    
    # Context
    site_name = Column(String(100), index=True)
    component = Column(String(100))  # crawler, processor, llm, etc.
    
    # Additional data
    extra_metadata = Column("metadata", JSONB)

    # Timestamp
    recorded_at = Column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        index=True
    )


# Indexes for common queries
from sqlalchemy import Index

Index('idx_documents_status_site', Document.status, Document.site_name)
Index('idx_documents_discovered_status', Document.discovered_at, Document.status)
Index('idx_classification_relevance', DocumentClassification.relevance_score.desc())
Index('idx_classification_topics', DocumentClassification.topics, postgresql_using='gin')
Index('idx_chunks_document_index', ContentChunk.document_id, ContentChunk.chunk_index)
Index('idx_queue_priority_status', ProcessingQueue.priority.desc(), ProcessingQueue.status)
Index('idx_metrics_name_time', SystemMetric.metric_name, SystemMetric.recorded_at)
