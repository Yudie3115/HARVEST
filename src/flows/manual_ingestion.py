"""
Manual document ingestion — accepts a local file or a URL and runs it
through the full processing pipeline (extract → classify → chunk → embed → store).

The web-crawl discovery step is bypassed; a sentinel CrawlRun(site_name="manual")
is used as the FK anchor for all manually uploaded documents.
"""
import mimetypes
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from loguru import logger

from src.config.settings import settings
from src.flows.processing import (
    _detect_document_type,
    download_document,
    extract_content,
    classify_document_content,
    chunk_and_embed,
    store_chunks,
)
from src.storage.models import DocumentStatus
from src.storage.postgres import PostgresClient
from src.storage.minio_client import MinIOClient
from src.utils.hashing import hash_content


def ingest_manual_document(
    *,
    content: Optional[bytes] = None,
    filename: Optional[str] = None,
    url: Optional[str] = None,
    title: Optional[str] = None,
    site_name: str = "manual",
    metadata: Optional[dict] = None,
) -> dict:
    """
    Ingest a document into the knowledge base without going through web crawling.

    Provide **either**:
    - ``content`` (bytes) + ``filename`` — for a locally uploaded file, or
    - ``url`` — to download and ingest a remote document.

    The full LLM classification pipeline runs, including the relevance gate
    (``settings.relevance_threshold``). Documents that score below the threshold
    are stored with status SKIPPED and their classification is recorded, but no
    chunks are written to the vector database.

    Returns a dict with keys:
        status          "processed" | "skipped" | "failed"
        document_id     UUID string of the Document row
        url             The URL or synthetic upload:// URI stored in the DB
        chunks          Number of chunks written (0 if skipped/failed)
        relevance_score Float (present when classification succeeded)
        reason          "low_relevance" | "no_content" (present when skipped)
    """
    if content is None and url is None:
        raise ValueError("Provide either 'content' + 'filename', or 'url'")
    if content is not None and filename is None:
        raise ValueError("'filename' is required when supplying 'content'")

    db = PostgresClient()
    minio = MinIOClient()

    # Sentinel crawl run — created once, reused forever
    crawl_run = db.get_or_create_manual_crawl_run()

    # Determine the canonical URL for this document
    if url:
        source_url = url
        mime_type = None
        doc_type = None
    else:
        doc_uuid = str(uuid4())
        source_url = f"upload://{doc_uuid}/{filename}"
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"
        doc_type = _detect_document_type(filename, mime_type)

    # Create the DB record (idempotent — returns existing if URL already present)
    doc = db.create_document(
        url=source_url,
        site_name=site_name,
        crawl_run_id=crawl_run.id,
        title=title or filename or url,
        document_type=doc_type,
        metadata={"manual_upload": True, **(metadata or {})},
    )
    doc_id = str(doc.id)
    db.update_document_status(UUID(doc_id), DocumentStatus.PROCESSING)

    # --- Acquire raw bytes and a download_result dict ---
    if content is not None:
        ext = Path(filename).suffix or f".{doc_type}"
        object_name = f"{doc_id}{ext}"
        minio.upload_bytes(content, object_name=object_name, content_type=mime_type)
        file_hash = hash_content(content)

        db.update_document_file_info(
            document_id=UUID(doc_id),
            file_path=object_name,
            file_hash=file_hash,
            file_size_bytes=len(content),
            mime_type=mime_type,
        )

        download_result = {
            "minio_path": object_name,
            "file_hash": file_hash,
            "file_size": len(content),
            "mime_type": mime_type,
            "doc_type": doc_type,
            "content": content,
        }
    else:
        # Delegate download (and MinIO upload) to the existing task function
        download_result = download_document(doc_id, url)
        if not download_result:
            # download_document already set status=FAILED and logged the error
            return {"document_id": doc_id, "url": source_url, "status": "failed", "chunks": 0}

        db.update_document_file_info(
            document_id=UUID(doc_id),
            file_path=download_result["minio_path"],
            file_hash=download_result["file_hash"],
            file_size_bytes=download_result["file_size"],
            mime_type=download_result["mime_type"],
        )
        db.update_document_status(UUID(doc_id), DocumentStatus.PROCESSING)

    # --- Extract text ---
    text = extract_content(download_result, url=source_url)
    if not text:
        db.update_document_status(
            UUID(doc_id),
            DocumentStatus.SKIPPED,
            error_log="No extractable content",
        )
        logger.warning(f"Manual ingestion skipped (no content): {source_url}")
        return {
            "document_id": doc_id,
            "url": source_url,
            "status": "skipped",
            "chunks": 0,
            "reason": "no_content",
        }

    # --- Classify (LLM) ---
    classification = classify_document_content(text, url=source_url)
    relevance_score = classification.get("relevance_score", 0.0)

    # --- Relevance gate ---
    if relevance_score < settings.relevance_threshold:
        db.update_document_status(
            UUID(doc_id),
            DocumentStatus.SKIPPED,
            error_log=(
                f"Relevance score {relevance_score:.1f} below "
                f"threshold {settings.relevance_threshold}"
            ),
        )
        db.create_classification(UUID(doc_id), classification)
        logger.info(
            f"Manual ingestion skipped (relevance {relevance_score:.1f} < "
            f"{settings.relevance_threshold}): {source_url}"
        )
        return {
            "document_id": doc_id,
            "url": source_url,
            "status": "skipped",
            "chunks": 0,
            "reason": "low_relevance",
            "relevance_score": relevance_score,
        }

    db.create_classification(UUID(doc_id), classification)

    # --- Chunk, embed, and store ---
    try:
        chunks = chunk_and_embed(text, doc_id, classification, url=source_url)
        stored = store_chunks(chunks, doc_id, classification)
        db.update_document_status(UUID(doc_id), DocumentStatus.PROCESSED)
    except Exception as exc:
        db.update_document_status(
            UUID(doc_id),
            DocumentStatus.FAILED,
            error_log=str(exc),
        )
        logger.error(f"Manual ingestion failed during chunk/store for {source_url}: {exc}")
        return {
            "document_id": doc_id,
            "url": source_url,
            "status": "failed",
            "chunks": 0,
        }

    summary = {
        "document_id": doc_id,
        "url": source_url,
        "status": "processed",
        "chunks": stored,
        "relevance_score": relevance_score,
    }
    logger.info(f"Manual ingestion complete: {summary}")
    return summary
