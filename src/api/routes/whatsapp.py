"""
WhatsApp webhook routes — Meta verification and inbound message handling.
"""
import asyncio
import hashlib
import hmac
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
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
from src.api.services import access_service
from src.api.services.chat_service import process_chat
from src.llm.client import LLMContextTooLargeError
from src.api.services.whatsapp_service import WhatsAppService
from src.config.settings import settings
from src.llm.client import LLMClient
from src.llm.embeddings import EmbeddingClient
from src.storage.models import ChannelEnum, ChatSession
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient

router = APIRouter(tags=["whatsapp"])


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def _verify_signature(body: bytes, signature_header: str, app_secret: str) -> bool:
    """Return True iff the X-Hub-Signature-256 header matches the payload."""
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# Per-phone rate limiting (sliding window, in-memory)
# ---------------------------------------------------------------------------

_PHONE_TIMESTAMPS: dict[str, list[float]] = {}
_RATE_WINDOW = 3600.0  # seconds


def _is_rate_limited(phone: str, limit: int) -> bool:
    """Return True if *phone* has exceeded *limit* messages in the past hour."""
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW
    timestamps = [ts for ts in _PHONE_TIMESTAMPS.get(phone, []) if ts > cutoff]
    if len(timestamps) >= limit:
        _PHONE_TIMESTAMPS[phone] = timestamps
        return True
    timestamps.append(now)
    _PHONE_TIMESTAMPS[phone] = timestamps
    return False


# ---------------------------------------------------------------------------
# Message deduplication (bounded in-memory cache, 1-hour TTL)
# ---------------------------------------------------------------------------

_SEEN_IDS: OrderedDict[str, float] = OrderedDict()
_SEEN_IDS_MAX = 1000
_SEEN_IDS_TTL = 3600.0


