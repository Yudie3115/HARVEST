"""Deterministic ordering helpers for persisted chat messages."""

from sqlalchemy import case

from src.storage.models import ChatMessage, MessageRoleEnum


def newest_first_message_order():
    """Return SQL ordering that keeps same-transaction question/answer pairs stable."""
    return (
        ChatMessage.created_at.desc(),
        case(
            (ChatMessage.role == MessageRoleEnum.assistant, 0),
            else_=1,
        ).asc(),
        ChatMessage.id.desc(),
    )
