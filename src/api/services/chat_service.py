"""
Core RAG chat service — orchestrates translation, embedding, retrieval, and LLM synthesis.
"""
from typing import Generator, List
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from src.api.models.requests import ChatRequest
from src.api.models.responses import ChatResponse, SourceRef
from src.api.services.catalogue_service import enqueue_candidate_job
from src.config.settings import settings
from src.llm.client import LLMClient, LLMContextTooLargeError
from src.llm.embeddings import EmbeddingClient
from src.storage.models import ChatMessage, ChatSession, MessageRoleEnum
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient

# Number of recent messages to load from DB (wider window for other future uses)
_HISTORY_WINDOW = 10
# Number of messages to actually send to the LLM as context (last 3 turn pairs)
_HISTORY_SEND_WINDOW = 6

_NO_RESULTS_ANSWER = (
    "I couldn't find relevant information in the knowledge base for this question. "
    "Try rephrasing, or ask about post-harvest storage, drying, pest control, or handling practices."
)

_CONTEXT_TOO_LARGE_ANSWER = (
    "This conversation has grown too long for the current model to handle. "
    "Please start a new chat, or switch to GPT-4o Mini which supports longer conversations."
)


def _history_content(msg: ChatMessage) -> str:
    role = msg.role.value if hasattr(msg.role, "value") else msg.role
    english_content = getattr(msg, "english_content", None)
    if role == "assistant" and isinstance(english_content, str) and english_content:
        return english_content
    return msg.content


