"""
WhatsApp webhook routes — Meta verification and inbound message handling.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from slowapi import Limiter
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_db,
    get_embedding_client,
    get_llm_client,
    get_translation_client,
    get_vector_db_client,
    get_whatsapp_service,
)
from src.api.models.requests import ChatRequest
from src.api.services.chat_service import process_chat
from src.api.services.whatsapp_service import WhatsAppService
from src.config.settings import settings
from src.llm.client import LLMClient
from src.llm.embeddings import EmbeddingClient
from src.storage.models import ChannelEnum, ChatSession
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient

# Rate-limit by phone number: the key is extracted from the request inside the handler.
def _phone_key(request: Request) -> str:
    """Extract sender phone from the parsed WhatsApp payload (best-effort)."""
    # slowapi calls this synchronously; we fall back to remote IP if unavailable.
    return getattr(request.state, "whatsapp_sender", request.client.host if request.client else "unknown")


limiter = Limiter(key_func=_phone_key)
router = APIRouter(tags=["whatsapp"])


@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(default=None, alias="hub.mode"),
    hub_verify_token: str = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str = Query(default=None, alias="hub.challenge"),
) -> int:
    """
    Meta webhook verification handshake.
    Returns hub.challenge as plain integer when the verify token matches.
    """
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="Invalid hub.mode")

    if hub_verify_token != settings.whatsapp_verify_token:
        logger.warning("WhatsApp webhook verify token mismatch")
        raise HTTPException(status_code=403, detail="Verify token mismatch")

    logger.info("WhatsApp webhook verified successfully")
    return int(hub_challenge)


@router.post("/whatsapp", status_code=200)
@limiter.limit(f"{settings.api_rate_limit_whatsapp}/hour")
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    vector_db_client: VectorDBClient = Depends(get_vector_db_client),
    translation_client: TranslationClient = Depends(get_translation_client),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> dict:
    """
    Receive inbound WhatsApp messages, run the RAG pipeline, and reply.

    Meta requires a 200 response within 20 s; processing happens inline here.
    For high-volume deployments consider offloading to a background task queue.
    """
    payload: dict = await request.json()

    # ----------------------------------------------------------------
    # Parse the Meta webhook payload
    # ----------------------------------------------------------------
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]["value"]
        message_obj = changes["messages"][0]
        sender_phone: str = message_obj["from"]
        message_text: str = message_obj["text"]["body"]
    except (KeyError, IndexError, TypeError):
        # Not a text message or unexpected payload structure — ack and ignore.
        logger.debug(f"WhatsApp webhook: unhandled payload type: {payload}")
        return {"status": "ignored"}

    # Store sender phone for the rate-limit key function
    request.state.whatsapp_sender = sender_phone

    logger.info(f"WhatsApp message from {sender_phone}: {message_text[:80]!r}")

    # ----------------------------------------------------------------
    # Look up or create a ChatSession for this phone number
    # ----------------------------------------------------------------
    chat_session: ChatSession | None = (
        db.query(ChatSession)
        .filter(
            ChatSession.channel == ChannelEnum.whatsapp,
            ChatSession.identifier == sender_phone,
        )
        .first()
    )

    if chat_session is None:
        chat_session = ChatSession(
            channel=ChannelEnum.whatsapp,
            identifier=sender_phone,
        )
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)
        logger.info(f"Created WhatsApp session {chat_session.id} for {sender_phone}")

    # ----------------------------------------------------------------
    # Run RAG pipeline
    # ----------------------------------------------------------------
    try:
        chat_response = process_chat(
            request=ChatRequest(
                session_id=str(chat_session.id),
                message=message_text,
            ),
            db=db,
            llm_client=llm_client,
            embedding_client=embedding_client,
            vector_db_client=vector_db_client,
            translation_client=translation_client,
        )
    except Exception as exc:
        logger.error(f"WhatsApp RAG pipeline error for {sender_phone}: {exc}")
        # Reply with a graceful error rather than timing out the webhook
        try:
            whatsapp_service.send_text(
                sender_phone,
                "Sorry, I could not process your message. Please try again later.",
            )
        except Exception:
            pass
        return {"status": "error"}

    # ----------------------------------------------------------------
    # Send reply
    # ----------------------------------------------------------------
    try:
        whatsapp_service.send_text(sender_phone, chat_response.answer)
    except Exception as exc:
        logger.error(f"Failed to send WhatsApp reply to {sender_phone}: {exc}")

    return {"status": "ok"}
