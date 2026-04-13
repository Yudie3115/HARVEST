"""
Health check endpoint
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Returns service liveness status."""
    return {"status": "ok", "version": "1.0.0"}
