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
from prefect import flow

from src.config.settings import settings
from src.flows.processing import (
    _detect_document_type,
    _log_processing_status,
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
    doc_uuid: Optional[str] = None,
    document_id: Optional[str] = None,
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

    ``document_id``, when given, is the id of a Document row the API already
    created (status QUEUED) before triggering this run. It is excluded from
    the duplicate lookup below so that row isn't mistaken for a pre-existing
    duplicate of itself — without it, every manual upload would find its own
    just-created row and return "duplicate" immediately, leaving it stuck at
    QUEUED forever.

    Returns a dict with keys:
        status          "processed" | "duplicate" | "skipped" | "failed"
        document_id     UUID string of the Document row
        url             The URL or synthetic upload:// URI stored in the DB
        chunks          Number of chunks written (0 if skipped/failed)
        relevance_score Float (present when classification succeeded)
        reason          Machine-readable skip/failure reason (present for non-success outcomes)
    """
    if content is None and url is None:
        raise ValueError("Provide either 'content' + 'filename', or 'url'")
    if content is not None and filename is None:
        raise ValueError("'filename' is required when supplying 'content'")

    db = PostgresClient()

    file_hash = hash_content(content) if content is not None else None
    existing = (
        db.get_document_by_file_hash(file_hash)
        if file_hash
        else db.get_document_by_url(url)
    )
    if existing is not None and str(existing.id) != document_id:
        return {
            "document_id": str(existing.id),
            "url": existing.url,
            "status": "duplicate",
            "chunks": 0,
            "reason": "duplicate_content" if file_hash else "duplicate_url",
            "existing_title": existing.title,
        }

    minio = MinIOClient()

    # Sentinel crawl run — created once, reused forever
    crawl_run = db.get_or_create_manual_crawl_run()

    # Determine the canonical URL for this document
    if url:
        source_url = url
        mime_type = None
        doc_type = None
    else:
        doc_uuid = doc_uuid or str(uuid4())
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
        file_hash=file_hash,
        metadata={"manual_upload": True, **(metadata or {})},
    )
    doc_id = str(doc.id)
    db.update_document_status(UUID(doc_id), DocumentStatus.PROCESSING)

    # --- Acquire raw bytes and a download_result dict ---
    if content is not None:
        ext = Path(filename).suffix or f".{doc_type}"
        object_name = f"{doc_id}{ext}"
        minio.upload_bytes(content, object_name=object_name, content_type=mime_type)

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
            _log_processing_status(
                document_id=doc_id,
                url=source_url,
                status="failed",
                explanation=(
                    "manual ingestion could not download or store the source file; "
                    "no content was indexed"
                ),
            )
            return {
                "document_id": doc_id,
                "url": source_url,
                "status": "failed",
                "chunks": 0,
                "reason": "download_failed",
            }

        existing = db.get_document_by_file_hash(download_result["file_hash"])
        if existing is not None and str(existing.id) != doc_id:
            minio.delete_object(download_result["minio_path"])
            db.delete_unprocessed_document(UUID(doc_id))
            return {
                "document_id": str(existing.id),
                "url": existing.url,
                "status": "duplicate",
                "chunks": 0,
                "reason": "duplicate_content",
                "existing_title": existing.title,
            }

        db.update_document_file_info(
            document_id=UUID(doc_id),
            file_path=download_result["minio_path"],
            file_hash=download_result["file_hash"],
            file_size_bytes=download_result["file_size"],
            mime_type=download_result["mime_type"],
        )
        # download_document() internally sets status=QUEUED on success; reset to PROCESSING.
        db.update_document_status(UUID(doc_id), DocumentStatus.PROCESSING)

    # --- Extract text ---
    text = extract_content(download_result, url=source_url)
    if not text:
        db.update_document_status(
            UUID(doc_id),
            DocumentStatus.SKIPPED,
            error_log="No extractable content",
        )
        _log_processing_status(
            document_id=doc_id,
            url=source_url,
            status="skipped",
            explanation=(
                "manual ingestion found no usable text (content may be empty, too short, "
                "unsupported, or image-only); no chunks were indexed"
            ),
        )
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

    # Mirror the crawl pipeline: stash the classification on the Document's
    # metadata so the admin dashboard (which reads
    # extra_metadata["llm_classification"]) shows relevance for manual uploads too.
    db.update_document_metadata(
        UUID(doc_id),
        {
            "llm_classification": classification,
            "relevance_score": relevance_score,
        },
    )

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
        _log_processing_status(
            document_id=doc_id,
            url=source_url,
            status="skipped",
            explanation=(
                f"relevance score {relevance_score:.1f} is below the configured threshold "
                f"{settings.relevance_threshold}; classification was saved but no chunks "
                "were indexed"
            ),
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
        _log_processing_status(
            document_id=doc_id,
            url=source_url,
            status="failed",
            explanation=(
                f"manual ingestion failed during chunking, embedding, or storage; "
                f"document was not fully indexed: {exc}"
            ),
        )
        return {
            "document_id": doc_id,
            "url": source_url,
            "status": "failed",
            "chunks": 0,
            "reason": "chunk_or_storage_failed",
        }

    summary = {
        "document_id": doc_id,
        "url": source_url,
        "status": "processed",
        "chunks": stored,
        "relevance_score": relevance_score,
    }
    _log_processing_status(
        document_id=doc_id,
        url=source_url,
        status="processed",
        explanation=(
            f"manual ingestion completed successfully; {stored} chunks were stored and "
            f"indexed (relevance_score={relevance_score})"
        ),
    )
    return summary


@flow(name="ingest_manual_upload")
def ingest_manual_upload_flow(
    staging_object: Optional[str] = None,
    filename: Optional[str] = None,
    url: Optional[str] = None,
    title: Optional[str] = None,
    site_name: str = "manual",
    doc_uuid: Optional[str] = None,
    document_id: Optional[str] = None,
) -> dict:
    """
    Worker-side entry point for Admin document ingestion.

    The API used to call ingest_manual_document() directly via
    asyncio.to_thread, which held the whole upload in memory and ran
    extract/classify/chunk/embed inside the web container — twenty
    concurrent uploads were enough to get uvicorn OOM-killed.

    The API now streams the upload to a staging object in MinIO and
    triggers this flow, so the bytes are only ever resident in the worker,
    one document at a time.

    Args:
        staging_object: MinIO object holding the uploaded bytes. Mutually
            exclusive with ``url``.
        filename:       Original filename, required with ``staging_object``.
        url:            Remote document to download instead of an upload.
        title:          Optional title override.
        site_name:      Document source label.
        doc_uuid:       ID the API already used to create the Document row
            (status QUEUED) before triggering this run — reused here so the
            row is updated in place instead of a second one being created.
        document_id:    Id of that same pre-created Document row, so the
            duplicate check doesn't mistake it for an existing duplicate of
            itself (see ingest_manual_document).
    """
    minio = MinIOClient()

    content = minio.get_object(staging_object) if staging_object else None
    try:
        return ingest_manual_document(
            content=content,
            filename=filename,
            url=url,
            title=title,
            site_name=site_name,
            doc_uuid=doc_uuid,
            document_id=document_id,
        )
    finally:
        if staging_object:
            # Best effort — the document is already ingested by this point, so
            # a stranded staging object must not fail the flow run.
            try:
                minio.delete_object(staging_object)
            except Exception as exc:
                logger.warning(
                    f"Could not delete staging object {staging_object}: {exc}"
                )
