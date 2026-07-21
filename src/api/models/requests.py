"""
API request models
"""
from typing import Literal

from pydantic import BaseModel


class NewSessionRequest(BaseModel):
    channel: str = "web"  # "web" or "whatsapp"


class ChatRequest(BaseModel):
    session_id: str
    message: str
    language_override: str | None = None  # e.g. "lug", "ach"
    model_preference: Literal["openai", "groq", "ollama"] | None = None


class CreateAccessCodeRequest(BaseModel):
    label: str
    monthly_limit: int
    organization_name: str | None = None
    contact_message: str | None = None


class UpdateAccessCodeRequest(BaseModel):
    label: str | None = None
    monthly_limit: int | None = None
    organization_name: str | None = None
    contact_message: str | None = None


class RedeemCodeRequest(BaseModel):
    code: str


class PublicationUpdateRequest(BaseModel):
    publicly_visible: bool
    public_source_url: str | None = None
