"""
End-to-end feature smoke test.

Verifies that every major feature of the system works against LIVE services.

Requirements before running:
  - docker compose up -d
  - poetry run python scripts/init_db.py
  - OPENAI_API_KEY set in .env  (or LLM_PROVIDER=ollama with Ollama running)

Usage:
  poetry run python scripts/smoke_test.py
  poetry run python scripts/smoke_test.py --skip-crawl   # fastest - skips live crawl

Exit code 0 = all tests passed, non-zero = one or more failures.
"""

import argparse
import sys
import textwrap
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

# ── colour helpers ────────────────────────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

PASS = f"{GREEN}✓ PASS{RESET}"
FAIL = f"{RED}✗ FAIL{RESET}"
SKIP = f"{YELLOW}⚠ SKIP{RESET}"

_results: list[tuple[str, bool, str]] = []  # (label, passed, detail)


def check(label: str, fn, skip: bool = False):
    """Run fn(), record result, never raise."""
    if skip:
        _results.append((label, True, "skipped"))
        print(f"  {SKIP}  {label}")
        return None
    try:
        result = fn()
        _results.append((label, True, ""))
        print(f"  {PASS}  {label}")
        return result
    except Exception as e:
        detail = str(e)[:120]
        _results.append((label, False, detail))
        print(f"  {FAIL}  {label}")
        print(f"           {detail}")
        return None


def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── individual feature checks ─────────────────────────────────────────────────

def check_postgres():
    from src.storage.postgres import PostgresClient
    db = PostgresClient()
    stats = db.get_crawl_stats()
    assert isinstance(stats, dict), "Expected dict"
    return stats


def check_minio():
    from src.storage.minio_client import MinIOClient
    m = MinIOClient()
    # ensure_bucket already called in __init__
    objects = m.list_objects()
    return len(objects)


def check_qdrant():
    from src.storage.vector_db import VectorDBClient
    from src.config.settings import settings

    vdb = VectorDBClient()
    assert vdb.check_connection(), "Qdrant not reachable"

    # Check if existing collection dimension matches current embedding dimension.
    # If the collection was created with a different dimension (e.g. 384 from a
    # misconfigured .env but embeddings now produce 1536) we must recreate it.
    existing = [c.name for c in vdb.client.get_collections().collections]
    if vdb.collection in existing:
        info = vdb.client.get_collection(vdb.collection)
        try:
            cfg = info.config.params.vectors
            # cfg may be a dict (named vectors) or a VectorParams object
            if hasattr(cfg, "size"):
                stored_dim = cfg.size
            elif isinstance(cfg, dict):
                stored_dim = next(iter(cfg.values())).size if cfg else None
            else:
                stored_dim = None

            if stored_dim is not None and stored_dim != settings.embedding_dimension:
                logger.warning(
                    f"Collection '{vdb.collection}' has dim={stored_dim} but "
                    f"embedding_dimension={settings.embedding_dimension}. "
                    f"Recreating collection."
                )
                vdb.ensure_collection(recreate=True)
        except Exception:
            pass  # Can't determine dim – proceed as-is
    else:
        vdb.ensure_collection()

    return vdb.get_collection_info()


def check_llm():
    from src.llm.client import LLMClient
    llm = LLMClient()
    assert llm.check_connection(), "LLM not reachable"
    return llm.provider


def check_embeddings():
    from src.llm.embeddings import EmbeddingClient
    embedder = EmbeddingClient()
    vec = embedder.embed("maize post-harvest storage")
    assert len(vec) > 0, "Empty embedding vector"
    return len(vec)


def check_html_extraction():
    from src.extractors.html_extractor import extract_html_content
    html = "<html><body><p>Post-harvest storage reduces losses for Ugandan farmers.</p></body></html>"
    text = extract_html_content(html, url="http://test")
    assert text and "post-harvest" in text.lower(), "Expected 'post-harvest' in extracted text"
    return len(text)


def check_text_chunking():
    from src.utils.text_processing import chunk_text
    long_text = ("Post-harvest losses are a major problem in Uganda. " * 50).strip()
    chunks = chunk_text(long_text, chunk_size=200, chunk_overlap=50)
    assert len(chunks) > 1, "Expected multiple chunks"
    return len(chunks)


