"""Administrator review and publication controls for catalogue candidates."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.routes.admin import require_admin
from src.api.services.catalogue_service import (
    CATALOGUE_LANGUAGES,
    enqueue_publication_job,
    enqueue_retraction_job,
)
from src.api.services.operational_metrics import (
    CATALOGUE_REVIEW_METRIC,
    build_calibration_report,
    record_metric,
)
from src.storage.models import CatalogueEntry, CatalogueStatusEnum, ChatMessage

router = APIRouter(prefix="/admin/catalogue", tags=["admin-catalogue"])


@router.get("/calibration")
def calibration(
    days: int = Query(default=30, ge=1, le=365),
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return build_calibration_report(db, days=days)


def _serialize(db: Session, entry: CatalogueEntry) -> dict:
    message = db.get(ChatMessage, entry.source_message_id) if entry.source_message_id else None
    return {
        "id": str(entry.id),
        "question_en": entry.question_en,
        "answer_en": entry.answer_en,
        "status": entry.status.value if hasattr(entry.status, "value") else entry.status,
        "sources": list(message.sources or []) if message else [],
        "grounding_score": entry.grounding_score,
        "llm_score": entry.llm_score,
        "served_count": entry.served_count,
        "helpful_count": entry.helpful_count,
        "candidate_duplicate_count": entry.candidate_duplicate_count,
        "publish_error": entry.publish_error,
        "publish_attempts": entry.publish_attempts,
        "translations_complete": all(
            (entry.question_translations or {}).get(lang)
            and (entry.answer_translations or {}).get(lang)
            for lang in CATALOGUE_LANGUAGES
        ),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "approved_at": entry.approved_at.isoformat() if entry.approved_at else None,
    }


def _list_entries(db: Session, statuses: tuple, offset: int, limit: int) -> dict:
    query = db.query(CatalogueEntry).filter(CatalogueEntry.status.in_(statuses))
    total = query.count()
    rows = query.order_by(CatalogueEntry.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [_serialize(db, row) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/pending")
def list_pending(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return _list_entries(
        db,
        (
            CatalogueStatusEnum.pending,
            CatalogueStatusEnum.publishing,
            CatalogueStatusEnum.publish_failed,
        ),
        offset,
        limit,
    )


@router.get("/approved")
def list_approved(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return _list_entries(
        db,
        (
            CatalogueStatusEnum.approved,
            CatalogueStatusEnum.retracted,
            CatalogueStatusEnum.rejected,
        ),
        offset,
        limit,
    )


def _entry_or_404(db: Session, entry_id: UUID) -> CatalogueEntry:
    entry = db.get(CatalogueEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Catalogue entry not found.")
    return entry


@router.post("/{entry_id}/approve", status_code=status.HTTP_202_ACCEPTED)
def approve(
    entry_id: UUID,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_or_404(db, entry_id)
    if entry.status not in (
        CatalogueStatusEnum.pending,
        CatalogueStatusEnum.publish_failed,
    ):
        raise HTTPException(status_code=409, detail="Entry is not awaiting publication.")
    job = enqueue_publication_job(db, entry.id)
    record_metric(
        db,
        CATALOGUE_REVIEW_METRIC,
        1,
        component="catalogue_review",
        metadata={
            "outcome": "approved",
            "grounding_score": entry.grounding_score,
            "llm_score": entry.llm_score,
        },
    )
    db.commit()
    return {"id": str(entry.id), "job_id": str(job.id), "status": "queued"}


@router.post("/{entry_id}/reject")
def reject(
    entry_id: UUID,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_or_404(db, entry_id)
    if entry.status not in (
        CatalogueStatusEnum.pending,
        CatalogueStatusEnum.publish_failed,
    ):
        raise HTTPException(status_code=409, detail="Entry cannot be rejected.")
    entry.status = CatalogueStatusEnum.rejected
    record_metric(
        db,
        CATALOGUE_REVIEW_METRIC,
        0,
        component="catalogue_review",
        metadata={
            "outcome": "rejected",
            "grounding_score": entry.grounding_score,
            "llm_score": entry.llm_score,
        },
    )
    db.commit()
    return _serialize(db, entry)


@router.post("/{entry_id}/retract", status_code=status.HTTP_202_ACCEPTED)
def retract(
    entry_id: UUID,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_or_404(db, entry_id)
    if entry.status != CatalogueStatusEnum.approved:
        raise HTTPException(status_code=409, detail="Only approved entries can be retracted.")
    entry.status = CatalogueStatusEnum.retracted
    job = enqueue_retraction_job(db, entry.id)
    db.commit()
    return {"id": str(entry.id), "job_id": str(job.id), "status": "retracted"}


@router.post("/{entry_id}/retry-publish", status_code=status.HTTP_202_ACCEPTED)
def retry_publish(
    entry_id: UUID,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_or_404(db, entry_id)
    if entry.status != CatalogueStatusEnum.publish_failed:
        raise HTTPException(status_code=409, detail="Entry has not failed publication.")
    job = enqueue_publication_job(db, entry.id)
    db.commit()
    return {"id": str(entry.id), "job_id": str(job.id), "status": "queued"}
