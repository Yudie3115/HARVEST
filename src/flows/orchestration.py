"""
Main orchestration flow – ties together discovery and processing pipelines
"""
from typing import List, Dict, Optional
from loguru import logger
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner

from src.config.settings import settings
from src.storage.postgres import PostgresClient
from src.storage.models import DocumentStatus
from src.storage.vector_db import VectorDBClient
from src.flows.discovery import discover_all_sites, discover_content
from src.flows.processing import process_documents_batch


# ---------------------------------------------------------------------------
# Helper tasks
# ---------------------------------------------------------------------------


@task(name="fetch_pending_documents")
def fetch_pending_documents(
    limit: int = 200,
    site_name: Optional[str] = None,
) -> List[Dict]:
    """
    Fetch documents that are in DISCOVERED or QUEUED status, ready for processing.

    Args:
        limit:     Maximum number of documents to return
        site_name: Filter by site (optional)

    Returns:
        List of dicts with keys: id, url, site_name
    """
    db = PostgresClient()
    docs = db.get_documents(
        site_name=site_name,
        status=DocumentStatus.DISCOVERED,
        limit=limit,
    )
    result = [{"id": str(doc.id), "url": doc.url, "site_name": doc.site_name} for doc in docs]
    logger.info(f"Found {len(result)} documents pending processing")
    return result


@task(name="run_quality_checks")
def run_quality_checks() -> Dict:
    """
    Run basic data-quality checks on the knowledge base.

    Returns:
        Quality report dict
    """
    db = PostgresClient()
    stats = db.get_crawl_stats()

    report = {
        "total_documents": stats.get("total_documents", 0),
        "processed_documents": stats.get("processed_documents", 0),
        "processing_rate": stats.get("processing_rate", 0),
    }

    # Warn if processing rate is low
    rate = report["processing_rate"]
    if report["total_documents"] > 0 and rate < 0.5:
        logger.warning(
            f"Processing rate is low: {rate:.0%} "
            f"({report['processed_documents']}/{report['total_documents']} docs)"
        )
    else:
        logger.info(
            f"Quality check OK: {rate:.0%} processing rate "
            f"({report['processed_documents']}/{report['total_documents']} docs)"
        )

    return report


@task(name="refresh_vector_index")
def refresh_vector_index() -> Dict:
    """
    Retrieve collection statistics from the configured vector DB and log a health summary.

    Returns:
        Collection info dict
    """
    try:
        vector_db = VectorDBClient()
        info = vector_db.get_collection_info()
        logger.info(
            f"Vector index: {info.get('vectors_count', 0)} vectors, "
            f"status={info.get('status', 'unknown')}"
        )
        return info
    except Exception as e:
        logger.error(f"Vector index refresh failed: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# High-level flows
# ---------------------------------------------------------------------------


@flow(
    name="post_harvest_scraper",
    task_runner=ConcurrentTaskRunner(),
    description="Full pipeline: discover → process → quality check",
)
def main_scraper_flow(
    sites: Optional[List[str]] = None,
    max_documents: int = 200,
    run_discovery: bool = True,
    run_processing: bool = True,
) -> Dict:
    """
    Main daily orchestration flow.

    Phases:
    1. Discovery  – crawl all enabled sites in parallel
    2. Processing – download, extract, embed, and store discovered documents
    3. Quality    – run quality checks
    4. Index      – refresh vector index stats

    Args:
        sites:           Sites to process (default: all enabled sites)
        max_documents:   Cap on documents processed per run
        run_discovery:   Whether to run the discovery phase
        run_processing:  Whether to run the processing phase

    Returns:
        Run summary dict
    """
    sites = sites or settings.enabled_sites
    logger.info(
        f"Starting main scraper flow for sites: {sites} "
        f"(discovery={run_discovery}, processing={run_processing})"
    )

    summary: Dict = {
        "sites": sites,
        "discovery": {},
        "processing": {},
        "quality": {},
        "vector_index": {},
    }

    # Phase 1: Discovery
    if run_discovery:
        discovery_results = discover_all_sites()
        summary["discovery"] = {
            "total_urls": sum(r.get("urls_discovered", 0) for r in discovery_results),
            "total_stored": sum(r.get("documents_stored", 0) for r in discovery_results),
            "per_site": {r["site_name"]: r for r in discovery_results},
        }
        logger.info(
            f"Discovery complete: " f"{summary['discovery']['total_stored']} documents stored"
        )

    # Phase 2: Processing
    if run_processing:
        pending = fetch_pending_documents(limit=max_documents)
        if pending:
            processing_results = process_documents_batch(pending)
            processed = sum(1 for r in processing_results if r.get("status") == "processed")
            skipped = sum(1 for r in processing_results if r.get("status") == "skipped")
            failed = sum(1 for r in processing_results if r.get("status") == "failed")
            summary["processing"] = {
                "total_queued": len(pending),
                "total_processed": processed,
                "total_skipped": skipped,
                "total_failed": failed,
            }
        else:
            logger.info("No documents pending processing")
            summary["processing"] = {"total_queued": 0, "total_processed": 0}

    # Phase 3: Quality checks
    summary["quality"] = run_quality_checks()

    # Phase 4: Vector index
    summary["vector_index"] = refresh_vector_index()

    logger.info(f"Main scraper flow complete: {summary}")
    return summary


@flow(
    name="incremental_update",
    description="Lightweight update: discover new content without full reprocessing",
)
def incremental_update_flow(site_name: Optional[str] = None) -> Dict:
    """
    Incremental update for one or all sites – only discovers new URLs and
    processes documents that haven't been processed yet.

    Args:
        site_name: Specific site to update (default: all enabled sites)

    Returns:
        Summary dict
    """
    if site_name:
        sites = [site_name]
    else:
        sites = settings.enabled_sites

    logger.info(f"Incremental update for: {sites}")

    discovery_results = []
    for site in sites:
        result = discover_content(site)
        discovery_results.append(result)

    pending = fetch_pending_documents(limit=50)
    processing_results: List[Dict] = []
    if pending:
        processing_results = process_documents_batch(pending, max_concurrent=3)

    processed = sum(1 for r in processing_results if r.get("status") == "processed")
    return {
        "sites": sites,
        "urls_discovered": sum(r.get("urls_discovered", 0) for r in discovery_results),
        "documents_processed": processed,
    }


@flow(name="reprocess_failed")
def reprocess_failed_flow(limit: int = 50) -> Dict:
    """
    Retry processing for documents that previously failed.

    Args:
        limit: Maximum number of failed documents to retry

    Returns:
        Summary dict
    """
    db = PostgresClient()
    failed_docs = db.get_documents(status=DocumentStatus.FAILED, limit=limit)

    if not failed_docs:
        logger.info("No failed documents to reprocess")
        return {"reprocessed": 0}

    # Reset status to DISCOVERED so the processing flow will pick them up
    for doc in failed_docs:
        doc.retry_count = (doc.retry_count or 0) + 1
        db.update_document_status(doc.id, DocumentStatus.DISCOVERED)

    logger.info(f"Reset {len(failed_docs)} failed documents for reprocessing")

    documents = [
        {"id": str(doc.id), "url": doc.url, "site_name": doc.site_name} for doc in failed_docs
    ]
    results = process_documents_batch(documents)
    processed = sum(1 for r in results if r.get("status") == "processed")

    return {"reprocessed": processed, "total_retried": len(failed_docs)}
