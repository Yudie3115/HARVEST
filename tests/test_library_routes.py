"""Tests for the public /library routes."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

_engine = create_engine(str(settings.database_url))
_Session = sessionmaker(bind=_engine)


def _make_db_session():
    return _Session()


def _make_client():
    from src.api.routes.library import router
    from src.api.dependencies import get_db

    app = FastAPI()
    app.include_router(router)
    db = _make_db_session()
    app.dependency_overrides[get_db] = lambda: db
    return app, TestClient(app, raise_server_exceptions=False), db


@pytest.fixture(autouse=True)
def _reset_library_cache():
    """Force a fresh facets computation for every test — correctness must not depend on caching."""
    import src.api.routes.library as lib
    lib._reset_facets_cache()
    yield
    lib._reset_facets_cache()


def _delete_test_rows():
    """Delete all rows this test file could have inserted, identified by the hardcoded
    site_name='test' used throughout _make_document().

    Uses real, committed DELETE statements against the persistent local dev Postgres —
    not a transaction rollback. Every test in this file gets its own `db` session from
    _make_client() (shared with app.dependency_overrides for the duration of that one
    test), so there is no single outer transaction a rollback-based fixture could wrap;
    each test's session commits independently via _make_document(). Cleanup therefore
    has to be an explicit DELETE + commit against the real DB, run in its own session.

    Order matters: documents must be deleted before crawl_runs. document_classifications
    and content_chunks cascade automatically (ondelete="CASCADE" on their document_id FK
    — see DocumentClassification/ContentChunk in src/storage/models.py), but
    Document.crawl_run_id -> crawl_runs.id has no ondelete, so deleting crawl_runs first
    would raise a foreign key violation against any remaining test documents.
    """
    db = _make_db_session()
    try:
        db.execute(text("DELETE FROM documents WHERE site_name = 'test'"))
        db.execute(text("DELETE FROM crawl_runs WHERE site_name = 'test'"))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_test_documents():
    """Guarantee a clean starting DB state for every test in this file, and leave a clean
    state behind afterward. Runs before AND after each individual test function (function
    scope, not module scope) because tests run in an unpredictable order and every test —
    not just the first — needs to start from zero rows. Without this, e.g.
    test_counts_are_correct_across_multiple_documents's `shared["count"] == 3` assertion
    would accumulate extra rows on a second suite run, and
    test_cache_serves_stale_result_until_reset's `"cache-test-topic" not in before`
    assertion would fail if a prior run's row were still present.
    """
    _delete_test_rows()
    yield
    _delete_test_rows()


def _make_document(
    db,
    *,
    status="PROCESSED",
    publicly_visible=True,
    relevance_score=8.0,
    url=None,
    public_source_url=None,
    topics=None,
    crops=None,
    regions=None,
    title="Test Document",
):
    """Insert a Document + DocumentClassification pair via raw SQL (status is stored as the
    enum member's UPPER CASE name, e.g. 'PROCESSED' — see the plan's Global Constraints)."""
    from src.storage.models import CrawlStatus

    crawl_run_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO crawl_runs (id, site_name, started_at, status) "
            "VALUES (:id, 'test', now(), :status)"
        ),
        {"id": crawl_run_id, "status": CrawlStatus.RUNNING.name},
    )

    doc_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO documents "
            "(id, crawl_run_id, url, site_name, discovered_at, status, publicly_visible, "
            " public_source_url, title) "
            "VALUES (:id, :crawl_run_id, :url, 'test', now(), :status, :publicly_visible, "
            " :public_source_url, :title)"
        ),
        {
            "id": doc_id,
            "crawl_run_id": crawl_run_id,
            "url": url or f"https://example.org/{doc_id}",
            "status": status,
            "publicly_visible": publicly_visible,
            "public_source_url": public_source_url,
            "title": title,
        },
    )

    db.execute(
        text(
            "INSERT INTO document_classifications "
            "(id, document_id, relevance_score, topics, crops, regions, summary, classified_at) "
            "VALUES (:id, :document_id, :relevance_score, :topics, :crops, :regions, "
            " 'A test summary.', now())"
        ),
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "relevance_score": relevance_score,
            "topics": topics or ["storage"],
            "crops": crops or ["maize"],
            "regions": regions or ["central"],
        },
    )
    db.commit()
    return doc_id


class TestLibraryFacets:
    def test_only_publicly_visible_processed_above_threshold_are_counted(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "relevance_threshold", 6.0)
        app, client, db = _make_client()

        # Qualifies
        _make_document(db, topics=["storage"], crops=["maize"], regions=["central"])
        # Excluded: not publicly_visible
        _make_document(db, publicly_visible=False, topics=["drying"])
        # Excluded: not PROCESSED
        _make_document(db, status="DISCOVERED", topics=["pests"])
        # Excluded: below relevance threshold
        _make_document(db, relevance_score=3.0, topics=["packaging"])

        resp = client.get("/library/facets")
        assert resp.status_code == 200
        body = resp.json()
        topic_values = {t["value"] for t in body["topics"]}
        assert "storage" in topic_values
        assert "drying" not in topic_values
        assert "pests" not in topic_values
        assert "packaging" not in topic_values

    def test_upload_source_excluded_unless_public_source_url_set(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "relevance_threshold", 6.0)
        app, client, db = _make_client()

        doc_id = uuid.uuid4()
        _make_document(
            db,
            url=f"upload://{doc_id}/guide.pdf",
            public_source_url=None,
            topics=["excluded-upload-topic"],
        )
        _make_document(
            db,
            url=f"upload://{uuid.uuid4()}/guide2.pdf",
            public_source_url="https://realsite.example/guide2.pdf",
            topics=["included-upload-topic"],
        )

        resp = client.get("/library/facets")
        body = resp.json()
        topic_values = {t["value"] for t in body["topics"]}
        assert "excluded-upload-topic" not in topic_values
        assert "included-upload-topic" in topic_values

    def test_counts_are_correct_across_multiple_documents(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "relevance_threshold", 6.0)
        app, client, db = _make_client()

        _make_document(db, topics=["shared-topic"])
        _make_document(db, topics=["shared-topic"])
        _make_document(db, topics=["shared-topic"])

        resp = client.get("/library/facets")
        body = resp.json()
        shared = next(t for t in body["topics"] if t["value"] == "shared-topic")
        assert shared["count"] == 3

    def test_empty_result_set_returns_empty_lists_not_an_error(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "relevance_threshold", 6.0)
        app, client, db = _make_client()
        # No documents inserted at all — no documents matching "no-such-anything-marker".

        resp = client.get("/library/facets")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["topics"], list)
        assert isinstance(body["crops"], list)
        assert isinstance(body["regions"], list)

    def test_cache_serves_stale_result_until_reset(self, monkeypatch):
        """Cache correctness contract: within the TTL, a second call must not need a DB round-trip
        to reflect a just-inserted document — this test proves the cache is real, then the autouse
        fixture resets it so it never leaks into other tests."""
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "relevance_threshold", 6.0)
        app, client, db = _make_client()

        resp1 = client.get("/library/facets")
        before = {t["value"] for t in resp1.json()["topics"]}
        assert "cache-test-topic" not in before

        _make_document(db, topics=["cache-test-topic"])

        resp2 = client.get("/library/facets")
        after = {t["value"] for t in resp2.json()["topics"]}
        assert "cache-test-topic" not in after  # still stale — cache not yet expired

        import src.api.routes.library as lib
        lib._reset_facets_cache()

        resp3 = client.get("/library/facets")
        after_reset = {t["value"] for t in resp3.json()["topics"]}
        assert "cache-test-topic" in after_reset
