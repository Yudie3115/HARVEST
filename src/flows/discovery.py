"""
Discovery flow - Intelligently crawl sites and identify relevant documents
"""
from datetime import timedelta
from typing import List, Dict
from uuid import UUID

from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
from loguru import logger
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import hashlib
import time

from src.config.settings import settings
from src.config.site_configs import get_site_config, SiteConfig
from src.llm.client import LLMClient
from src.storage.postgres import PostgresClient


@task(
    name="crawl_site",
    retries=2,
    retry_delay_seconds=30,
    # cache_key_fn=lambda context, params: f"crawl_{params['site_name']}",
    # cache_expiration=timedelta(hours=6)
)
def crawl_site(site_name: str, max_urls: int = 1000) -> List[str]:
    """
    Crawl a site and discover URLs
    
    Args:
        site_name: Name of the site to crawl
        max_urls: Maximum number of URLs to discover
        
    Returns:
        List of discovered URLs
    """
    config = get_site_config(site_name)
    logger.info(f"Starting crawl of {config.name} ({config.url})")
    
    discovered_urls = set()
    to_visit = [str(config.url)]
    visited = set()
    
    headers = {
        "User-Agent": settings.crawl_user_agent,
        **config.headers
    }
    
    client = httpx.Client(
        headers=headers,
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
        verify=settings.verify_ssl_for_site(site_name),
    )
    
    depth = 0
    while to_visit and len(discovered_urls) < max_urls and depth < config.max_depth:
        current_batch = to_visit[:20]  # Process 20 at a time
        to_visit = to_visit[20:]
        
        for url in current_batch:
            if url in visited:
                continue
            
            try:
                logger.debug(f"Fetching: {url}")
                response = client.get(url)
                response.raise_for_status()
                visited.add(url)
                time.sleep(config.rate_limit)
                
                # Parse HTML and extract links
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    absolute_url = urljoin(url, link['href'])
                    
                    # Filter based on patterns
                    if _should_follow_url(absolute_url, config):
                        if absolute_url not in discovered_urls and absolute_url not in visited:
                            discovered_urls.add(absolute_url)
                            
                            # Add to visit queue if not too deep
                            if depth < config.max_depth - 1:
                                to_visit.append(absolute_url)
                
            except Exception as e:
                logger.warning(f"Error crawling {url}: {e}")
                continue
        
        depth += 1
    
    logger.info(f"Crawl complete: {len(discovered_urls)} URLs discovered from {config.name}")
    return list(discovered_urls)


@task(
    name="classify_urls",
    retries=1,
    retry_delay_seconds=60
)
def classify_urls_batch(urls: List[str]) -> List[Dict]:
    """
    Use LLM to classify URLs by relevance
    
    Args:
        urls: List of URLs to classify
        
    Returns:
        List of classified URLs with metadata
    """
    logger.info(f"Classifying {len(urls)} URLs with LLM")
    
    llm_client = LLMClient()
    classifications = llm_client.classify_urls(urls)
    
    # Filter by relevance threshold
    filtered = [
        c for c in classifications
        if c.get('relevance_score', 0) >= settings.relevance_threshold
    ]
    
    logger.info(
        f"Filtered {len(filtered)} relevant URLs "
        f"(threshold: {settings.relevance_threshold})"
    )
    
    return filtered


@task(name="extract_document_metadata")
def extract_document_metadata(classified_urls: List[Dict]) -> List[Dict]:
    """
    Extract basic metadata from classified URLs
    
    Args:
        classified_urls: URLs with LLM classifications
        
    Returns:
        Document metadata dictionaries
    """
    documents = []
    
    for item in classified_urls:
        url = item['url']
        
        # Generate file hash from URL (will be updated when downloaded)
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        
        doc = {
            'url': url,
            'title': _extract_title_from_url(url),
            'document_type': item.get('document_type', 'unknown'),
            'file_hash': url_hash,
            'metadata': {
                'llm_classification': item,
                'topics': item.get('topics', []),
                'priority': item.get('priority', 'medium'),
                'relevance_score': item.get('relevance_score', 0)
            }
        }
        
        documents.append(doc)
    
    logger.info(f"Extracted metadata for {len(documents)} documents")
    return documents


