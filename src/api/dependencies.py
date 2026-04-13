"""
FastAPI dependency injection helpers.

All service clients are stored on app.state at startup (see main.py lifespan).
Route handlers receive them via these Depends() callables.
"""
from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and ensure it is closed after use."""
    db: Session = request.app.state.postgres_client.get_session()
    try:
        yield db
    finally:
        db.close()


def get_llm_client(request: Request):
    return request.app.state.llm_client


def get_embedding_client(request: Request):
    return request.app.state.embedding_client


def get_vector_db_client(request: Request):
    return request.app.state.vector_db_client


def get_translation_client(request: Request):
    return request.app.state.translation_client


def get_whatsapp_service(request: Request):
    return request.app.state.whatsapp_service
