"""Focused route tests for public catalogue serving and status verification."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.storage.models import CatalogueEntry, CatalogueStatusEnum


def _entry(status=CatalogueStatusEnum.approved):
    return CatalogueEntry(
        id=uuid4(),
        question_en="How should maize be dried?",
        answer_en="Dry maize to a safe moisture content before storage.",
        status=status,
        served_count=0,
        helpful_count=0,
        candidate_duplicate_count=0,
        publish_attempts=0,
        approved_at=datetime.now(timezone.utc),
    )


def _dependencies(entry):
    db = MagicMock()
    db.get.side_effect = lambda model, value: entry if model is CatalogueEntry else None
    embeddings = MagicMock()
    embeddings.embed.return_value = [0.1] * 1536
    vectors = MagicMock()
    vectors.search.return_value = [
        {
            "id": str(entry.id),
            "score": 0.94,
            "payload": {"catalogue_entry_id": str(entry.id)},
        }
    ]
    translations = MagicMock()
    translations.detect_language.return_value = None

    return db, embeddings, vectors, translations


def test_match_serves_and_counts_only_approved_entry():
    entry = _entry()
    db, embeddings, vectors, translations = _dependencies(entry)
    from src.api.routes.catalogue import match_catalogue

    result = match_catalogue.__wrapped__(
        request=MagicMock(),
        body={"question": "How do I dry maize?"},
        db=db,
        embeddings=embeddings,
        vectors=vectors,
        translations=translations,
    )

    assert result["matched"] is True
    assert result["entry"]["id"] == str(entry.id)
    assert entry.served_count == 1
    db.commit.assert_called_once()


def test_match_rechecks_database_status_after_vector_hit():
    entry = _entry(CatalogueStatusEnum.retracted)
    db, embeddings, vectors, translations = _dependencies(entry)
    from src.api.routes.catalogue import match_catalogue

    result = match_catalogue.__wrapped__(
        request=MagicMock(),
        body={"question": "How do I dry maize?"},
        db=db,
        embeddings=embeddings,
        vectors=vectors,
        translations=translations,
    )

    assert result == {"matched": False, "entry": None}
    assert entry.served_count == 0
    db.commit.assert_not_called()


def test_nonapproved_detail_uses_uniform_404():
    entry = _entry(CatalogueStatusEnum.publish_failed)
    db, _, _, _ = _dependencies(entry)
    from src.api.routes.catalogue import get_catalogue_entry

    with pytest.raises(HTTPException) as exc:
        get_catalogue_entry(entry.id, language="eng", db=db)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Catalogue entry not found."


def test_helpful_increments_only_approved_entry():
    entry = _entry()
    db, _, _, _ = _dependencies(entry)
    from src.api.routes.catalogue import mark_helpful

    result = mark_helpful.__wrapped__(request=MagicMock(), entry_id=entry.id, db=db)

    assert result["helpful_count"] == 1
    db.commit.assert_called_once()
