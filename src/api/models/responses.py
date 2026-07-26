"""
API response models
"""
from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    title: str | None = None
    url: str | None = None
    site_name: str | None = None
    score: float | None = None
    snippet: str | None = None
    document_id: str | None = None
    summary: str | None = None
    document_type: str | None = None
    topics: list[str] = Field(default_factory=list)
    citation_indices: list[int] = Field(default_factory=list)
    library_url: str | None = None


class SuggestedQuestion(BaseModel):
    text: str
    kind: str = "generated"
    catalogue_entry_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    channel: str


class ChatResponse(BaseModel):
    answer: str
    detected_language: str
    sources: list[SourceRef]
    session_id: str
    no_results: bool = False
    suggested_questions: list[SuggestedQuestion] = Field(default_factory=list)


class HistoryMessage(BaseModel):
    role: str
    content: str
    detected_language: str | None
    sources: list[SourceRef] | None
    suggested_questions: list[SuggestedQuestion] = Field(default_factory=list)


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


class RedeemResponse(BaseModel):
    access_token: str
    label: str
    monthly_limit: int
    usage_count: int
    period_resets_at: str


class AccessStatusResponse(BaseModel):
    status: str  # "active" | "revoked"
    label: str
    monthly_limit: int
    usage_count: int
    period_resets_at: str


class PublicationUpdateResponse(BaseModel):
    id: str
    publicly_visible: bool
    published_at: str | None
    published_by: str | None
    public_source_url: str | None


class DocumentTitleUpdateResponse(BaseModel):
    id: str
    title: str