@task(name="store_discovered_documents")
def store_discovered_documents(
    documents: List[Dict],
    site_name: str,
    crawl_run_id: UUID
) -> int:
    """
    Store discovered documents in PostgreSQL
    
    Args:
        documents: Document metadata dictionaries
        site_name: Name of the crawled site
        crawl_run_id: ID of the crawl run
        
    Returns:
        Number of documents stored
    """
    db = PostgresClient()
    
    stored_count = 0
    for doc in documents:
        try:
            db.create_document(
                url=doc['url'],
                site_name=site_name,
                crawl_run_id=crawl_run_id,
                title=doc.get('title'),
                document_type=doc.get('document_type'),
                file_hash=doc.get('file_hash'),
                metadata=doc.get('metadata', {})
            )
            stored_count += 1
        except Exception as e:
            logger.warning(f"Failed to store document {doc['url']}: {e}")
    
    logger.info(f"Stored {stored_count} documents in database")
    return stored_count


@flow(
    name="discover_content",
    task_runner=ConcurrentTaskRunner(),
    retries=1,
    retry_delay_seconds=300
)
def discover_content(site_name: str) -> Dict:
    """
    Main discovery workflow for a single site
    
    Args:
        site_name: Name of the site to crawl
        
    Returns:
        Summary statistics
    """
    logger.info(f"Starting discovery flow for {site_name}")
    
    # Initialize database client
    db = PostgresClient()
    
    # Create crawl run
    crawl_run = db.create_crawl_run(site_name=site_name)
    crawl_run_id = crawl_run.id
    
    try:
        # Phase 1: Crawl site
        urls = crawl_site(site_name)
        
        # Phase 2: LLM classification (only if configured)
        config = get_site_config(site_name)
        if config.llm_filter:
            classified_urls = classify_urls_batch(urls)
        else:
            # Skip LLM, use all URLs
            classified_urls = [{'url': url, 'relevance_score': 7.0} for url in urls]
        
        # Phase 3: Extract metadata
        documents = extract_document_metadata(classified_urls)
        
        # Phase 4: Store in database
        stored_count = store_discovered_documents(
            documents,
            site_name,
            crawl_run_id
        )
        
        # Update crawl run
        db.update_crawl_run(
            crawl_run_id,
            urls_discovered=len(urls),
            documents_processed=stored_count,
            status="completed"
        )
        
        summary = {
            'site_name': site_name,
            'crawl_run_id': str(crawl_run_id),
            'urls_discovered': len(urls),
            'urls_classified': len(classified_urls),
            'documents_stored': stored_count,
            'status': 'completed'
        }
        
        logger.info(f"Discovery complete: {summary}")
        return summary
        
    except Exception as e:
        logger.error(f"Discovery flow failed for {site_name}: {e}")
        
        # Mark crawl run as failed
        db.update_crawl_run(
            crawl_run_id,
            status="failed",
            errors={'error': str(e)}
        )
        
        raise


@flow(name="discover_all_sites")
def discover_all_sites() -> List[Dict]:
    """
    Run discovery for all enabled sites.

    Sites are processed sequentially. In Prefect 2.x, subflows (other @flow
    functions) cannot be submitted with .submit() – that API is task-only.
    For parallel site crawls deploy each flow run separately via the Prefect
    work pool and start multiple workers.

    Returns:
        List of summary statistics for each site
    """
    enabled_sites = settings.enabled_sites
    logger.info(f"Starting discovery for {len(enabled_sites)} sites")

    results = []
    for site in enabled_sites:
        try:
            result = discover_content(site)
            results.append(result)
        except Exception as e:
            logger.error(f"Discovery failed for {site}: {e}")
            results.append({
                "site_name": site,
                "status": "failed",
                "urls_discovered": 0,
                "documents_stored": 0,
            })

    total_docs = sum(r.get("documents_stored", 0) for r in results)
    logger.info(f"All discoveries complete. Total documents: {total_docs}")

    return results


# Helper functions

def _should_follow_url(url: str, config: SiteConfig) -> bool:
    """Check if URL matches site configuration patterns"""
    import re
    
    # Must be same domain
    base_domain = urlparse(str(config.url)).netloc
    url_domain = urlparse(url).netloc
    if url_domain != base_domain:
        return False
    
    # Check exclude patterns
    for pattern in config.exclude_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False
    
    # Check include patterns (if any)
    if config.url_patterns:
        for pattern in config.url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    return True


def _extract_title_from_url(url: str) -> str:
    """Extract a readable title from URL"""
    path = urlparse(url).path
    # Get last segment, remove extension, clean up
    segments = [s for s in path.split('/') if s]
    if segments:
        title = segments[-1].replace('-', ' ').replace('_', ' ')
        title = title.split('.')[0]  # Remove extension
        return title.title()
    return "Untitled"


if __name__ == "__main__":
    # For testing
    discover_content("naro")
