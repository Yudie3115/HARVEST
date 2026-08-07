"""
PostHarvest Knowledge API — FastAPI application entry point.

Start with:
    uvicorn src.api.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from openai import RateLimitError as OpenAIRateLimitError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config.settings import settings
from src.api.routes import (
    access,
    admin,
    admin_access,
    admin_catalogue,
    catalogue,
    chat,
    health,
    library,
    session,
    whatsapp,
)
from src.api.errors import llm_rate_limit_handler
from src.api.services.access_service import AccessError, access_error_handler


# ---------------------------------------------------------------------------
# Lifespan — initialise and teardown all service clients once
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create service clients on startup and cleanly dispose them on shutdown."""
    logger.info("Starting PostHarvest Knowledge API …")

    # Lazy imports so that import errors surface at startup, not at module load
    from src.llm.client import LLMClient
    from src.llm.embeddings import EmbeddingClient
    from src.storage.postgres import PostgresClient
    from src.storage.vector_db import VectorDBClient
    from src.translation.client import TranslationClient
    from src.api.services.whatsapp_service import WhatsAppService

    # Bring the schema up to date (creates tables and applies any pending
    # column/index changes — safe to run on every startup)
    from src.storage.migrations import upgrade_to_head
    upgrade_to_head()

    postgres_client = PostgresClient()

    app.state.postgres_client = postgres_client
    app.state.llm_client = LLMClient()
    if settings.groq_api_key:
        app.state.llm_client_groq = LLMClient(provider="groq")
    if settings.openai_api_key:
        app.state.llm_client_openai = LLMClient(provider="openai")
    app.state.embedding_client = EmbeddingClient()
    app.state.vector_db_client = VectorDBClient()
    app.state.catalogue_vector_db_client = VectorDBClient(
        collection=settings.catalogue_collection_name
    )
    app.state.vector_db_client.ensure_collection()
    app.state.catalogue_vector_db_client.ensure_collection()
    app.state.translation_client = TranslationClient()
    app.state.whatsapp_service = WhatsAppService(
        token=settings.whatsapp_token,
        phone_number_id=settings.whatsapp_phone_number_id,
    )

    logger.info("All service clients initialised — API ready.")

    yield  # application is running

    # Shutdown
    logger.info("Shutting down PostHarvest Knowledge API …")
    postgres_client.close()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PostHarvest Knowledge API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Rate limiter (global — per-route limits are applied in each router)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(AccessError, access_error_handler)
# openai.RateLimitError — covers Groq too, which uses the same SDK.
app.add_exception_handler(OpenAIRateLimitError, llm_rate_limit_handler)

# Routers
app.include_router(health.router)
app.include_router(session.router, prefix="/session")
app.include_router(chat.router)
app.include_router(whatsapp.router, prefix="/webhook")
app.include_router(admin.router)
app.include_router(admin_access.router)
app.include_router(access.router)
app.include_router(library.router)
app.include_router(catalogue.router)
app.include_router(admin_catalogue.router)