def _is_duplicate(msg_id: str) -> bool:
    """Return True if *msg_id* was already processed within the TTL window."""
    now = time.monotonic()
    while _SEEN_IDS:
        oldest_id, ts = next(iter(_SEEN_IDS.items()))
        if now - ts > _SEEN_IDS_TTL:
            _SEEN_IDS.popitem(last=False)
        else:
            break
    if msg_id in _SEEN_IDS:
        return True
    _SEEN_IDS[msg_id] = now
    if len(_SEEN_IDS) > _SEEN_IDS_MAX:
        _SEEN_IDS.popitem(last=False)
    return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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

    Meta requires a 200 response within 20 s. High-volume deployments should
    move process_chat to a background task queue.
    """
    # ------------------------------------------------------------------
    # 1. Verify webhook signature (X-Hub-Signature-256)
    # ------------------------------------------------------------------
    body = await request.body()
    if settings.whatsapp_app_secret:
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(body, sig, settings.whatsapp_app_secret):
            logger.warning("WhatsApp webhook signature mismatch — request rejected")
            raise HTTPException(status_code=403, detail="Invalid signature")
    else:
        logger.warning("WHATSAPP_APP_SECRET not set — webhook signature verification is disabled")

    # ------------------------------------------------------------------
    # 2. Parse the Meta webhook payload
    # ------------------------------------------------------------------
    try:
        payload: dict = await request.json()
        entry = payload["entry"][0]
        changes = entry["changes"][0]["value"]
        message_obj = changes["messages"][0]
        sender_phone: str = message_obj["from"]
        msg_id: str = message_obj["id"]
    except (KeyError, IndexError, TypeError):
        logger.debug(f"WhatsApp webhook: unhandled payload structure: {payload!r}")
        return {"status": "ignored"}

    # ------------------------------------------------------------------
    # 3. Deduplicate — Meta retries on slow/failed responses
    # ------------------------------------------------------------------
    if _is_duplicate(msg_id):
        logger.info(f"Duplicate WhatsApp message {msg_id} from {sender_phone} — ignored")
        return {"status": "duplicate"}

    # ------------------------------------------------------------------
    # 4. Per-phone rate limiting
    # ------------------------------------------------------------------
    if _is_rate_limited(sender_phone, settings.api_rate_limit_whatsapp):
        logger.warning(f"WhatsApp rate limit exceeded for {sender_phone}")
        return {"status": "rate_limited"}

    # ------------------------------------------------------------------
    # 5. Non-text message handling
    # ------------------------------------------------------------------
    if message_obj.get("type") != "text" or "text" not in message_obj:
        logger.debug(
            f"WhatsApp non-text message from {sender_phone}: type={message_obj.get('type')!r}"
        )
        try:
            whatsapp_service.send_text(
                sender_phone,
                "I can only answer text questions — please type your question.",
            )
        except Exception:
            pass
        return {"status": "ignored"}

    message_text: str = message_obj["text"]["body"]
    # Compute this up front (pure, no DB access) so the log line below can avoid
    # writing a plaintext access code to the application log.
    code_shaped = access_service.is_code_format(message_text)
    if code_shaped:
        logger.info(f"WhatsApp message from {sender_phone}: [redacted access code]")
    else:
        logger.info(f"WhatsApp message from {sender_phone}: {message_text[:80]!r}")

    # ------------------------------------------------------------------
    # 6. Resolve any existing grant for this phone
    # ------------------------------------------------------------------
    resolved = access_service.resolve_whatsapp_grant(db, sender_phone)

    # ------------------------------------------------------------------
    # 7. Code-shaped messages are treated as a redemption attempt — this
    #    covers first-time redemption AND rebinding a replacement code over
    #    an existing (possibly revoked) grant. Exception: if the phone
    #    already has a resolved grant and the "code" doesn't match any real
    #    code (AccessInvalidError), it's most likely an ordinary short
    #    question that happened to normalize into the 3-word code shape
    #    (e.g. "dry my maize") — don't swallow it as a failed redemption
    #    attempt, fall through to the normal authorized-chat path instead.
    #    A real-but-revoked code (AccessRevokedError) is a different
    #    situation and keeps the existing invalid_code handling below.
    # ------------------------------------------------------------------
    if code_shaped:
        try:
            access_service.check_redemption_throttle(db, sender_phone)
        except access_service.RedemptionRateLimitedError:
            try:
                whatsapp_service.send_text(
                    sender_phone,
                    "Too many attempts. Please wait a while before trying another code.",
                )
            except Exception:
                pass
            return {"status": "redemption_rate_limited"}

        try:
            result = access_service.redeem_whatsapp_code(db, sender_phone, message_text)
        except access_service.AccessInvalidError:
            if resolved is None:
                access_service.record_failed_redemption_attempt(db, sender_phone)
                try:
                    whatsapp_service.send_text(
                        sender_phone,
                        "That code was not recognized. Please check it and try again.",
                    )
                except Exception:
                    pass
                return {"status": "invalid_code"}
            # Already-authorized phone — treat this as an ordinary chat question
            # rather than a failed redemption attempt. Falls through to step 9.
        except access_service.AccessError:
            access_service.record_failed_redemption_attempt(db, sender_phone)
            try:
                whatsapp_service.send_text(
                    sender_phone,
                    "That code was not recognized. Please check it and try again.",
                )
            except Exception:
                pass
            return {"status": "invalid_code"}
        else:
            access_service.clear_redemption_throttle(db, sender_phone)
            try:
                whatsapp_service.send_text(
                    sender_phone,
                    f"You're connected to {result.access_code.label}. "
                    "Send your post-harvest question any time.",
                )
            except Exception:
                pass
            return {"status": "redeemed"}

    # ------------------------------------------------------------------
    # 8. No grant and a non-code message — prompt for a code, don't chat
    # ------------------------------------------------------------------
    if resolved is None:
        try:
            whatsapp_service.send_text(
                sender_phone,
                "Welcome! To ask a question, first send your 3-word access code "
                "(e.g. mango-river-granary).",
            )
        except Exception:
            pass
        return {"status": "awaiting_code"}

    # ------------------------------------------------------------------
    # 9. Gate on code status and reserve quota before entering the RAG pipeline
    # ------------------------------------------------------------------
    try:
        access_service.require_active_code(resolved.access_code)
        access_service.reserve_quota(db, resolved.access_code.id)
    except access_service.AccessRevokedError:
        try:
            whatsapp_service.send_text(
                sender_phone,
                "This group's access has been revoked. Contact your administrator for a replacement code.",
            )
        except Exception:
            pass
        return {"status": "access_revoked"}
    except access_service.QuotaExhaustedError:
        try:
            whatsapp_service.send_text(
                sender_phone,
                "This group's messages have been used for this month. Try again next month.",
            )
        except Exception:
            pass
        return {"status": "quota_exhausted"}
    except access_service.GlobalLimitReachedError:
        try:
            whatsapp_service.send_text(
                sender_phone,
                "The service is at capacity right now. Please try again later.",
            )
        except Exception:
            pass
        return {"status": "global_limit_reached"}

    # ------------------------------------------------------------------
    # 10. Look up or create a ChatSession for this phone, owned by the grant
    # ------------------------------------------------------------------
    chat_session: ChatSession | None = (
        db.query(ChatSession)
        .filter(
            ChatSession.channel == ChannelEnum.whatsapp,
            ChatSession.identifier == sender_phone,
            ChatSession.access_grant_id == resolved.grant.id,
        )
        .first()
    )

    if chat_session is None:
        chat_session = ChatSession(
            channel=ChannelEnum.whatsapp,
            identifier=sender_phone,
            access_grant_id=resolved.grant.id,
        )
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)
        logger.info(f"Created WhatsApp session {chat_session.id} for {sender_phone}")

    # ------------------------------------------------------------------
    # 11. Run RAG pipeline with a 15-second timeout
    # ------------------------------------------------------------------
    try:
        chat_response = await asyncio.wait_for(
            asyncio.to_thread(
                process_chat,
                request=ChatRequest(
                    session_id=str(chat_session.id),
                    message=message_text,
                ),
                db=db,
                llm_client=llm_client,
                embedding_client=embedding_client,
                vector_db_client=vector_db_client,
                translation_client=translation_client,
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"RAG pipeline timed out for {sender_phone}")
        try:
            whatsapp_service.send_text(
                sender_phone,
                "Sorry, your request took too long to process. Please try again.",
            )
        except Exception:
            pass
        return {"status": "timeout"}
    except LLMContextTooLargeError:
        logger.warning(f"Context too large for WhatsApp session {sender_phone}")
        try:
            whatsapp_service.send_text(
                sender_phone,
                "This conversation has become too long for me to process. "
                "Please send your question again as a new message.",
            )
        except Exception:
            pass
        return {"status": "context_too_large"}
    except Exception as exc:
        logger.error(f"WhatsApp RAG pipeline error for {sender_phone}: {exc}")
        try:
            whatsapp_service.send_text(
                sender_phone,
                "Sorry, I could not process your message. Please try again later.",
            )
        except Exception:
            pass
        return {"status": "error"}

    # ------------------------------------------------------------------
    # 12. Send reply
    # ------------------------------------------------------------------
    try:
        whatsapp_service.send_text(sender_phone, chat_response.answer)
    except Exception as exc:
        logger.error(f"Failed to send WhatsApp reply to {sender_phone}: {exc}")

    return {"status": "ok"}