def process_chat(
    request: ChatRequest,
    db: Session,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_db_client: VectorDBClient,
    translation_client: TranslationClient,
) -> ChatResponse:
    """
    Orchestrate the full RAG pipeline for a single chat turn.

    Steps
    -----
    1. Resolve the ChatSession row (raises ValueError if not found).
    2. Load the last _HISTORY_WINDOW messages for context.
    3. Detect / override the language of the incoming message.
    4. Translate the message to English if needed.
    5. Embed the English message and search the configured vector DB.
    5b. No-results shortcut — skip LLM if no relevant chunks found.
    6. Build conversation history for multi-turn context.
    7. Synthesise an answer via the LLM.
    8. Translate the answer back to the detected language if needed.
    9. Build sources from chunk payloads.
    10. Persist both user and assistant messages.
    11. Enqueue a durable catalogue candidate job (scored off critical path by the worker).
    """
    session_uuid = UUID(request.session_id)

    # ------------------------------------------------------------------
    # 1. Resolve chat session
    # ------------------------------------------------------------------
    chat_session: ChatSession | None = db.get(ChatSession, session_uuid)
    if chat_session is None:
        raise ValueError(f"Session not found: {request.session_id}")

    # ------------------------------------------------------------------
    # 2. Load recent history
    # ------------------------------------------------------------------
    recent_messages: List[ChatMessage] = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_uuid)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_WINDOW)
        .all()
    )
    recent_messages.reverse()  # chronological order

    # ------------------------------------------------------------------
    # 3. Detect / override language
    # ------------------------------------------------------------------
    detected_language = "eng"  # default — English

    if request.language_override:
        detected_language = request.language_override
        logger.debug(f"Language override applied: {detected_language}")
    else:
        try:
            lang = translation_client.detect_language(request.message)
            if lang:
                detected_language = lang
                logger.debug(f"Detected language: {detected_language}")
        except Exception as exc:
            logger.warning(f"Language detection failed, defaulting to English: {exc}")

    # ------------------------------------------------------------------
    # 4. Translate message to English if needed
    # ------------------------------------------------------------------
    english_message = request.message
    if detected_language != "eng":
        try:
            english_message = translation_client.translate_to_english(
                request.message, detected_language
            )
            logger.debug(
                f"Translated message from {detected_language} to English "
                f"({len(request.message)} → {len(english_message)} chars)"
            )
        except Exception as exc:
            logger.warning(
                f"Translation to English failed, proceeding with original message: {exc}"
            )
            english_message = request.message

    # ------------------------------------------------------------------
    # 5. Embed and search
    # ------------------------------------------------------------------
    query_vector = embedding_client.embed(english_message)
    search_results = vector_db_client.search(
        query_vector=query_vector,
        top_k=5,
        score_threshold=settings.chat_score_threshold,
    )

    chunks = [
        {
            "text": hit["payload"].get("text", ""),
            "source_url": hit["payload"].get("source_url", ""),
            "title": hit["payload"].get("title"),
            "site_name": hit["payload"].get("site_name"),
        }
        for hit in search_results
        if hit.get("payload", {}).get("text")
    ]

    # ------------------------------------------------------------------
    # 5b. No-results shortcut — skip LLM if no relevant chunks found
    # ------------------------------------------------------------------
    if not chunks:
        user_msg = ChatMessage(
            session_id=session_uuid,
            role=MessageRoleEnum.user,
            content=request.message,
            detected_language=detected_language,
            sources=None,
        )
        assistant_msg = ChatMessage(
            session_id=session_uuid,
            role=MessageRoleEnum.assistant,
            content=_NO_RESULTS_ANSWER,
            detected_language=detected_language,
            sources=[],
        )
        db.add(user_msg)
        db.add(assistant_msg)
        from sqlalchemy.sql import func as sqlfunc
        chat_session.last_active_at = sqlfunc.now()
        db.commit()
        logger.info(f"No relevant chunks for session {request.session_id}")
        return ChatResponse(
            answer=_NO_RESULTS_ANSWER,
            detected_language=detected_language,
            sources=[],
            session_id=request.session_id,
            no_results=True,
        )

    # ------------------------------------------------------------------
    # 6. Build conversation history for multi-turn context
    # ------------------------------------------------------------------
    history_turns = [
        {
            "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
            "content": _history_content(msg),
        }
        for msg in recent_messages[-_HISTORY_SEND_WINDOW:]
    ] or None

    # ------------------------------------------------------------------
    # 7. Synthesise answer
    # ------------------------------------------------------------------
    try:
        english_answer = llm_client.answer_question(
            question=english_message,
            chunks=chunks,
            history=history_turns,
        )
    except LLMContextTooLargeError:
        logger.warning(f"Context too large for session {request.session_id}")
        raise

    # ------------------------------------------------------------------
    # 8. Translate answer back if needed
    # ------------------------------------------------------------------
    final_answer = english_answer
    if detected_language != "eng":
        try:
            final_answer = translation_client.translate_from_english(
                english_answer, detected_language
            )
            logger.debug(f"Translated answer from English to {detected_language}")
        except Exception as exc:
            logger.warning(
                f"Translation back to {detected_language} failed, returning English answer: {exc}"
            )
            final_answer = english_answer

    # ------------------------------------------------------------------
    # 9. Build sources from chunk payloads
    # ------------------------------------------------------------------
    sources: List[SourceRef] = []
    seen_urls: set[str] = set()
    for hit in search_results:
        payload = hit.get("payload", {})
        url = payload.get("source_url")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        text = payload.get("text", "")
        sources.append(
            SourceRef(
                title=payload.get("title"),
                url=url,
                site_name=payload.get("site_name"),
                score=hit.get("score"),
                snippet=text[:200] if text else None,
            )
        )

    sources_dicts = [s.model_dump() for s in sources]

    # ------------------------------------------------------------------
    # 10. Persist messages
    # ------------------------------------------------------------------
    user_msg = ChatMessage(
        session_id=session_uuid,
        role=MessageRoleEnum.user,
        content=request.message,
        detected_language=detected_language,
        sources=None,
    )
    db.add(user_msg)

    assistant_msg = ChatMessage(
        session_id=session_uuid,
        role=MessageRoleEnum.assistant,
        content=final_answer,
        english_content=english_answer if detected_language != "eng" else None,
        detected_language=detected_language,
        sources=sources_dicts,
    )
    db.add(assistant_msg)
    db.flush()
    enqueue_candidate_job(
        db,
        assistant_message_id=assistant_msg.id,
        source_chunk_ids=[hit["id"] for hit in search_results],
    )

    from sqlalchemy.sql import func as sqlfunc
    chat_session.last_active_at = sqlfunc.now()
    db.commit()

    logger.info(
        f"Chat turn complete for session {request.session_id} "
        f"(lang={detected_language}, sources={len(sources)})"
    )

    return ChatResponse(
        answer=final_answer,
        detected_language=detected_language,
        sources=sources,
        session_id=request.session_id,
        no_results=False,
    )


