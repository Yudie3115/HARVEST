"""
Admin API routes — all protected by JWT.

Endpoints:
  POST /admin/login                  → exchange credentials for JWT
  GET  /admin/stats                  → doc counts + crawl activity
  GET  /admin/documents              → paginated document list
  GET  /admin/health                 → service connection status
  GET  /admin/config                 → read-only settings snapshot
  POST /admin/crawl/full             → trigger Prefect full crawl
  POST /admin/crawl/incremental      → trigger Prefect incremental update
  POST /admin/documents/ingest       → file or URL ingestion
  GET  /admin/chat-quality           → paginated scored chat messages
  GET  /admin/chat-quality/stats     → aggregate faithfulness stats
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import cast, func, text
from sqlalchemy.dialects.postgresql import DATE
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_vector_db_client
from src.config.settings import settings
from src.storage.models import Document, DocumentStatus

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 8

security = HTTPBearer()
router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "exp": expire},
        settings.admin_jwt_secret,
        algorithm=_ALGORITHM,
    )


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.admin_jwt_secret,
            algorithms=[_ALGORITHM],
        )
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    username_ok = secrets.compare_digest(body.username, settings.admin_username)
    password_ok = secrets.compare_digest(body.password, settings.admin_password)
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=_create_token(body.username))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_stats(
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
    vector_db=Depends(get_vector_db_client),
):
    total = db.query(Document).count()
    processed = db.query(Document).filter(
        Document.status == DocumentStatus.PROCESSED
    ).count()

    # Crawl activity: document count per day over last 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = (
        db.query(
            cast(Document.discovered_at, DATE).label("date"),
            func.count(Document.id).label("count"),
        )
        .filter(Document.discovered_at >= cutoff)
        .group_by(cast(Document.discovered_at, DATE))
        .order_by(cast(Document.discovered_at, DATE))
        .all()
    )
    crawl_activity = [{"date": str(r.date), "count": r.count} for r in rows]

    vectors_count = 0
    try:
        info = vector_db.get_collection_info()
        vectors_count = info.get("vectors_count", 0) or 0
    except Exception:
        pass

    return {
        "total_documents": total,
        "processed_documents": processed,
        "processing_rate": processed / total if total > 0 else 0,
        "vectors_count": vectors_count,
        "crawl_activity": crawl_activity,
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/documents")
def list_documents(
    site: Optional[str] = None,
    status: Optional[str] = None,
    sort: str = "discovered",
    offset: int = 0,
    limit: int = 50,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if site:
        query = query.filter(Document.site_name == site)
    if status:
        try:
            query = query.filter(Document.status == DocumentStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")

    total = query.count()

    if sort == "discovered":
        query = query.order_by(Document.discovered_at.desc())

    docs = query.offset(offset).limit(limit).all()

    items = []
    for doc in docs:
        meta = doc.extra_metadata or {}
        llm = meta.get("llm_classification", {}) or {}
        relevance = llm.get("relevance_score")
        items.append({
            "id": str(doc.id),
            "title": doc.title or "Untitled",
            "url": doc.url,
            "site_name": doc.site_name,
            "document_type": doc.document_type or "unknown",
            "status": doc.status.value if doc.status else "unknown",
            "relevance_score": relevance,
            "discovered_at": doc.discovered_at.isoformat() if doc.discovered_at else None,
        })

    if sort == "relevance":
        items.sort(
            key=lambda d: (d["relevance_score"] is None, -(d["relevance_score"] or 0))
        )

    return {"items": items, "total": total, "offset": offset, "limit": limit}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
def check_health(_: str = Depends(require_admin)):
    results = {}

    # PostgreSQL
    try:
        from src.storage.postgres import PostgresClient
        PostgresClient().get_crawl_stats()
        results["PostgreSQL"] = "ok"
    except Exception as exc:
        logger.warning(f"PostgreSQL health check failed: {exc}")
        results["PostgreSQL"] = "error"

    # Qdrant
    try:
        from src.storage.vector_db import VectorDBClient
        results["Qdrant"] = "ok" if VectorDBClient().check_connection() else "error"
    except Exception as exc:
        logger.warning(f"Qdrant health check failed: {exc}")
        results["Qdrant"] = "error"

    # MinIO
    try:
        from src.storage.minio_client import MinIOClient
        MinIOClient().list_objects()
        results["MinIO"] = "ok"
    except Exception as exc:
        logger.warning(f"MinIO health check failed: {exc}")
        results["MinIO"] = "error"

    # LLM
    try:
        from src.llm.client import LLMClient
        results["LLM Service"] = "ok" if LLMClient().check_connection() else "error"
    except Exception as exc:
        logger.warning(f"LLM health check failed: {exc}")
        results["LLM Service"] = "error"

    # Prefect
    try:
        r = httpx.get(settings.prefect_api_url + "/health", timeout=5)
        results["Prefect"] = "ok" if r.status_code == 200 else "error"
    except Exception:
        results["Prefect"] = "error"

    # Sunbird AI
    if settings.translation_enabled and settings.sunbird_api_key:
        try:
            from src.translation import TranslationClient
            results["Sunbird AI"] = "ok" if TranslationClient().check_connection() else "error"
        except Exception:
            results["Sunbird AI"] = "error"
    else:
        results["Sunbird AI"] = "disabled"

    return results


# ---------------------------------------------------------------------------
# Knowledge Q&A
# ---------------------------------------------------------------------------

class QARequest(BaseModel):
    question: str
    top_k: int = 8
    score_threshold: float = 0.4


@router.post("/qa")
def knowledge_qa(
    body: QARequest,
    _: str = Depends(require_admin),
    vector_db=Depends(get_vector_db_client),
):
    from src.llm.client import LLMClient
    from src.llm.embeddings import EmbeddingClient

    embedder = EmbeddingClient()
    query_vec = embedder.embed(body.question)
    results = vector_db.search(
        query_vec,
        top_k=body.top_k,
        score_threshold=body.score_threshold,
    )
    if not results:
        return {"answer": None, "sources": [], "reason": "no_results"}

    llm = LLMClient()
    chunk_payloads = [r["payload"] for r in results]
    answer = llm.answer_question(body.question, chunk_payloads)
    return {"answer": answer, "sources": results}


# ---------------------------------------------------------------------------
# Config (read-only)
# ---------------------------------------------------------------------------

@router.get("/config")
def get_config(_: str = Depends(require_admin)):
    def _mask(val: str) -> str:
        return "***" if val else "(not set)"

    return {
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.openai_model if settings.llm_provider == "openai" else settings.ollama_model,
            "temperature": settings.openai_temperature if settings.llm_provider == "openai" else settings.ollama_temperature,
            "max_tokens": settings.openai_max_tokens if settings.llm_provider == "openai" else settings.ollama_max_tokens,
            "openai_api_key": _mask(settings.openai_api_key),
        },
        "crawl": {
            "max_depth": settings.crawl_max_depth,
            "delay_seconds": settings.crawl_delay_seconds,
            "relevance_threshold": settings.relevance_threshold,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
        },
        "services": {
            "database_url": _mask(str(settings.database_url)),
            "qdrant_url": settings.qdrant_url,
            "minio_endpoint": settings.minio_endpoint,
            "prefect_api_url": settings.prefect_api_url,
            "sunbird_api_url": settings.sunbird_api_url,
            "translation_enabled": settings.translation_enabled,
        },
        "sites": {
            "naro": settings.naro_enabled,
            "agriculture": settings.agriculture_enabled,
            "extension": settings.extension_enabled,
            "ubos": settings.ubos_enabled,
        },
        "environment": settings.environment,
    }


# ---------------------------------------------------------------------------
# Crawl triggers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    score_threshold: float = 0.0


@router.post("/search")
def semantic_search(
    body: SearchRequest,
    _: str = Depends(require_admin),
    vector_db=Depends(get_vector_db_client),
):
    from src.llm.embeddings import EmbeddingClient
    embedder = EmbeddingClient()
    query_vec = embedder.embed(body.query)
    results = vector_db.search(
        query_vec,
        top_k=body.top_k,
        score_threshold=body.score_threshold,
    )
    return results


# ---------------------------------------------------------------------------
# Crawl triggers
# ---------------------------------------------------------------------------

async def _trigger_prefect_deployment(deployment_name: str) -> dict:
    url = f"{settings.prefect_api_url}/deployments/name/{deployment_name}/create_flow_run"
    headers = {}
    if settings.prefect_api_key:
        headers["Authorization"] = f"Bearer {settings.prefect_api_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={}, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Prefect error: {exc.response.text}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Prefect: {exc}")


@router.post("/crawl/full")
async def trigger_full_crawl(_: str = Depends(require_admin)):
    result = await _trigger_prefect_deployment(
        "post_harvest_scraper/daily-scraper-production"
    )
    return {"status": "triggered", "flow_run_id": result.get("id")}


@router.post("/crawl/incremental")
async def trigger_incremental_crawl(_: str = Depends(require_admin)):
    result = await _trigger_prefect_deployment(
        "incremental_update/incremental-update-production"
    )
    return {"status": "triggered", "flow_run_id": result.get("id")}


# ---------------------------------------------------------------------------
# Document ingest
# ---------------------------------------------------------------------------

@router.post("/documents/ingest")
async def ingest_document(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    site_name: str = Form("manual"),
    _: str = Depends(require_admin),
):
    if file is None and not url:
        raise HTTPException(
            status_code=400, detail="Provide either a file upload or a url field."
        )

    from src.flows.manual_ingestion import ingest_manual_document

    if file is not None:
        content = await file.read()
        result = ingest_manual_document(
            content=content,
            filename=file.filename,
            title=title or None,
            site_name=site_name or "manual",
        )
    else:
        result = ingest_manual_document(
            url=url,
            title=title or None,
            site_name=site_name or "manual",
        )

    return result


# ---------------------------------------------------------------------------
# Chat quality (BertScore)
# ---------------------------------------------------------------------------

@router.get("/chat-quality/stats")
def chat_quality_stats(
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Aggregate BertScore faithfulness statistics over all assistant messages."""
    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE bert_score IS NOT NULL)            AS total_scored,
            COUNT(*) FILTER (WHERE bert_score IS NULL)                AS total_unscored,
            AVG((bert_score->>'f1')::float)
                FILTER (WHERE bert_score IS NOT NULL)                  AS mean_f1,
            COUNT(*) FILTER (
                WHERE bert_score IS NOT NULL
                  AND (bert_score->>'f1')::float < 0.4)               AS bucket_0_40,
            COUNT(*) FILTER (
                WHERE bert_score IS NOT NULL
                  AND (bert_score->>'f1')::float >= 0.4
                  AND (bert_score->>'f1')::float <  0.6)              AS bucket_40_60,
            COUNT(*) FILTER (
                WHERE bert_score IS NOT NULL
                  AND (bert_score->>'f1')::float >= 0.6
                  AND (bert_score->>'f1')::float <  0.8)              AS bucket_60_80,
            COUNT(*) FILTER (
                WHERE bert_score IS NOT NULL
                  AND (bert_score->>'f1')::float >= 0.8)              AS bucket_80_100
        FROM chat_messages
        WHERE role = 'assistant'
    """)).mappings().one()

    return {
        "total_scored": row["total_scored"],
        "total_unscored": row["total_unscored"],
        "mean_f1": round(float(row["mean_f1"]), 4) if row["mean_f1"] is not None else None,
        "distribution": [
            {"range": "0.0–0.4", "count": row["bucket_0_40"]},
            {"range": "0.4–0.6", "count": row["bucket_40_60"]},
            {"range": "0.6–0.8", "count": row["bucket_60_80"]},
            {"range": "0.8–1.0", "count": row["bucket_80_100"]},
        ],
    }


@router.get("/chat-quality")
def chat_quality(
    offset: int = 0,
    limit: int = 20,
    min_f1: Optional[float] = None,
    max_f1: Optional[float] = None,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Paginated list of scored assistant messages with the preceding user question.

    Uses a PostgreSQL LATERAL JOIN to efficiently attach each assistant message
    to the most recent user message that preceded it in the same session.
    """
    filters = ["am.role = 'assistant'", "am.bert_score IS NOT NULL"]
    if min_f1 is not None:
        filters.append(f"(am.bert_score->>'f1')::float >= {float(min_f1)}")
    if max_f1 is not None:
        filters.append(f"(am.bert_score->>'f1')::float <= {float(max_f1)}")

    where_clause = " AND ".join(filters)

    rows = db.execute(text(f"""
        SELECT
            am.id          AS message_id,
            am.session_id,
            am.content     AS answer,
            am.bert_score,
            am.created_at,
            um.content     AS question
        FROM chat_messages am
        LEFT JOIN LATERAL (
            SELECT content
            FROM chat_messages
            WHERE session_id = am.session_id
              AND role = 'user'
              AND created_at <= am.created_at
            ORDER BY created_at DESC
            LIMIT 1
        ) um ON true
        WHERE {where_clause}
        ORDER BY am.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()

    total_row = db.execute(text(f"""
        SELECT COUNT(*) AS cnt
        FROM chat_messages am
        WHERE {where_clause}
    """)).mappings().one()

    items = [
        {
            "message_id": str(r["message_id"]),
            "session_id": str(r["session_id"]),
            "question": r["question"],
            "answer": r["answer"],
            "bert_score": r["bert_score"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

    return {"items": items, "total": total_row["cnt"], "offset": offset, "limit": limit}
