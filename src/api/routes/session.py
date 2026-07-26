"""
Session management routes — create sessions and retrieve history.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_web_grant
from src.api.models.requests import CatalogueSessionRequest, NewSessionRequest
from src.api.models.responses import (
    HistoryMessage,
    SessionHistoryResponse,
    SessionResponse,
    SourceRef,
    SuggestedQuestion,
    ThreadListResponse,
    ThreadSummary,
)
from src.api.services import access_service
from src.api.services.access_service import ResolvedGrant, SessionForbiddenError
from src.api.services.message_ordering import newest_first_message_order
from src.storage.models import (
    CatalogueEntry,
    CatalogueStatusEnum,
    ChannelEnum,
    ChatMessage,
    ChatSession,
    MessageRoleEnum,
)

router = APIRouter(tags=["session"])

_HISTORY_LIMIT = 50
_THREAD_LIMIT = 50
_THREAD_TITLE_LIMIT = 80


def _thread_title(first_question: str | None) -> str:
    if not first_question:
        return "New chat"
    title = " ".join(first_question.split())
    if len(title) <= _THREAD_TITLE_LIMIT:
        return title
    return f"{title[:_THREAD_TITLE_LIMIT - 1].rstrip()}…"


@router.post("/new", response_model=SessionResponse, status_code=201)
async def create_session(
    body: NewSessionRequest,
    db: Session = Depends(get_db),
    resolved: ResolvedGrant = Depends(get_web_grant),
) -> SessionResponse:
    """Create a new chat session owned by the caller's access grant."""
    access_service.require_active_code(resolved.access_code)

    try:
        channel = ChannelEnum(body.channel)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid channel '{body.channel}'. Must be 'web' or 'whatsapp'.",
        )

    import uuid

    chat_session = ChatSession(
        channel=channel,
        identifier=str(uuid.uuid4()),  # web sessions use a generated UUID as identifier
        access_grant_id=resolved.grant.id,
    )
    db.add(chat_session)
    db.commit()
    db.refresh(chat_session)

    logger.info(
        f"Created chat session {chat_session.id} (channel={channel}, grant={resolved.grant.id})"
    )

    return SessionResponse(
        session_id=str(chat_session.id),
        channel=chat_session.channel.value,
    )


@router.post("/from-catalogue", response_model=SessionResponse, status_code=201)
async def create_session_from_catalogue(
    body: CatalogueSessionRequest,
    db: Session = Depends(get_db),
    resolved: ResolvedGrant = Depends(get_web_grant),
) -> SessionResponse:
    """Create a grant-owned web session seeded with one approved catalogue Q&A."""
    access_service.require_active_code(resolved.access_code)
    try:
        entry_id = UUID(body.catalogue_entry_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid catalogue_entry_id format.")

    entry = db.get(CatalogueEntry, entry_id)
    if entry is None or entry.status != CatalogueStatusEnum.approved:
        raise HTTPException(status_code=404, detail="Catalogue entry not found.")

    import uuid

    chat_session = ChatSession(
        channel=ChannelEnum.web,
        identifier=str(uuid.uuid4()),
        access_grant_id=resolved.grant.id,
    )
    db.add(chat_session)
    db.flush()
    db.add_all(
        [
            ChatMessage(
                session_id=chat_session.id,
                role=MessageRoleEnum.user,
                content=entry.question_en,
                detected_language="eng",
            ),
            ChatMessage(
                session_id=chat_session.id,
                role=MessageRoleEnum.assistant,
                content=entry.answer_en,
                detected_language="eng",
                sources=_catalogue_sources(db, entry),
            ),
        ]
    )
    db.commit()
    db.refresh(chat_session)
    return SessionResponse(session_id=str(chat_session.id), channel=chat_session.channel.value)


def _catalogue_sources(db: Session, entry: CatalogueEntry) -> list[dict]:
    if entry.source_message_id is None:
        return []
    source_message = db.get(ChatMessage, entry.source_message_id)
    return list(source_message.sources or []) if source_message else []


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    db: Session = Depends(get_db),
    resolved: ResolvedGrant = Depends(get_web_grant),
) -> ThreadListResponse:
    """List recent web chat threads owned by the caller's access grant."""
    access_service.require_active_code(resolved.access_code)

    first_question = (
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == ChatSession.id,
            ChatMessage.role == MessageRoleEnum.user,
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .limit(1)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    message_count = (
        select(func.count(ChatMessage.id))
        .where(ChatMessage.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )

    rows = (
        db.query(
            ChatSession,
            first_question.label("first_question"),
            message_count.label("message_count"),
        )
        .filter(
            ChatSession.access_grant_id == resolved.grant.id,
            ChatSession.channel == ChannelEnum.web,
            ChatSession.messages.any(),
        )
        .order_by(ChatSession.last_active_at.desc(), ChatSession.created_at.desc())
        .limit(_THREAD_LIMIT)
        .all()
    )

    return ThreadListResponse(
        items=[
            ThreadSummary(
                session_id=str(chat_session.id),
                title=_thread_title(question),
                message_count=count,
                created_at=chat_session.created_at,
                updated_at=chat_session.last_active_at or chat_session.created_at,
            )
            for chat_session, question, count in rows
        ]
    )


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    resolved: ResolvedGrant = Depends(get_web_grant),
) -> SessionHistoryResponse:
    """Return the last 50 messages for a session owned by the caller's access grant."""
    access_service.require_active_code(resolved.access_code)

    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id format.")

    chat_session: ChatSession | None = db.get(ChatSession, session_uuid)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if chat_session.access_grant_id != resolved.grant.id:
        raise SessionForbiddenError("This session belongs to a different access grant.")

    messages: list[ChatMessage] = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_uuid)
        .order_by(*newest_first_message_order())
        .limit(_HISTORY_LIMIT)
        .all()
    )
    messages.reverse()  # return in chronological order

    history = [
        HistoryMessage(
            role=msg.role.value,
            content=msg.content,
            detected_language=msg.detected_language,
            sources=([SourceRef(**s) for s in msg.sources] if msg.sources else None),
            suggested_questions=[
                SuggestedQuestion(**item) for item in (msg.suggested_questions or [])
            ],
        )
        for msg in messages
    ]

    return SessionHistoryResponse(
        session_id=session_id,
        messages=history,
    )
