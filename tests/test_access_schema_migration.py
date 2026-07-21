"""Verify the access & quota schema migration produced the expected tables/columns."""
from sqlalchemy import create_engine, inspect

from src.config.settings import settings


def test_access_and_quota_tables_exist():
    engine = create_engine(str(settings.database_url))
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"access_codes", "access_grants", "global_usage_counters", "redemption_attempts"} <= tables

    chat_session_columns = {c["name"] for c in inspector.get_columns("chat_sessions")}
    assert "access_grant_id" in chat_session_columns

    access_grant_indexes = inspector.get_indexes("access_grants")
    partial_unique = [
        ix for ix in access_grant_indexes
        if ix["name"] == "uq_access_grants_active_channel_identifier"
    ]
    assert len(partial_unique) == 1
    assert partial_unique[0]["unique"] is True
    engine.dispose()


def test_global_usage_counter_singleton_seeded():
    engine = create_engine(str(settings.database_url))
    with engine.connect() as conn:
        from sqlalchemy import text
        row = conn.execute(
            text("SELECT id, usage_count FROM global_usage_counters")
        ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == 0
    engine.dispose()


def test_publication_catalogue_and_job_tables_exist():
    engine = create_engine(str(settings.database_url))
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"catalogue_entries", "background_jobs"} <= tables

    document_columns = {c["name"] for c in inspector.get_columns("documents")}
    assert {"publicly_visible", "published_at", "published_by"} <= document_columns
    engine.dispose()


def test_document_public_source_url_column_exists():
    engine = create_engine(str(settings.database_url))
    inspector = inspect(engine)
    document_columns = {c["name"]: c for c in inspector.get_columns("documents")}
    assert "public_source_url" in document_columns
    assert document_columns["public_source_url"]["nullable"] is True
    engine.dispose()
