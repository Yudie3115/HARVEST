"""
Chat endpoint — POST /chat
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_db,
    get_embedding_client,
    get_llm_client,
    get_translation_client,
    get_vector_db_client,
)
from src.api.models.requests import ChatRequest
from src.api.models.responses import ChatResponse
from src.api.services.chat_service import process_chat, process_chat_stream
from src.config.settings import settings
from src.llm.client import LLMClient
from src.llm.embeddings import EmbeddingClient
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(f"{settings.api_rate_limit_web}/hour")
async def chat(
    request: Request,  # required by slowapi
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    vector_db_client: VectorDBClient = Depends(get_vector_db_client),
    translation_client: TranslationClient = Depends(get_translation_client),
) -> ChatResponse:
    """Process a user message and return an AI-generated answer with sources."""
    if body.model_preference == "groq" and hasattr(request.app.state, "llm_client_groq"):
        active_llm = request.app.state.llm_client_groq
    elif body.model_preference == "openai" and hasattr(request.app.state, "llm_client_openai"):
        active_llm = request.app.state.llm_client_openai
    else:
        active_llm = llm_client
    try:
        return process_chat(
            request=body,
            db=db,
            llm_client=active_llm,
            embedding_client=embedding_client,
            vector_db_client=vector_db_client,
            translation_client=translation_client,
            background_tasks=background_tasks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Chat error for session {body.session_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@router.post("/chat/stream")
@limiter.limit(f"{settings.api_rate_limit_web}/hour")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    vector_db_client: VectorDBClient = Depends(get_vector_db_client),
    translation_client: TranslationClient = Depends(get_translation_client),
):
    """Stream a chat response as Server-Sent Events."""
    if body.model_preference == "groq" and hasattr(request.app.state, "llm_client_groq"):
        active_llm = request.app.state.llm_client_groq
    elif body.model_preference == "openai" and hasattr(request.app.state, "llm_client_openai"):
        active_llm = request.app.state.llm_client_openai
    else:
        active_llm = llm_client

    def _generate():
        yield from process_chat_stream(
            request=body,
            db=db,
            llm_client=active_llm,
            embedding_client=embedding_client,
            vector_db_client=vector_db_client,
            translation_client=translation_client,
            background_tasks=background_tasks,
        )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
