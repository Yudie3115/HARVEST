"""
Public document library routes — browsable without an access code.

Every endpoint applies the same visibility rule: Document.status == PROCESSED,
its classification's relevance_score >= settings.relevance_threshold, and
Document.publicly_visible == true. Uploaded (upload://) sources are additionally
excluded unless public_source_url is set. Relevance alone never grants visibility.
"""
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.config.settings import settings
from src.storage.models import ContentChunk, Document, DocumentClassification, DocumentStatus

router = APIRouter(prefix="/library", tags=["library"])

_FACETS_CACHE_TTL_SECONDS = 300
_facets_cache: dict = {"data": None, "computed_at": 0.0}

# documents.status is stored as the enum member's UPPER CASE name (verified against
# the live DB), not its lowercase .value — see the plan's Global Constraints.
_VISIBILITY_SQL = """
    d.status = 'PROCESSED'
    AND dc.relevance_score >= :relevance_threshold
    AND d.publicly_visible = true
    AND (d.url NOT LIKE 'upload://%' OR d.public_source_url IS NOT NULL)
"""


def _reset_facets_cache() -> None:
    """Test hook — forces the next call to recompute rather than serve a cached result."""
    _facets_cache["data"] = None
    _facets_cache["computed_at"] = 0.0


def _compute_facets(db: Session) -> dict:
    facets = {}
    for column, key in (("topics", "topics"), ("crops", "crops"), ("regions", "regions")):
        rows = db.execute(
            text(
                f"""
                SELECT value, COUNT(*) AS count
                FROM documents d
                JOIN document_classifications dc ON dc.document_id = d.id
                CROSS JOIN LATERAL unnest(dc.{column}) AS value
                WHERE {_VISIBILITY_SQL}
                GROUP BY value
                ORDER BY value
                """
            ),
            {"relevance_threshold": settings.relevance_threshold},
        ).mappings().all()
        facets[key] = [{"value": r["value"], "count": r["count"]} for r in rows]
    return facets


def _get_cached_facets(db: Session) -> dict:
    now = time.monotonic()
    if _facets_cache["data"] is None or (now - _facets_cache["computed_at"]) > _FACETS_CACHE_TTL_SECONDS:
        _facets_cache["data"] = _compute_facets(db)
        _facets_cache["computed_at"] = now
    return _facets_cache["data"]


@router.get("/facets")
def get_facets(db: Session = Depends(get_db)) -> dict:
    """Distinct topic/crop/region values with counts, scoped to publicly visible documents."""
    return _get_cached_facets(db)


def _visible_documents_query(db: Session):
    return (
        db.query(Document, DocumentClassification)
        .join(DocumentClassification, DocumentClassification.document_id == Document.id)
        .filter(
            Document.status == DocumentStatus.PROCESSED,
            DocumentClassification.relevance_score >= settings.relevance_threshold,
            Document.publicly_visible.is_(True),
            or_(
                ~Document.url.startswith("upload://"),
                Document.public_source_url.isnot(None),
            ),
        )
    )


def _source_url(doc: Document) -> str:
    return doc.public_source_url if doc.public_source_url else doc.url


_MAX_QUERY_LENGTH = 200
_MAX_FACET_VALUE_LENGTH = 100


@router.get("/documents")
def list_documents(
    topic: str | None = Query(default=None, max_length=_MAX_FACET_VALUE_LENGTH),
    crop: str | None = Query(default=None, max_length=_MAX_FACET_VALUE_LENGTH),
    region: str | None = Query(default=None, max_length=_MAX_FACET_VALUE_LENGTH),
    q: str | None = Query(default=None, max_length=_MAX_QUERY_LENGTH),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Paginated, filterable list of publicly visible documents."""
    query = _visible_documents_query(db)

    if topic:
        query = query.filter(DocumentClassification.topics.any(topic))
    if crop:
        query = query.filter(DocumentClassification.crops.any(crop))
    if region:
        query = query.filter(DocumentClassification.regions.any(region))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Document.title.ilike(like), DocumentClassification.summary.ilike(like))
        )

    total = query.count()
    rows = query.order_by(Document.discovered_at.desc()).offset(offset).limit(limit).all()

    items = [
        {
            "id": str(doc.id),
            "title": doc.title,
            "summary": classification.summary,
            "document_category": classification.document_category,
            "topics": classification.topics or [],
            "crops": classification.crops or [],
            "regions": classification.regions or [],
            "source_url": _source_url(doc),
        }
        for doc, classification in rows
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


_EXCERPT_MAX_CHUNKS = 3
_EXCERPT_MAX_CHARS = 800


@router.get("/documents/{document_id}")
def get_document_detail(document_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Full detail for one publicly visible document: metadata + bounded excerpts, not full text."""
    row = (
        _visible_documents_query(db)
        .filter(Document.id == document_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc, classification = row

    chunks = (
        db.query(ContentChunk)
        .filter(ContentChunk.document_id == document_id)
        .order_by(ContentChunk.chunk_index)
        .limit(_EXCERPT_MAX_CHUNKS)
        .all()
    )
    excerpts = [
        {"chunk_index": c.chunk_index, "text": c.text[:_EXCERPT_MAX_CHARS]}
        for c in chunks
    ]

    return {
        "id": str(doc.id),
        "title": doc.title,
        "summary": classification.summary,
        "document_category": classification.document_category,
        "topics": classification.topics or [],
        "crops": classification.crops or [],
        "regions": classification.regions or [],
        "key_practices": classification.key_practices,
        "actionable": bool(classification.actionable),
        "has_data": bool(classification.has_data),
        "source_url": _source_url(doc),
        "excerpts": excerpts,
    }
