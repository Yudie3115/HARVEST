"""
Session management routes — create sessions and retrieve history.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.models.requests import NewSessionRequest
from src.api.models.responses import HistoryMessage, SessionHistoryResponse, SessionResponse, SourceRef
from src.storage.models import ChannelEnum, ChatMessage, ChatSession

router = APIRouter(tags=["session"])

_HISTORY_LIMIT = 50


@router.post("/new", response_model=SessionResponse, status_code=201)
async def create_session(
    body: NewSessionRequest,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Create a new chat session and return its ID."""
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
    )
    db.add(chat_session)
    db.commit()
    db.refresh(chat_session)

    logger.info(f"Created chat session {chat_session.id} (channel={channel})")

    return SessionResponse(
        session_id=str(chat_session.id),
        channel=chat_session.channel.value,
    )


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
) -> SessionHistoryResponse:
    """Return the last 50 messages for a session."""
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id format.")

    chat_session: ChatSession | None = db.get(ChatSession, session_uuid)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages: list[ChatMessage] = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_uuid)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_LIMIT)
        .all()
    )
    messages.reverse()  # return in chronological order

    history = [
        HistoryMessage(
            role=msg.role.value,
            content=msg.content,
            detected_language=msg.detected_language,
            sources=(
                [SourceRef(**s) for s in msg.sources]
                if msg.sources
                else None
            ),
        )
        for msg in messages
    ]

    return SessionHistoryResponse(
        session_id=session_id,
        messages=history,
    )