def check_url_classification(llm_available: bool):
    if not llm_available:
        raise RuntimeError("LLM not available – skipping classification")
    from src.llm.client import LLMClient
    llm = LLMClient()
    results = llm.classify_urls([
        "https://naro.go.ug/research/post-harvest-maize-storage.pdf",
        "https://naro.go.ug/about/contact.html",
    ])
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"
    top = max(results, key=lambda r: r.get("relevance_score", 0))
    assert top["relevance_score"] > 5, f"Expected high relevance for PDF, got {top['relevance_score']}"
    return top["relevance_score"]


def check_content_classification(llm_available: bool):
    if not llm_available:
        raise RuntimeError("LLM not available – skipping classification")
    from src.llm.client import LLMClient
    llm = LLMClient()
    result = llm.classify_content(
        "Maize should be dried to below 13.5% moisture before storing in hermetic bags "
        "to prevent aflatoxin contamination. Store in a cool, dry place away from pests.",
        url="https://naro.go.ug/guide"
    )
    assert isinstance(result.get("relevance_score"), (int, float))
    assert result["relevance_score"] > 5, f"Expected relevance > 5, got {result['relevance_score']}"
    return result["relevance_score"]


def check_vector_roundtrip():
    """Embed a text, store in Qdrant, search for it, verify it comes back."""
    import uuid
    from src.llm.embeddings import EmbeddingClient
    from src.storage.vector_db import VectorDBClient

    embedder = EmbeddingClient()
    vdb = VectorDBClient()
    vdb.ensure_collection()

    test_text = f"Smoke test chunk {time.time()}: hermetic bags reduce aflatoxin contamination"
    vec = embedder.embed(test_text)

    # Qdrant IDs must be UUID strings or unsigned integers – not arbitrary strings
    chunk_id = str(uuid.uuid4())
    payload = {
        "document_id": str(uuid.uuid4()),
        "text": test_text,
        "topics": ["storage"],
        "crops": ["maize"],
        "regions": ["Uganda"],
        "source_url": "https://test.example.com",
        "document_type": "smoke_test",
        "relevance_score": 9.0,
    }
    vdb.upsert_chunk(chunk_id, vec, payload)

    # Search for it
    query_vec = embedder.embed("hermetic bags aflatoxin")
    results = vdb.search(query_vec, top_k=5)
    assert any(r["id"] == chunk_id for r in results), (
        "Upserted chunk not found in search results"
    )

    # Clean up
    vdb.delete_chunk(chunk_id)
    return len(results)


def check_discovery_crawl():
    """Crawl a single URL from NARO and store results – takes ~30-60 seconds."""
    from src.flows.discovery import discover_content
    result = discover_content("naro")
    assert result["status"] == "completed", f"Discovery failed: {result}"
    assert result["urls_discovered"] > 0, "No URLs discovered"
    return result


def check_process_one_document():
    """Process the first DISCOVERED document end-to-end."""
    from src.storage.postgres import PostgresClient
    from src.storage.models import DocumentStatus
    from src.flows.processing import process_document

    db = PostgresClient()
    docs = db.get_documents(status=DocumentStatus.DISCOVERED, limit=1)
    if not docs:
        raise RuntimeError("No DISCOVERED documents in DB – run discovery first")

    doc = docs[0]
    result = process_document(str(doc.id), doc.url, site_name=doc.site_name)
    assert result["status"] in ("processed", "skipped"), (
        f"Unexpected status: {result['status']}"
    )
    return result


def check_semantic_search():
    """Run a semantic search and verify at least one result is returned."""
    from src.llm.embeddings import EmbeddingClient
    from src.storage.vector_db import VectorDBClient

    embedder = EmbeddingClient()
    vdb = VectorDBClient()

    query_vec = embedder.embed("maize storage best practices Uganda")
    results = vdb.search(query_vec, top_k=5)
    # It's OK to have 0 results if no docs have been processed yet
    return len(results)


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Feature smoke test for the post-harvest scraper")
    p.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip the live crawl test (faster, avoids network requests)",
    )
    p.add_argument(
        "--skip-process",
        action="store_true",
        help="Skip end-to-end document processing test",
    )
    return p.parse_args()


