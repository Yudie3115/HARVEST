"""
Chat endpoint — POST /chat
"""
from fastapi import APIRouter, Depends, HTTPException, Request
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
from src.api.services.chat_service import process_chat
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
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    vector_db_client: VectorDBClient = Depends(get_vector_db_client),
    translation_client: TranslationClient = Depends(get_translation_client),
) -> ChatResponse:
    """Process a user message and return an AI-generated answer with sources."""
    try:
        return process_chat(
            request=body,
            db=db,
            llm_client=llm_client,
            embedding_client=embedding_client,
            vector_db_client=vector_db_client,
            translation_client=translation_client,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Chat error for session {body.session_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error.")
