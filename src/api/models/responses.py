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


class AccessCodeAdminResponse(BaseModel):
    id: str
    label: str
    organization_name: str | None
    contact_message: str | None
    monthly_limit: int
    status: str
    usage_count: int
    period_start: str
    created_at: str
    created_by: str


class AccessCodeCreatedResponse(AccessCodeAdminResponse):
    code: str  # plaintext, shown once at creation only


class AccessCodeListResponse(BaseModel):
    items: list[AccessCodeAdminResponse]
    total: int
    offset: int
    limit: int
