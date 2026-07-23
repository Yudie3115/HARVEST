"""Unit tests for catalogue scoring helpers and durable job payloads."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.api.services.catalogue_service import (
    _cosine_similarity,
    delete_entry_vector,
    enqueue_candidate_job,
    publish_entry,
    run_claimed_job,
    score_and_create_candidate,
)
from src.storage.models import (
    BackgroundJob,
    BackgroundJobStatusEnum,
    CatalogueEntry,
    CatalogueStatusEnum,
    ChatMessage,
    ContentChunk,
    MessageRoleEnum,
)


def test_cosine_similarity_supports_duplicate_threshold_boundaries():
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert _cosine_similarity([], [1.0]) == -1.0
    assert _cosine_similarity([1.0], [1.0, 2.0]) == -1.0


def test_candidate_job_contains_stable_message_and_chunk_ids():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    message_id = uuid4()
    chunk_ids = [uuid4(), uuid4()]

    job = enqueue_candidate_job(
        db,
        assistant_message_id=message_id,
        source_chunk_ids=chunk_ids,
    )

    assert isinstance(job, BackgroundJob)
    assert job.job_type == "score_and_catalogue"
    assert job.payload == {
        "assistant_message_id": str(message_id),
        "source_chunk_ids": [str(value) for value in chunk_ids],
    }
    db.add.assert_called_once_with(job)


def test_candidate_job_enqueue_is_idempotent_per_assistant_message():
    db = MagicMock()
    existing = BackgroundJob(id=uuid4(), job_type="score_and_catalogue", payload={})
    db.query.return_value.filter.return_value.first.return_value = existing

    result = enqueue_candidate_job(
        db,
        assistant_message_id=uuid4(),
        source_chunk_ids=[],
    )

    assert result is existing
    db.add.assert_not_called()


def test_candidate_reloads_sources_by_vector_id_and_stores_chunk_primary_key():
    db = MagicMock()
    session_id = uuid4()
    message_id = uuid4()
    created_at = datetime.now(timezone.utc)
    assistant = ChatMessage(
        id=message_id,
        session_id=session_id,
        role=MessageRoleEnum.assistant,
        content="Dry maize before storage.",
        created_at=created_at,
    )
    user = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role=MessageRoleEnum.user,
        content="How should I dry maize?",
        created_at=created_at,
    )
    chunk = ContentChunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        text="Maize should be dried to a safe moisture content.",
        vector_id=str(uuid4()),
    )

    empty_source_query = MagicMock()
    empty_source_query.filter.return_value.first.return_value = None
    user_query = MagicMock()
    user_query.filter.return_value.order_by.return_value.first.return_value = user
    chunks_query = MagicMock()
    chunks_query.filter.return_value.all.return_value = [chunk]
    duplicate_query = MagicMock()
    duplicate_query.filter.return_value.all.return_value = []
    db.query.side_effect = [
        empty_source_query,
        user_query,
        chunks_query,
        duplicate_query,
    ]
    db.get.return_value = assistant

    llm = MagicMock()
    llm.evaluate_catalogue_candidate.return_value = {
        "worth_cataloguing_score": 0.9,
        "optimised_question": "How should maize be dried before storage?",
    }
    embeddings = MagicMock()
    embeddings.embed.return_value = [0.1] * 3
    scorer = MagicMock()
    scorer.score.return_value = {"f1": 0.8}

    with (
        patch("src.api.services.catalogue_service.get_scorer", return_value=scorer),
        patch("src.api.services.catalogue_service.settings") as config,
    ):
        config.bertscore_enabled = True
        config.catalogue_min_faithfulness = 0.6
        config.catalogue_mode = "manual"
        config.catalogue_min_score = 0.7
        config.embedding_dimension = 3
        config.catalogue_duplicate_threshold = 0.9
        entry = score_and_create_candidate(
            db,
            {
                "assistant_message_id": str(message_id),
                "source_chunk_ids": [chunk.vector_id],
            },
            llm_client=llm,
            embedding_client=embeddings,
        )

    assert isinstance(entry, CatalogueEntry)
    assert entry.source_chunk_ids == [chunk.id]
    scorer.score.assert_called_once_with(assistant.content, [chunk.text])


def _pending_entry(**overrides) -> CatalogueEntry:
    defaults = dict(
        id=uuid4(),
        question_en="How should maize be dried?",
        answer_en="Dry maize to a safe moisture content before storage.",
        embedding=[0.1, 0.2, 0.3],
        status=CatalogueStatusEnum.pending,
        question_translations=None,
        answer_translations=None,
        publish_attempts=0,
        publish_error=None,
    )
    defaults.update(overrides)
    return CatalogueEntry(**defaults)


def test_publish_entry_translates_all_languages_and_approves():
    entry = _pending_entry()
    db = MagicMock()
    db.get.return_value = entry
    translations = MagicMock()
    translations.translate_from_english.side_effect = lambda text, lang: f"{lang}:{text}"
    vectors = MagicMock()

    with patch("src.api.services.catalogue_service.settings") as config:
        config.embedding_dimension = 3
        result = publish_entry(
            db, entry.id, translation_client=translations, catalogue_vector_client=vectors
        )

    assert result.status == CatalogueStatusEnum.approved
    assert result.approved_at is not None
    assert result.publish_error is None
    assert set(result.question_translations) == {"lug", "ach", "nyn", "teo", "lgg"}
    assert set(result.answer_translations) == {"lug", "ach", "nyn", "teo", "lgg"}
    vectors.upsert_chunk.assert_called_once_with(
        str(entry.id),
        [0.1, 0.2, 0.3],
        {"catalogue_entry_id": str(entry.id), "question_en": entry.question_en},
    )


def test_publish_entry_is_idempotent_when_already_approved():
    entry = _pending_entry(status=CatalogueStatusEnum.approved)
    db = MagicMock()
    db.get.return_value = entry
    translations = MagicMock()
    vectors = MagicMock()

    result = publish_entry(
        db, entry.id, translation_client=translations, catalogue_vector_client=vectors
    )

    assert result is entry
    translations.translate_from_english.assert_not_called()
    vectors.upsert_chunk.assert_not_called()


def test_publish_entry_reuses_already_persisted_translations_on_retry():
    entry = _pending_entry(
        status=CatalogueStatusEnum.publish_failed,
        question_translations={"lug": "already-translated-question"},
        answer_translations={"lug": "already-translated-answer"},
    )
    db = MagicMock()
    db.get.return_value = entry
    translations = MagicMock()
    translations.translate_from_english.side_effect = lambda text, lang: f"{lang}:{text}"
    vectors = MagicMock()

    with patch("src.api.services.catalogue_service.settings") as config:
        config.embedding_dimension = 3
        publish_entry(db, entry.id, translation_client=translations, catalogue_vector_client=vectors)

    called_languages = {call.args[1] for call in translations.translate_from_english.call_args_list}
    assert "lug" not in called_languages
    assert entry.question_translations["lug"] == "already-translated-question"
    assert entry.answer_translations["lug"] == "already-translated-answer"


def test_publish_entry_marks_publish_failed_and_retains_completed_translations():
    entry = _pending_entry()
    db = MagicMock()
    db.get.return_value = entry
    translations = MagicMock()

    def flaky(text, lang):
        if lang == "nyn":
            raise RuntimeError("translation service unavailable")
        return f"{lang}:{text}"

    translations.translate_from_english.side_effect = flaky
    vectors = MagicMock()

    with patch("src.api.services.catalogue_service.settings") as config:
        config.embedding_dimension = 3
        with pytest.raises(RuntimeError):
            publish_entry(
                db, entry.id, translation_client=translations, catalogue_vector_client=vectors
            )

    assert entry.status == CatalogueStatusEnum.publish_failed
    assert "translation service unavailable" in entry.publish_error
    assert entry.question_translations["lug"] == "lug:How should maize be dried?"
    assert entry.answer_translations["ach"].startswith("ach:")
    assert "nyn" not in entry.question_translations
    vectors.upsert_chunk.assert_not_called()


def test_publish_entry_rejects_unpublishable_status():
    entry = _pending_entry(status=CatalogueStatusEnum.rejected)
    db = MagicMock()
    db.get.return_value = entry

    with pytest.raises(ValueError):
        publish_entry(
            db, entry.id, translation_client=MagicMock(), catalogue_vector_client=MagicMock()
        )


def test_delete_entry_vector_noop_unless_retracted():
    entry = _pending_entry(status=CatalogueStatusEnum.approved)
    db = MagicMock()
    db.get.return_value = entry
    vectors = MagicMock()

    delete_entry_vector(db, entry.id, catalogue_vector_client=vectors)
    vectors.delete_point.assert_not_called()

    entry.status = CatalogueStatusEnum.retracted
    delete_entry_vector(db, entry.id, catalogue_vector_client=vectors)
    vectors.delete_point.assert_called_once_with(str(entry.id))


def test_delete_entry_vector_noop_when_entry_missing():
    db = MagicMock()
    db.get.return_value = None
    vectors = MagicMock()

    delete_entry_vector(db, uuid4(), catalogue_vector_client=vectors)

    vectors.delete_point.assert_not_called()


def test_run_claimed_job_completes_and_clears_previous_error():
    job = BackgroundJob(
        id=uuid4(),
        job_type="publish_catalogue",
        payload={"catalogue_entry_id": str(uuid4())},
        attempts=2,
        last_error="a previous failure",
    )
    db = MagicMock()
    db.get.return_value = job

    with patch("src.api.services.catalogue_service.publish_entry") as publish:
        run_claimed_job(
            db,
            job,
            llm_client=MagicMock(),
            embedding_client=MagicMock(),
            translation_client=MagicMock(),
            catalogue_vector_client=MagicMock(),
        )

    publish.assert_called_once()
    assert job.status == BackgroundJobStatusEnum.completed
    assert job.last_error is None


def test_run_claimed_job_schedules_backoff_retry_below_max_attempts():
    job = BackgroundJob(
        id=uuid4(),
        job_type="publish_catalogue",
        payload={"catalogue_entry_id": str(uuid4())},
        attempts=1,
    )
    db = MagicMock()
    db.get.return_value = job
    before = datetime.now(timezone.utc)

    with (
        patch("src.api.services.catalogue_service.publish_entry", side_effect=RuntimeError("boom")),
        patch("src.api.services.catalogue_service.settings") as config,
    ):
        config.catalogue_job_max_attempts = 5
        run_claimed_job(
            db,
            job,
            llm_client=MagicMock(),
            embedding_client=MagicMock(),
            translation_client=MagicMock(),
            catalogue_vector_client=MagicMock(),
        )

    assert job.status == BackgroundJobStatusEnum.pending
    assert job.last_error == "boom"
    assert job.available_at > before


def test_run_claimed_job_marks_failed_after_max_attempts():
    job = BackgroundJob(
        id=uuid4(),
        job_type="publish_catalogue",
        payload={"catalogue_entry_id": str(uuid4())},
        attempts=5,
    )
    db = MagicMock()
    db.get.return_value = job

    with (
        patch("src.api.services.catalogue_service.publish_entry", side_effect=RuntimeError("boom")),
        patch("src.api.services.catalogue_service.settings") as config,
    ):
        config.catalogue_job_max_attempts = 5
        run_claimed_job(
            db,
            job,
            llm_client=MagicMock(),
            embedding_client=MagicMock(),
            translation_client=MagicMock(),
            catalogue_vector_client=MagicMock(),
        )

    assert job.status == BackgroundJobStatusEnum.failed
