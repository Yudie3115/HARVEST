"""
Public document library routes — browsable without an access code.

Every endpoint applies the same visibility rule: Document.status == PROCESSED,
its classification's relevance_score >= settings.relevance_threshold, and
Document.publicly_visible == true. Uploaded (upload://) sources are additionally
excluded unless public_source_url is set. Relevance alone never grants visibility.
"""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.config.settings import settings

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
