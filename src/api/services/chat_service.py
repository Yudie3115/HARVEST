"""
Core RAG chat service — orchestrates translation, embedding, retrieval, and LLM synthesis.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import BackgroundTasks
from loguru import logger
from sqlalchemy.orm import Session

from src.api.models.requests import ChatRequest
from src.api.models.responses import ChatResponse, SourceRef
from src.llm.client import LLMClient
from src.llm.embeddings import EmbeddingClient
from src.storage.models import ChatMessage, ChatSession, MessageRoleEnum
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient

# Number of recent messages to load from DB (wider window for other future uses)
_HISTORY_WINDOW = 10
# Number of messages to actually send to the LLM as context (last 3 turn pairs)
_HISTORY_SEND_WINDOW = 6


def process_chat(
    request: ChatRequest,
    db: Session,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_db_client: VectorDBClient,
    translation_client: TranslationClient,
    background_tasks: Optional[BackgroundTasks] = None,
) -> ChatResponse:
    """
    Orchestrate the full RAG pipeline for a single chat turn.

    Steps
    -----
    1. Resolve the ChatSession row (raises ValueError if not found).
    2. Load the last _HISTORY_WINDOW messages for context.
    3. Detect / override the language of the incoming message.
    4. Translate the message to English if needed.
    5. Embed the English message and search Qdrant.
    6. Synthesise an answer via the LLM.
    7. Translate the answer back to the detected language if needed.
    8. Persist both user and assistant messages.
    9. Return ChatResponse.
    """
    session_uuid = UUID(request.session_id)

    # ------------------------------------------------------------------
    # 1. Resolve chat session
    # ------------------------------------------------------------------
    chat_session: ChatSession | None = db.get(ChatSession, session_uuid)
    if chat_session is None:
        raise ValueError(f"Session not found: {request.session_id}")

    # ------------------------------------------------------------------
    # 2. Load recent history (for potential future use / context)
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
    search_results = vector_db_client.search(query_vector=query_vector, top_k=10)

    # Build chunks list expected by LLMClient.answer_question()
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
    # 6. Build conversation history for multi-turn context
    # ------------------------------------------------------------------
    history_turns = [
        {"role": msg.role.value if hasattr(msg.role, "value") else msg.role, "content": msg.content}
        for msg in recent_messages[-_HISTORY_SEND_WINDOW:]
    ] or None

    # ------------------------------------------------------------------
    # 7. Synthesise answer
    # ------------------------------------------------------------------
    english_answer = llm_client.answer_question(
        question=english_message,
        chunks=chunks,
        history=history_turns,
    )

    # ------------------------------------------------------------------
    # 8. Translate answer back if needed
    # ------------------------------------------------------------------
    final_answer = english_answer
    if detected_language != "eng":
        try:
            final_answer = translation_client.translate_from_english(
                english_answer, detected_language
            )
            logger.debug(
                f"Translated answer from English to {detected_language}"
            )
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
        sources.append(
            SourceRef(
                title=payload.get("title"),
                url=url,
                site_name=payload.get("site_name"),
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
        detected_language=detected_language,
        sources=sources_dicts,
    )
    db.add(assistant_msg)

    # Touch last_active_at on the session
    from sqlalchemy.sql import func as sqlfunc
    chat_session.last_active_at = sqlfunc.now()

    db.commit()

    # ------------------------------------------------------------------
    # 11. Schedule faithfulness scoring (off critical path)
    # ------------------------------------------------------------------
    if background_tasks is not None:
        from src.config.settings import settings as _settings
        if _settings.bertscore_enabled and chunks:
            from src.llm.bert_scoring import score_message_background
            background_tasks.add_task(
                score_message_background,
                message_id=str(assistant_msg.id),
                candidate=english_answer,
                references=[c["text"] for c in chunks],
            )

    logger.info(
        f"Chat turn complete for session {request.session_id} "
        f"(lang={detected_language}, sources={len(sources)})"
    )

    return ChatResponse(
        answer=final_answer,
        detected_language=detected_language,
        sources=sources,
        session_id=request.session_id,
    )
