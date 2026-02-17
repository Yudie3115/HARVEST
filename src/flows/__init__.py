"""
Prefect flows
"""
from src.flows.discovery import discover_content, discover_all_sites
from src.flows.processing import process_document, process_documents_batch
from src.flows.orchestration import (
    main_scraper_flow,
    incremental_update_flow,
    reprocess_failed_flow,
)

__all__ = [
    "discover_content",
    "discover_all_sites",
    "process_document",
    "process_documents_batch",
    "main_scraper_flow",
    "incremental_update_flow",
    "reprocess_failed_flow",
]
