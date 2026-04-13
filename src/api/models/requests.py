"""
API request models
"""
from pydantic import BaseModel


class NewSessionRequest(BaseModel):
    channel: str = "web"  # "web" or "whatsapp"


class ChatRequest(BaseModel):
    session_id: str
    message: str
    language_override: str | None = None  # e.g. "lug", "ach"
