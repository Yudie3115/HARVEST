"""Public browse, detail, match, and helpful endpoints for approved Q&A."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_catalogue_vector_db_client,
    get_db,
    get_embedding_client,
    get_translation_client,
)
from src.config.settings import settings
from src.storage.models import CatalogueEntry, CatalogueStatusEnum, ChatMessage

router = APIRouter(prefix="/catalogue", tags=["catalogue"])
limiter = Limiter(key_func=get_remote_address)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Catalogue entry not found.")


def _sources(db: Session, entry: CatalogueEntry) -> list[dict]:
    if not entry.source_message_id:
        return []
    message = db.get(ChatMessage, entry.source_message_id)
    return list(message.sources or []) if message else []


def _public_entry(db: Session, entry: CatalogueEntry, language: str = "eng") -> dict:
    questions = entry.question_translations or {}
    answers = entry.answer_translations or {}
    return {
        "id": str(entry.id),
        "question": questions.get(language) or entry.question_en,
        "answer": answers.get(language) or entry.answer_en,
        "language": language if language in questions else "eng",
        "sources": _sources(db, entry),
        "served_count": entry.served_count,
        "helpful_count": entry.helpful_count,
        "approved_at": entry.approved_at.isoformat() if entry.approved_at else None,
    }


@router.get("")
def list_catalogue(
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(CatalogueEntry).filter(
        CatalogueEntry.status == CatalogueStatusEnum.approved
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(CatalogueEntry.question_en.ilike(like), CatalogueEntry.answer_en.ilike(like))
        )
    total = query.count()
    entries = (
        query.order_by(CatalogueEntry.approved_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_public_entry(db, entry) for entry in entries],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{entry_id}")
def get_catalogue_entry(
    entry_id: UUID,
    language: str = Query(default="eng", max_length=3),
    db: Session = Depends(get_db),
) -> dict:
    entry = db.get(CatalogueEntry, entry_id)
    if entry is None or entry.status != CatalogueStatusEnum.approved:
        raise _not_found()
    return _public_entry(db, entry, language)


@router.post("/match")
@limiter.limit(settings.catalogue_match_rate_limit)
def match_catalogue(
    request: Request,
    body: dict,
    db: Session = Depends(get_db),
    embeddings=Depends(get_embedding_client),
    vectors=Depends(get_catalogue_vector_db_client),
    translations=Depends(get_translation_client),
) -> dict:
    question = str(body.get("question", "")).strip()
    if not question or len(question) > 1000:
        raise HTTPException(status_code=422, detail="question must contain 1–1000 characters")

    language = translations.detect_language(question) or "eng"
    question_en = (
        translations.translate_to_english(question, language) if language != "eng" else question
    )
    hits = vectors.search(
        embeddings.embed(question_en),
        top_k=3,
        score_threshold=settings.catalogue_match_threshold,
    )
    for hit in hits:
        try:
            entry_id = UUID(hit.get("payload", {}).get("catalogue_entry_id") or hit["id"])
        except (KeyError, TypeError, ValueError):
            continue
        entry = db.get(CatalogueEntry, entry_id)
        if entry is None or entry.status != CatalogueStatusEnum.approved:
            continue
        entry.served_count += 1
        db.commit()
        result = _public_entry(db, entry, language)
        result["score"] = hit.get("score")
        return {"matched": True, "entry": result}
    return {"matched": False, "entry": None}


@router.post("/{entry_id}/helpful")
@limiter.limit(settings.catalogue_helpful_rate_limit)
def mark_helpful(
    request: Request,
    entry_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    entry = db.get(CatalogueEntry, entry_id)
    if entry is None or entry.status != CatalogueStatusEnum.approved:
        raise _not_found()
    entry.helpful_count += 1
    db.commit()
    return {"id": str(entry.id), "helpful_count": entry.helpful_count}