def process_chat_stream(
    request: ChatRequest,
    db: Session,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_db_client: VectorDBClient,
    translation_client: TranslationClient,
) -> Generator[str, None, None]:
    """
    SSE generator for streaming chat responses.

    Yields lines in the format ``data: <json>\\n\\n`` where the JSON is one of:
      {"type": "token",  "content": "..."}
      {"type": "done",   "answer": "...", "sources": [...], "detected_language": "eng",
                         "no_results": false, "session_id": "..."}
      {"type": "error",  "message": "..."}
    """
    import json as _json

    try:
        session_uuid = UUID(request.session_id)
        chat_session: ChatSession | None = db.get(ChatSession, session_uuid)
        if chat_session is None:
            yield "data: " + _json.dumps(
                {
                    "type": "error",
                    "code": "session_not_found",
                    "status": 404,
                    "message": "Session not found",
                }
            ) + "\n\n"
            return

        # Load recent history
        recent_messages: List[ChatMessage] = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_uuid)
            .order_by(ChatMessage.created_at.desc())
            .limit(_HISTORY_WINDOW)
            .all()
        )
        recent_messages.reverse()

        # Language detection
        detected_language = "eng"
        if request.language_override:
            detected_language = request.language_override
        else:
            try:
                lang = translation_client.detect_language(request.message)
                if lang:
                    detected_language = lang
            except Exception as exc:
                logger.warning(f"Language detection failed: {exc}")

        # Translate to English
        english_message = request.message
        if detected_language != "eng":
            try:
                english_message = translation_client.translate_to_english(
                    request.message, detected_language
                )
            except Exception as exc:
                logger.warning(f"Translation to English failed: {exc}")

        # Embed + search
        query_vector = embedding_client.embed(english_message)
        search_results = vector_db_client.search(
            query_vector=query_vector,
            top_k=5,
            score_threshold=settings.chat_score_threshold,
        )

        chunks = [
            {
                "text": hit["payload"].get("text", ""),
                "source_url": hit["payload"].get("source_url", ""),
                "title": hit["payload"].get("title"),
                "site_name": hit["payload"].get("site_name"),
            }
            for hit in search_results
            if hit.get("payload", {}).get("text")
        ]

        # History turns — use English content for assistant messages to avoid
        # tokenization overhead from non-Latin scripts in history
        history_turns = [
            {
                "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                "content": _history_content(msg),
            }
            for msg in recent_messages[-_HISTORY_SEND_WINDOW:]
        ] or None

        # No-results shortcut
        if not chunks:
            user_msg = ChatMessage(
                session_id=session_uuid, role=MessageRoleEnum.user,
                content=request.message, detected_language=detected_language, sources=None,
            )
            assistant_msg = ChatMessage(
                session_id=session_uuid, role=MessageRoleEnum.assistant,
                content=_NO_RESULTS_ANSWER, detected_language=detected_language, sources=[],
            )
            db.add(user_msg)
            db.add(assistant_msg)
            from sqlalchemy.sql import func as sqlfunc
            chat_session.last_active_at = sqlfunc.now()
            db.commit()
            yield f"data: {_json.dumps({'type': 'done', 'answer': _NO_RESULTS_ANSWER, 'sources': [], 'detected_language': detected_language, 'no_results': True, 'session_id': request.session_id})}\n\n"
            return

        # Stream tokens
        full_english_response = ""
        for token in llm_client.stream_answer(
            question=english_message, chunks=chunks, history=history_turns
        ):
            full_english_response += token
            yield f"data: {_json.dumps({'type': 'token', 'content': token})}\n\n"

        # Translate answer back
        final_answer = full_english_response
        if detected_language != "eng":
            try:
                final_answer = translation_client.translate_from_english(
                    full_english_response, detected_language
                )
            except Exception as exc:
                logger.warning(f"Translation back to {detected_language} failed: {exc}")

        # Build sources
        sources: List[SourceRef] = []
        seen_urls: set[str] = set()
        for hit in search_results:
            payload = hit.get("payload", {})
            url = payload.get("source_url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            text = payload.get("text", "")
            sources.append(
                SourceRef(
                    title=payload.get("title"),
                    url=url,
                    site_name=payload.get("site_name"),
                    score=hit.get("score"),
                    snippet=text[:200] if text else None,
                )
            )

        sources_dicts = [s.model_dump() for s in sources]

        # Persist messages
        user_msg = ChatMessage(
            session_id=session_uuid, role=MessageRoleEnum.user,
            content=request.message, detected_language=detected_language, sources=None,
        )
        assistant_msg = ChatMessage(
            session_id=session_uuid, role=MessageRoleEnum.assistant,
            content=final_answer,
            english_content=full_english_response if detected_language != "eng" else None,
            detected_language=detected_language, sources=sources_dicts,
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.flush()
        enqueue_candidate_job(
            db,
            assistant_message_id=assistant_msg.id,
            source_chunk_ids=[hit["id"] for hit in search_results],
        )
        from sqlalchemy.sql import func as sqlfunc
        chat_session.last_active_at = sqlfunc.now()
        db.commit()

        logger.info(
            f"Streaming chat turn complete for session {request.session_id} "
            f"(lang={detected_language}, sources={len(sources)})"
        )

        yield f"data: {_json.dumps({'type': 'done', 'answer': final_answer, 'sources': sources_dicts, 'detected_language': detected_language, 'no_results': False, 'session_id': request.session_id})}\n\n"

    except LLMContextTooLargeError:
        logger.warning(f"Context too large for session {request.session_id}")
        yield f"data: {_json.dumps({'type': 'error', 'message': _CONTEXT_TOO_LARGE_ANSWER})}\n\n"
    except Exception as exc:
        logger.error(f"Streaming chat error for session {request.session_id}: {exc}")
        yield f"data: {_json.dumps({'type': 'error', 'message': 'Internal server error'})}\n\n"
