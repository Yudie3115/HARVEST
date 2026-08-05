"""
PostgreSQL database client
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Union
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from src.config.settings import settings
from src.storage.models import (
    Base, CrawlRun, Document, DocumentClassification,
    ContentChunk, ProcessingQueue, SystemMetric,
    CrawlStatus, DocumentStatus
)


class PostgresClient:
    """PostgreSQL database client"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or str(settings.database_url)
        self.engine = create_engine(
            self.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        logger.info(f"Initialized PostgreSQL client")
    
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Created database tables")
    
    def get_session(self) -> Session:
        """Get a database session"""
        return self.SessionLocal()
    
    # Crawl Run methods
    
    def create_crawl_run(self, site_name: str, config: Dict = None) -> CrawlRun:
        """Create a new crawl run"""
        with self.get_session() as session:
            crawl_run = CrawlRun(
                site_name=site_name,
                status=CrawlStatus.RUNNING,
                config=config
            )
            session.add(crawl_run)
            session.commit()
            session.refresh(crawl_run)
            logger.info(f"Created crawl run {crawl_run.id} for {site_name}")
            return crawl_run
    
    def get_or_create_manual_crawl_run(self) -> CrawlRun:
        """Return the sentinel CrawlRun used for manually uploaded documents.

        Creates it on first call; subsequent calls return the same row.
        """
        with self.get_session() as session:
            existing = session.query(CrawlRun).filter(
                CrawlRun.site_name == "manual"
            ).first()
            if existing:
                session.refresh(existing)
                return existing

            crawl_run = CrawlRun(
                site_name="manual",
                status=CrawlStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
                config={"type": "manual_upload"},
            )
            session.add(crawl_run)
            session.commit()
            session.refresh(crawl_run)
            logger.info(f"Created manual upload crawl run {crawl_run.id}")
            return crawl_run

    def update_crawl_run(
        self,
        crawl_run_id: UUID,
        urls_discovered: int = None,
        documents_processed: int = None,
        status: str = None,
        errors: Dict = None
    ):
        """Update crawl run statistics"""
        with self.get_session() as session:
            crawl_run = session.query(CrawlRun).filter(
                CrawlRun.id == crawl_run_id
            ).first()
            
            if crawl_run:
                if urls_discovered is not None:
                    crawl_run.urls_discovered = urls_discovered
                if documents_processed is not None:
                    crawl_run.documents_processed = documents_processed
                if status is not None:
                    crawl_run.status = CrawlStatus(status)
                if errors is not None:
                    crawl_run.errors = errors
                
                session.commit()
                logger.debug(f"Updated crawl run {crawl_run_id}")
    
    # Document methods
    
    def create_document(
        self,
        url: str,
        site_name: str,
        crawl_run_id: UUID,
        title: str = None,
        document_type: str = None,
        file_hash: str = None,
        metadata: Dict = None
    ) -> Document:
        """Create a new document record"""
        with self.get_session() as session:
            # Check if document already exists
            existing = session.query(Document).filter(
                Document.url == url
            ).first()
            
            if existing:
                logger.debug(f"Document already exists: {url}")
                return existing
            
            document = Document(
                url=url,
                site_name=site_name,
                crawl_run_id=crawl_run_id,
                title=title,
                document_type=document_type,
                file_hash=file_hash,
                status=DocumentStatus.DISCOVERED,
                extra_metadata=metadata or {}
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            logger.debug(f"Created document: {url}")
            return document
    
    def get_document(self, document_id: UUID) -> Optional[Document]:
        """Get a document by ID"""
        with self.get_session() as session:
            return session.query(Document).filter(
                Document.id == document_id
            ).first()

    def get_document_by_url(self, url: str) -> Optional[Document]:
        """Return an existing document with the exact source URL."""
        with self.get_session() as session:
            return session.query(Document).filter(Document.url == url).first()

    def get_document_by_file_hash(self, file_hash: str) -> Optional[Document]:
        """Return an existing document with identical stored source bytes."""
        with self.get_session() as session:
            return (
                session.query(Document)
                .filter(Document.file_hash == file_hash)
                .order_by(Document.discovered_at.asc())
                .first()
            )

    def delete_unprocessed_document(self, document_id: UUID) -> None:
        """Remove a document row created by ingestion before indexing began."""
        with self.get_session() as session:
            session.query(ProcessingQueue).filter(
                ProcessingQueue.document_id == document_id
            ).delete(synchronize_session=False)
            session.query(Document).filter(Document.id == document_id).delete(
                synchronize_session=False
            )
            session.commit()
    
    def get_documents(
        self,
        site_name: str = None,
        status: Union[DocumentStatus, List[DocumentStatus]] = None,
        limit: int = 100
    ) -> List[Document]:
        """Get documents with filters. `status` accepts a single status or a list."""
        with self.get_session() as session:
            query = session.query(Document)

            if site_name:
                query = query.filter(Document.site_name == site_name)
            if status:
                if isinstance(status, (list, tuple, set)):
                    query = query.filter(Document.status.in_(status))
                else:
                    query = query.filter(Document.status == status)

            return query.limit(limit).all()
    
    def update_document_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        error_log: str = None
    ):
        """Update document processing status"""
        with self.get_session() as session:
            document = session.query(Document).filter(
                Document.id == document_id
            ).first()
            
            if document:
                document.status = status
                if error_log:
                    document.error_log = error_log
                session.commit()
    
    def update_document_file_info(
        self,
        document_id: UUID,
        file_path: str,
        file_hash: str,
        file_size_bytes: int,
        mime_type: str,
    ) -> None:
        """Persist MinIO file metadata back to the Document row."""
        with self.get_session() as session:
            doc = session.query(Document).filter(
                Document.id == document_id
            ).first()
            if doc:
                doc.file_path = file_path
                doc.file_hash = file_hash
                doc.file_size_bytes = file_size_bytes
                doc.mime_type = mime_type
                session.commit()
            else:
                logger.warning(f"update_document_file_info: document {document_id} not found, skipping")

    def update_document_metadata(self, document_id: UUID, metadata_updates: Dict) -> None:
        """Shallow-merge keys into a Document's extra_metadata JSON blob.

        Reassigns a new dict so SQLAlchemy detects the change on the JSONB column.
        """
        with self.get_session() as session:
            doc = session.query(Document).filter(
                Document.id == document_id
            ).first()
            if doc:
                doc.extra_metadata = {**(doc.extra_metadata or {}), **metadata_updates}
                session.commit()
            else:
                logger.warning(f"update_document_metadata: document {document_id} not found, skipping")

    # Classification methods
    
    def create_classification(
        self,
        document_id: UUID,
        classification_data: Dict
    ) -> DocumentClassification:
        """Create document classification"""
        with self.get_session() as session:
            classification = DocumentClassification(
                document_id=document_id,
                topics=classification_data.get('topics', []),
                crops=classification_data.get('crops', []),
                regions=classification_data.get('regions', []),
                relevance_score=classification_data.get('relevance_score', 0),
                document_category=classification_data.get('document_type'),
                target_audience=classification_data.get('target_audience', []),
                language=classification_data.get('language', 'en'),
                summary=classification_data.get('summary'),
                key_practices=classification_data.get('key_practices', []),
                actionable=classification_data.get('actionable', False),
                has_data=classification_data.get('has_data', False),
                llm_model=classification_data.get('llm_model', 'gpt-4o-mini'),
                llm_metadata=classification_data.get('llm_metadata', {})
            )
            session.add(classification)
            session.commit()
            session.refresh(classification)
            return classification
    
    # Statistics methods
    
    def get_crawl_stats(self) -> Dict:
        """Get overall crawl statistics"""
        with self.get_session() as session:
            total_docs = session.query(Document).count()
            processed_docs = session.query(Document).filter(
                Document.status == DocumentStatus.PROCESSED
            ).count()
            
            return {
                'total_documents': total_docs,
                'processed_documents': processed_docs,
                'processing_rate': processed_docs / total_docs if total_docs > 0 else 0
            }
    
    def close(self):
        """Close database connection"""
        self.engine.dispose()
        logger.info("Closed PostgreSQL connection")
