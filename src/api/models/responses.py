"""
API response models
"""
from pydantic import BaseModel


class SourceRef(BaseModel):
    title: str | None
    url: str | None
    site_name: str | None
    score: float | None = None
    snippet: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    channel: str


class ChatResponse(BaseModel):
    answer: str
    detected_language: str
    sources: list[SourceRef]
    session_id: str
    no_results: bool = False


class HistoryMessage(BaseModel):
    role: str
    content: str
    detected_language: str | None
    sources: list[SourceRef] | None


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]