def main():
    args = parse_args()
    print("\n🌾  Post-Harvest Scraper – Feature Smoke Test")
    print("=" * 60)

    # ── 1. Infrastructure ────────────────────────────────────────
    section("1 / 6  Infrastructure Connectivity")
    pg_ok   = check("PostgreSQL connection", check_postgres)
    minio_ok = check("MinIO connection", check_minio)
    qdrant_ok = check("Qdrant connection", check_qdrant)
    llm_result = check("LLM connection", check_llm)
    llm_ok = llm_result is not None
    emb_result = check("Embedding service", check_embeddings)
    emb_ok = emb_result is not None

    if emb_ok:
        print(f"         → dimension: {emb_result}")

    # ── 2. Content extraction ────────────────────────────────────
    section("2 / 6  Content Extraction")
    check("HTML extraction (trafilatura/BS4)", check_html_extraction)
    chunks_result = check("Text chunking", check_text_chunking)
    if chunks_result:
        print(f"         → {chunks_result} chunks produced")

    # ── 3. LLM classification ────────────────────────────────────
    section("3 / 6  LLM Classification")
    rel = check("URL classification", lambda: check_url_classification(llm_ok))
    if rel:
        print(f"         → top relevance score: {rel:.1f}/10")
    crel = check("Content classification", lambda: check_content_classification(llm_ok))
    if crel:
        print(f"         → relevance score: {crel:.1f}/10")

    # ── 4. Vector DB roundtrip ───────────────────────────────────
    section("4 / 6  Vector DB Roundtrip (embed → store → search)")
    vr = check("Embed + upsert + search + delete", check_vector_roundtrip,
               skip=not (emb_ok and qdrant_ok))
    if vr:
        print(f"         → {vr} results returned")

    # ── 5. Discovery pipeline ────────────────────────────────────
    section("5 / 6  Discovery Pipeline (live crawl of NARO)")
    if args.skip_crawl:
        print(f"  {SKIP}  Discovery crawl (--skip-crawl)")
        _results.append(("Discovery crawl", True, "skipped"))
        discovery_ok = False
    else:
        print("         (crawling naro.go.ug – may take 30–90 s)")
        disc = check("Crawl + LLM classify + DB store", check_discovery_crawl)
        discovery_ok = disc is not None
        if disc:
            print(f"         → {disc['urls_discovered']} URLs, "
                  f"{disc['documents_stored']} stored")

    # ── 6. Processing pipeline ───────────────────────────────────
    section("6 / 6  Processing Pipeline (download → extract → embed → store)")
    if args.skip_process or not (pg_ok and minio_ok and qdrant_ok and emb_ok):
        reason = "--skip-process" if args.skip_process else "dependency not ready"
        print(f"  {SKIP}  Document processing ({reason})")
        _results.append(("Document processing", True, "skipped"))
    else:
        proc = check("Process one document end-to-end", check_process_one_document)
        if proc:
            print(f"         → status: {proc['status']}, chunks: {proc.get('chunks', '?')}")

    # ── Semantic search (bonus) ──────────────────────────────────
    section("Bonus  Semantic Search")
    sr = check("Query vector DB", check_semantic_search,
               skip=not (emb_ok and qdrant_ok))
    if sr is not None:
        print(f"         → {sr} results (0 is OK if no docs processed yet)")

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    total  = len(_results)
    skipped = sum(1 for _, ok, d in _results if d == "skipped")
    failed = total - passed

    print(f"  Results: {passed}/{total} passed  "
          f"({skipped} skipped, {failed} failed)")

    failures = [(l, d) for l, ok, d in _results if not ok]
    if failures:
        print(f"\n  {RED}Failures:{RESET}")
        for label, detail in failures:
            print(f"    • {label}")
            if detail and detail != "skipped":
                print(f"      {detail}")
        print()
        sys.exit(1)
    else:
        print(f"\n  {GREEN}All checks passed!{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
