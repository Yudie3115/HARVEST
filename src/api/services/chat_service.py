"""
Core RAG chat service — orchestrates translation, embedding, retrieval, and LLM synthesis.
"""
from typing import Generator, List
from urllib.parse import unquote, urlparse
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from src.api.models.requests import ChatRequest
from src.api.models.responses import ChatResponse, SourceRef, SuggestedQuestion
from src.api.services.catalogue_service import enqueue_candidate_job
from src.api.services.message_ordering import newest_first_message_order
from src.api.services.operational_metrics import CHAT_RETRIEVAL_METRIC, record_metric
from src.config.settings import settings
from src.llm.client import LLMClient, LLMContextTooLargeError
from src.llm.embeddings import EmbeddingClient
from src.storage.models import (
    CatalogueEntry,
    CatalogueStatusEnum,
    ChatMessage,
    ChatSession,
    Document,
    MessageRoleEnum,
)
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient

# Number of recent messages to load from DB (wider window for other future uses)
_HISTORY_WINDOW = 10
# Number of messages to actually send to the LLM as context (last 3 turn pairs)
_HISTORY_SEND_WINDOW = 6

_NO_RESULTS_ANSWER = (
    "I couldn't find relevant information in the knowledge base for this question. "
    "Try rephrasing, or browse Documents and the Catalogue for reviewed guidance."
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


def _top_score(search_results: list[dict]) -> float | None:
    scores = [
        float(hit["score"]) for hit in search_results if isinstance(hit.get("score"), (int, float))
    ]
    return max(scores) if scores else None


def _retrieval_outcome(search_results: list[dict], chunks: list[dict]) -> tuple[str, float | None]:
    top_score = _top_score(search_results)
    if not chunks:
        return "no_hits", top_score
    threshold = settings.chat_min_top_score
    if isinstance(threshold, (int, float)) and (top_score is None or top_score < threshold):
        return "below_min_top_score", top_score
    return "synthesized", top_score


def _record_retrieval(db: Session, outcome: str, top_score: float | None) -> None:
    """Commit immediately so this survives a downstream synthesis failure."""
    record_metric(
        db,
        CHAT_RETRIEVAL_METRIC,
        top_score if top_score is not None else 0.0,
        component="chat",
        unit="similarity",
        metadata={
            "outcome": outcome,
            "gate_enabled": isinstance(settings.chat_min_top_score, (int, float)),
        },
    )
    db.commit()


def _file_name(url: str | None) -> str | None:
    if not url:
        return None
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return name or None


def _build_sources(db: Session, search_results: list[dict]) -> list[SourceRef]:
    """Group cited chunks into document-level research references."""
    grouped: dict[str, SourceRef] = {}
    for citation_index, hit in enumerate(search_results, 1):
        payload = hit.get("payload", {})
        document = None
        document_id = payload.get("document_id")
        if document_id:
            try:
                candidate = db.get(Document, UUID(str(document_id)))
                if isinstance(candidate, Document):
                    document = candidate
            except (TypeError, ValueError):
                pass

        url = (
            (document.public_source_url or document.url)
            if document is not None
            else payload.get("source_url")
        )
        key = str(document.id) if document is not None else str(document_id or url or hit.get("id"))
        score = float(hit["score"]) if isinstance(hit.get("score"), (int, float)) else None
        text = payload.get("text", "")

        if key in grouped:
            reference = grouped[key]
            reference.citation_indices.append(citation_index)
            if score is not None and (reference.score is None or score > reference.score):
                reference.score = score
            continue

        classification = document.classification if document is not None else None
        summary = (
            classification.summary
            if classification is not None and isinstance(classification.summary, str)
            else None
        )
        topics = (
            list(classification.topics or [])
            if classification is not None
            else list(payload.get("topics") or [])
        )
        title = document.title if document is not None else payload.get("title")
        grouped[key] = SourceRef(
            title=title or _file_name(url) or "Untitled research source",
            url=url,
            site_name=document.site_name if document is not None else payload.get("site_name"),
            score=score,
            snippet=text[:320] if text else None,
            document_id=str(document.id)
            if document is not None
            else str(document_id or "") or None,
            summary=summary,
            document_type=(
                classification.document_category
                if classification is not None
                else payload.get("document_type")
            ),
            topics=topics[:6],
            citation_indices=[citation_index],
            library_url=(
                f"/documents/{document.id}"
                if document is not None and document.publicly_visible
                else None
            ),
        )
    return list(grouped.values())


def _catalogue_suggestions(
    db: Session,
    catalogue_vector_db_client: VectorDBClient | None,
    query_vector: list[float],
    language: str,
) -> list[dict]:
    if catalogue_vector_db_client is None:
        return []
    try:
        hits = catalogue_vector_db_client.search(
            query_vector=query_vector,
            top_k=5,
            score_threshold=settings.catalogue_match_observation_threshold,
        )
    except Exception as exc:
        logger.warning(f"Related catalogue search failed: {type(exc).__name__}")
        return []

    suggestions: list[dict] = []
    for hit in hits:
        score = hit.get("score")
        if not isinstance(score, (int, float)) or score < settings.catalogue_suggestion_threshold:
            continue
        try:
            entry_id = UUID(hit.get("payload", {}).get("catalogue_entry_id") or hit["id"])
        except (KeyError, TypeError, ValueError):
            continue
        entry = db.get(CatalogueEntry, entry_id)
        if not isinstance(entry, CatalogueEntry) or entry.status != CatalogueStatusEnum.approved:
            continue
        translated = (entry.question_translations or {}).get(language)
        suggestions.append(
            {
                "text": translated or entry.question_en,
                "kind": "catalogue",
                "catalogue_entry_id": str(entry.id),
            }
        )
        if len(suggestions) == 2:
            break
    return suggestions


def _suggest_questions(
    db: Session,
    *,
    llm_client: LLMClient,
    translation_client: TranslationClient,
    catalogue_vector_db_client: VectorDBClient | None,
    query_vector: list[float],
    question: str,
    answer: str | None,
    chunks: list[dict],
    language: str,
) -> list[SuggestedQuestion]:
    suggestions = _catalogue_suggestions(db, catalogue_vector_db_client, query_vector, language)
    generated: list[str] = []
    if answer and chunks:
        try:
            result = llm_client.suggest_followup_questions(question, answer, chunks)
            if isinstance(result, list):
                generated = [str(value).strip() for value in result if str(value).strip()]
        except Exception as exc:
            logger.warning(f"Follow-up generation failed: {type(exc).__name__}")

    if language != "eng":
        translated: list[str] = []
        for value in generated:
            try:
                translated.append(translation_client.translate_from_english(value, language))
            except Exception:
                translated.append(value)
        generated = translated

    seen = {item["text"].casefold() for item in suggestions}
    for text in generated:
        if text.casefold() in seen:
            continue
        suggestions.append({"text": text[:240], "kind": "generated"})
        seen.add(text.casefold())
        if len(suggestions) == 4:
            break
    return [SuggestedQuestion(**item) for item in suggestions]


def process_chat(
    request: ChatRequest,
    db: Session,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_db_client: VectorDBClient,
    translation_client: TranslationClient,
    catalogue_vector_db_client: VectorDBClient | None = None,
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
        .order_by(*newest_first_message_order())
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
    # No per-chunk score filter here — candidates are gated as a whole by
    # settings.chat_min_top_score below instead, so a paraphrase/synonym query
    # whose best chunk barely clears the bar still gets its full top-k of
    # supporting context rather than losing weaker (but still relevant) chunks.
    search_results = vector_db_client.search(
        query_vector=query_vector,
        top_k=5,
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
    retrieval_outcome, top_score = _retrieval_outcome(search_results, chunks)
    _record_retrieval(db, retrieval_outcome, top_score)
    if retrieval_outcome != "synthesized":
        suggestions = _suggest_questions(
            db,
            llm_client=llm_client,
            translation_client=translation_client,
            catalogue_vector_db_client=catalogue_vector_db_client,
            query_vector=query_vector,
            question=english_message,
            answer=None,
            chunks=[],
            language=detected_language,
        )
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
            suggested_questions=[item.model_dump() for item in suggestions],
        )
        db.add(user_msg)
        db.add(assistant_msg)
        from sqlalchemy.sql import func as sqlfunc

        chat_session.last_active_at = sqlfunc.now()
        db.commit()
        logger.info(
            f"Live synthesis skipped for session {request.session_id} "
            f"(outcome={retrieval_outcome}, top_score={top_score})"
        )
        return ChatResponse(
            answer=_NO_RESULTS_ANSWER,
            detected_language=detected_language,
            sources=[],
            session_id=request.session_id,
            no_results=True,
            suggested_questions=suggestions,
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
    # 9. Build document-level sources and useful next questions
    # ------------------------------------------------------------------
    sources = _build_sources(db, search_results)
    suggestions = _suggest_questions(
        db,
        llm_client=llm_client,
        translation_client=translation_client,
        catalogue_vector_db_client=catalogue_vector_db_client,
        query_vector=query_vector,
        question=english_message,
        answer=english_answer,
        chunks=chunks,
        language=detected_language,
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
        suggested_questions=[item.model_dump() for item in suggestions],
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
        suggested_questions=suggestions,
    )


def process_chat_stream(
    request: ChatRequest,
    db: Session,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_db_client: VectorDBClient,
    translation_client: TranslationClient,
    catalogue_vector_db_client: VectorDBClient | None = None,
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
        yield f"data: {_json.dumps({'type': 'status', 'stage': 'preparing'})}\n\n"
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
            .order_by(*newest_first_message_order())
            .limit(_HISTORY_WINDOW)
            .all()
        )
        recent_messages.reverse()

        # Language detection
        yield f"data: {_json.dumps({'type': 'status', 'stage': 'language'})}\n\n"
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
        yield f"data: {_json.dumps({'type': 'status', 'stage': 'searching'})}\n\n"
        query_vector = embedding_client.embed(english_message)
        search_results = vector_db_client.search(
            query_vector=query_vector,
            top_k=5,
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

        retrieval_outcome, top_score = _retrieval_outcome(search_results, chunks)
        _record_retrieval(db, retrieval_outcome, top_score)
        yield f"data: {_json.dumps({'type': 'status', 'stage': 'reading_sources', 'source_count': len(search_results)})}\n\n"

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
        if retrieval_outcome != "synthesized":
            suggestions = _suggest_questions(
                db,
                llm_client=llm_client,
                translation_client=translation_client,
                catalogue_vector_db_client=catalogue_vector_db_client,
                query_vector=query_vector,
                question=english_message,
                answer=None,
                chunks=[],
                language=detected_language,
            )
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
                suggested_questions=[item.model_dump() for item in suggestions],
            )
            db.add(user_msg)
            db.add(assistant_msg)
            from sqlalchemy.sql import func as sqlfunc

            chat_session.last_active_at = sqlfunc.now()
            db.commit()
            yield f"data: {_json.dumps({'type': 'done', 'answer': _NO_RESULTS_ANSWER, 'sources': [], 'suggested_questions': [item.model_dump() for item in suggestions], 'detected_language': detected_language, 'no_results': True, 'session_id': request.session_id})}\n\n"
            return

        # Stream tokens
        yield f"data: {_json.dumps({'type': 'status', 'stage': 'synthesizing', 'source_count': len(search_results)})}\n\n"
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

        # Build document-level sources and next questions while the completed
        # answer is already visible in the stream.
        sources = _build_sources(db, search_results)
        yield f"data: {_json.dumps({'type': 'status', 'stage': 'followups'})}\n\n"
        suggestions = _suggest_questions(
            db,
            llm_client=llm_client,
            translation_client=translation_client,
            catalogue_vector_db_client=catalogue_vector_db_client,
            query_vector=query_vector,
            question=english_message,
            answer=full_english_response,
            chunks=chunks,
            language=detected_language,
        )

        sources_dicts = [s.model_dump() for s in sources]

        # Persist messages
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
            content=final_answer,
            english_content=full_english_response if detected_language != "eng" else None,
            detected_language=detected_language,
            sources=sources_dicts,
            suggested_questions=[item.model_dump() for item in suggestions],
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

        yield f"data: {_json.dumps({'type': 'done', 'answer': final_answer, 'sources': sources_dicts, 'suggested_questions': [item.model_dump() for item in suggestions], 'detected_language': detected_language, 'no_results': False, 'session_id': request.session_id})}\n\n"

    except LLMContextTooLargeError:
        logger.warning(f"Context too large for session {request.session_id}")
        yield f"data: {_json.dumps({'type': 'error', 'message': _CONTEXT_TOO_LARGE_ANSWER})}\n\n"
    except Exception as exc:
        logger.error(f"Streaming chat error for session {request.session_id}: {exc}")
        yield f"data: {_json.dumps({'type': 'error', 'message': 'Internal server error'})}\n\n"
