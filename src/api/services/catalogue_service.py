"""Durable candidate scoring and publication for the reusable Q&A catalogue."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.api.services.operational_metrics import (
    CATALOGUE_CANDIDATE_METRIC,
    CATALOGUE_WORKER_METRIC,
    record_metric,
)
from src.llm.bert_scoring import get_scorer
from src.storage.models import (
    BackgroundJob,
    BackgroundJobStatusEnum,
    CatalogueEntry,
    CatalogueStatusEnum,
    ChatMessage,
    ContentChunk,
    MessageRoleEnum,
)

CATALOGUE_LANGUAGES = ("lug", "ach", "nyn", "teo", "lgg")
_CATALOGUE_STATUSES = (
    CatalogueStatusEnum.pending,
    CatalogueStatusEnum.publishing,
    CatalogueStatusEnum.approved,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def enqueue_candidate_job(
    db: Session,
    *,
    assistant_message_id: UUID,
    source_chunk_ids: Iterable[str | UUID],
) -> BackgroundJob:
    """Add the candidate job in the same transaction as its assistant message."""
    message_id = str(assistant_message_id)
    existing = (
        db.query(BackgroundJob)
        .filter(
            BackgroundJob.job_type == "score_and_catalogue",
            BackgroundJob.payload["assistant_message_id"].astext == message_id,
        )
        .first()
    )
    if existing:
        return existing

    job = BackgroundJob(
        job_type="score_and_catalogue",
        payload={
            "assistant_message_id": message_id,
            "source_chunk_ids": [str(value) for value in source_chunk_ids],
        },
        status=BackgroundJobStatusEnum.pending,
        available_at=_now(),
    )
    db.add(job)
    return job


def enqueue_publication_job(db: Session, entry_id: UUID) -> BackgroundJob:
    job = BackgroundJob(
        job_type="publish_catalogue",
        payload={"catalogue_entry_id": str(entry_id)},
        status=BackgroundJobStatusEnum.pending,
        available_at=_now(),
    )
    db.add(job)
    return job


def enqueue_retraction_job(db: Session, entry_id: UUID) -> BackgroundJob:
    job = BackgroundJob(
        job_type="delete_catalogue_vector",
        payload={"catalogue_entry_id": str(entry_id)},
        status=BackgroundJobStatusEnum.pending,
        available_at=_now(),
    )
    db.add(job)
    return job


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return dot / (left_norm * right_norm)


def _preceding_user_message(db: Session, assistant: ChatMessage) -> ChatMessage | None:
    return (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == assistant.session_id,
            ChatMessage.role == MessageRoleEnum.user,
            ChatMessage.created_at <= assistant.created_at,
        )
        .order_by(ChatMessage.created_at.desc())
        .first()
    )


def score_and_create_candidate(
    db: Session,
    payload: dict,
    *,
    llm_client,
    embedding_client,
) -> CatalogueEntry | None:
    """Run the dependent candidate sequence once; safely deduplicate retries."""
    message_id = UUID(payload["assistant_message_id"])
    existing = (
        db.query(CatalogueEntry).filter(CatalogueEntry.source_message_id == message_id).first()
    )
    if existing:
        return existing
    if not settings.bertscore_enabled:
        record_metric(
            db,
            CATALOGUE_CANDIDATE_METRIC,
            0,
            component="catalogue",
            metadata={"outcome": "scoring_disabled"},
        )
        return None

    assistant = db.get(ChatMessage, message_id)
    if assistant is None or _enum_value(assistant.role) != MessageRoleEnum.assistant.value:
        raise ValueError("Assistant message no longer exists")
    user = _preceding_user_message(db, assistant)
    if user is None:
        raise ValueError("Preceding user message was not found")

    vector_ids = [str(value) for value in payload.get("source_chunk_ids", [])]
    chunks = (
        db.query(ContentChunk).filter(ContentChunk.vector_id.in_(vector_ids)).all()
        if vector_ids
        else []
    )
    references = [chunk.text for chunk in chunks if chunk.text]
    answer_en = assistant.english_content or assistant.content
    score = get_scorer().score(answer_en, references)
    if not score:
        record_metric(
            db,
            CATALOGUE_CANDIDATE_METRIC,
            0,
            component="catalogue",
            metadata={"outcome": "scoring_failed"},
        )
        return None
    assistant.bert_score = score
    db.commit()

    grounding_score = float(score["f1"])
    if grounding_score < settings.catalogue_min_faithfulness:
        record_metric(
            db,
            CATALOGUE_CANDIDATE_METRIC,
            grounding_score,
            component="catalogue",
            unit="similarity",
            metadata={"outcome": "below_faithfulness"},
        )
        return None

    evaluation = llm_client.evaluate_catalogue_candidate(user.content, answer_en)
    llm_score = evaluation["worth_cataloguing_score"]
    if settings.catalogue_mode == "manual" and llm_score < settings.catalogue_min_score:
        record_metric(
            db,
            CATALOGUE_CANDIDATE_METRIC,
            grounding_score,
            component="catalogue",
            unit="similarity",
            metadata={"outcome": "below_llm_score", "llm_score": llm_score},
        )
        return None

    question = evaluation["optimised_question"]
    embedding = embedding_client.embed(question)
    if len(embedding) != settings.embedding_dimension:
        raise ValueError(
            f"Catalogue embedding has {len(embedding)} dimensions; "
            f"expected {settings.embedding_dimension}"
        )

    candidates = (
        db.query(CatalogueEntry).filter(CatalogueEntry.status.in_(_CATALOGUE_STATUSES)).all()
    )
    duplicate = max(
        candidates,
        key=lambda entry: _cosine_similarity(embedding, entry.embedding or []),
        default=None,
    )
    if (
        duplicate is not None
        and _cosine_similarity(embedding, duplicate.embedding or [])
        >= settings.catalogue_duplicate_threshold
    ):
        duplicate.candidate_duplicate_count += 1
        record_metric(
            db,
            CATALOGUE_CANDIDATE_METRIC,
            grounding_score,
            component="catalogue",
            unit="similarity",
            metadata={"outcome": "duplicate", "llm_score": llm_score},
        )
        return duplicate

    entry = CatalogueEntry(
        question_en=question,
        answer_en=answer_en,
        embedding=embedding,
        status=CatalogueStatusEnum.pending,
        source_message_id=assistant.id,
        source_chunk_ids=[chunk.id for chunk in chunks],
        grounding_score=grounding_score,
        llm_score=llm_score,
    )
    db.add(entry)
    db.flush()
    record_metric(
        db,
        CATALOGUE_CANDIDATE_METRIC,
        grounding_score,
        component="catalogue",
        unit="similarity",
        metadata={
            "outcome": "candidate_created",
            "llm_score": llm_score,
            "mode": settings.catalogue_mode,
        },
    )
    if settings.catalogue_mode == "auto":
        enqueue_publication_job(db, entry.id)
    return entry


def publish_entry(
    db: Session,
    entry_id: UUID,
    *,
    translation_client,
    catalogue_vector_client,
) -> CatalogueEntry:
    """Idempotently translate, vectorize, and approve one catalogue entry."""
    entry = db.get(CatalogueEntry, entry_id)
    if entry is None:
        raise ValueError("Catalogue entry no longer exists")
    if entry.status == CatalogueStatusEnum.approved:
        return entry
    if entry.status not in (
        CatalogueStatusEnum.pending,
        CatalogueStatusEnum.publish_failed,
        CatalogueStatusEnum.publishing,
    ):
        raise ValueError(f"Entry cannot be published from status {_enum_value(entry.status)}")

    entry.status = CatalogueStatusEnum.publishing
    entry.publish_attempts += 1
    entry.publish_error = None
    db.commit()

    try:
        questions = dict(entry.question_translations or {})
        answers = dict(entry.answer_translations or {})
        for language in CATALOGUE_LANGUAGES:
            if not questions.get(language):
                questions[language] = translation_client.translate_from_english(
                    entry.question_en, language
                )
                entry.question_translations = dict(questions)
                db.commit()
            if not answers.get(language):
                answers[language] = translation_client.translate_from_english(
                    entry.answer_en, language
                )
                entry.answer_translations = dict(answers)
                db.commit()

        if any(not questions.get(lang) or not answers.get(lang) for lang in CATALOGUE_LANGUAGES):
            raise ValueError("One or more required catalogue translations are missing")
        if not entry.embedding or len(entry.embedding) != settings.embedding_dimension:
            raise ValueError("Catalogue entry has an invalid embedding")

        catalogue_vector_client.upsert_chunk(
            str(entry.id),
            list(entry.embedding),
            {"catalogue_entry_id": str(entry.id), "question_en": entry.question_en},
        )
        entry.status = CatalogueStatusEnum.approved
        entry.approved_at = _now()
        entry.publish_error = None
        db.commit()
        db.refresh(entry)
        return entry
    except Exception as exc:
        db.rollback()
        entry = db.get(CatalogueEntry, entry_id)
        entry.status = CatalogueStatusEnum.publish_failed
        entry.publish_error = str(exc)[:1000]
        db.commit()
        raise


def delete_entry_vector(db: Session, entry_id: UUID, *, catalogue_vector_client) -> None:
    entry = db.get(CatalogueEntry, entry_id)
    if entry is None:
        return
    if entry.status != CatalogueStatusEnum.retracted:
        return
    catalogue_vector_client.delete_point(str(entry_id))


def claim_next_job(db: Session) -> BackgroundJob | None:
    """Claim one available job using PostgreSQL skip-locked semantics."""
    job = (
        db.query(BackgroundJob)
        .filter(
            BackgroundJob.status == BackgroundJobStatusEnum.pending,
            BackgroundJob.available_at <= _now(),
        )
        .order_by(BackgroundJob.created_at)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        db.rollback()
        return None
    job.status = BackgroundJobStatusEnum.running
    job.attempts += 1
    db.commit()
    db.refresh(job)
    return job


def run_claimed_job(
    db: Session,
    job: BackgroundJob,
    *,
    llm_client,
    embedding_client,
    translation_client,
    catalogue_vector_client,
) -> None:
    """Dispatch one claimed job and record completion or retry state."""
    try:
        if job.job_type == "score_and_catalogue":
            score_and_create_candidate(
                db,
                job.payload,
                llm_client=llm_client,
                embedding_client=embedding_client,
            )
        elif job.job_type == "publish_catalogue":
            publish_entry(
                db,
                UUID(job.payload["catalogue_entry_id"]),
                translation_client=translation_client,
                catalogue_vector_client=catalogue_vector_client,
            )
        elif job.job_type == "delete_catalogue_vector":
            delete_entry_vector(
                db,
                UUID(job.payload["catalogue_entry_id"]),
                catalogue_vector_client=catalogue_vector_client,
            )
        else:
            raise ValueError(f"Unknown background job type: {job.job_type}")
        job = db.get(BackgroundJob, job.id)
        job.status = BackgroundJobStatusEnum.completed
        job.last_error = None
        record_metric(
            db,
            CATALOGUE_WORKER_METRIC,
            1,
            component="catalogue_worker",
            metadata={
                "outcome": "completed",
                "job_type": job.job_type,
                "attempts": job.attempts,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(BackgroundJob, job.id)
        job.last_error = str(exc)[:1000]
        if job.attempts >= settings.catalogue_job_max_attempts:
            job.status = BackgroundJobStatusEnum.failed
            outcome = "failed"
        else:
            job.status = BackgroundJobStatusEnum.pending
            job.available_at = _now() + timedelta(seconds=min(300, 2**job.attempts))
            outcome = "retry_scheduled"
        record_metric(
            db,
            CATALOGUE_WORKER_METRIC,
            0,
            component="catalogue_worker",
            metadata={
                "outcome": outcome,
                "job_type": job.job_type,
                "attempts": job.attempts,
                "error_type": type(exc).__name__,
            },
        )
        db.commit()
        logger.exception(f"Catalogue job {job.id} failed")
