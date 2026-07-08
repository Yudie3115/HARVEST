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


def _provider_label(provider: str) -> str:
    return {
        "openai": "OpenAI",
        "groq": "Groq",
        "ollama": "Ollama",
    }.get(provider, provider.title())


def _provider_model(provider: str) -> str:
    if provider == "openai":
        return settings.openai_model
    if provider == "groq":
        return settings.groq_model
    if provider == "ollama":
        return settings.ollama_model
    return "default"


def _effective_provider() -> str:
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        return "ollama"
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        return "ollama"
    return settings.llm_provider


def _model_options() -> list[dict]:
    active_provider = _effective_provider()
    options = [
        {
            "value": active_provider,
            "provider": active_provider,
            "label": _provider_model(active_provider),
            "sub": _provider_label(active_provider),
            "is_default": True,
        }
    ]

    if settings.groq_api_key and active_provider != "groq":
        options.append(
            {
                "value": "groq",
                "provider": "groq",
                "label": settings.groq_model,
                "sub": "Groq",
                "is_default": False,
            }
        )

    if settings.openai_api_key and active_provider != "openai":
        options.append(
            {
                "value": "openai",
                "provider": "openai",
                "label": settings.openai_model,
                "sub": "OpenAI",
                "is_default": False,
            }
        )

    return options


def _select_llm_client(request: Request, model_preference: str | None, default_llm: LLMClient):
    if model_preference == "groq" and hasattr(request.app.state, "llm_client_groq"):
        return request.app.state.llm_client_groq
    if model_preference == "openai" and hasattr(request.app.state, "llm_client_openai"):
        return request.app.state.llm_client_openai
    return default_llm


@router.get("/chat/models")
async def chat_models() -> dict:
    """Return the chat model choices available to the public web client."""
    active_provider = _effective_provider()
    return {
        "active_provider": active_provider,
        "active_model": _provider_model(active_provider),
        "options": _model_options(),
    }


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
    active_llm = _select_llm_client(request, body.model_preference, llm_client)
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
    active_llm = _select_llm_client(request, body.model_preference, llm_client)

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
