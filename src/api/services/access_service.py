"""
Access & quota service — code normalization/generation/hashing, grant resolution,
atomic quota reservation, and redemption throttling.

All functions here take a SQLAlchemy Session explicitly and raise AccessError
subclasses (see the error-contract section below) rather than FastAPI
HTTPExceptions directly, keeping domain logic decoupled from route handlers.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from src.config.settings import settings

DOMAIN_ACCESS_CODE = "access_code"
DOMAIN_WHATSAPP_GRANT = "whatsapp_grant_identifier"
DOMAIN_REDEMPTION_THROTTLE = "redemption_throttle"

_WORDLIST_PATH = Path(__file__).parent / "wordlists" / "access_code_words_v1.txt"
_WORDS: list[str] = _WORDLIST_PATH.read_text().split()

_SEPARATOR_RE = re.compile(r"[\s_\-]+")


# ---------------------------------------------------------------------------
# Access/quota error contract
# ---------------------------------------------------------------------------

class AccessError(Exception):
    """Base class for all access/quota authorization failures."""
    code: str = "access_error"
    http_status: int = 400

    def __init__(self, message: str, period_resets_at: "datetime | None" = None):
        super().__init__(message)
        self.message = message
        self.period_resets_at = period_resets_at


class AccessRequiredError(AccessError):
    code = "access_required"
    http_status = 401


class AccessInvalidError(AccessError):
    code = "access_invalid"
    http_status = 401


class AccessRevokedError(AccessError):
    code = "access_revoked"
    http_status = 403


class SessionForbiddenError(AccessError):
    code = "session_forbidden"
    http_status = 403


class QuotaExhaustedError(AccessError):
    code = "quota_exhausted"
    http_status = 429


class GlobalLimitReachedError(AccessError):
    code = "global_limit_reached"
    http_status = 503


class RedemptionRateLimitedError(AccessError):
    code = "redemption_rate_limited"
    http_status = 429


async def access_error_handler(request: Request, exc: AccessError) -> JSONResponse:
    """FastAPI exception handler translating AccessError into the stable JSON contract."""
    body: dict = {"error": {"code": exc.code, "message": exc.message}}
    if exc.period_resets_at is not None:
        body["error"]["period_resets_at"] = exc.period_resets_at.isoformat()
    return JSONResponse(status_code=exc.http_status, content=body)


def normalize_code(raw: str) -> str:
    """Trim, lowercase, and collapse separator whitespace/punctuation into single hyphens."""
    trimmed = raw.strip().lower()
    parts = [p for p in _SEPARATOR_RE.split(trimmed) if p]
    return "-".join(parts)


def generate_code() -> str:
    """Generate a normalized three-word access code using a cryptographically secure RNG."""
    return "-".join(secrets.choice(_WORDS) for _ in range(3))


def _keyed_hmac(domain: str, value: str) -> str:
    message = f"{domain}:{value}".encode()
    return hmac.new(settings.access_hash_secret.encode(), message, hashlib.sha256).hexdigest()


def hash_code(normalized_code: str) -> str:
    """Keyed HMAC-SHA-256 digest of an already-normalized access code."""
    return _keyed_hmac(DOMAIN_ACCESS_CODE, normalized_code)


def hash_identifier(value: str, domain: str) -> str:
    """Domain-separated keyed HMAC-SHA-256 digest of a low-entropy identifier (phone, IP)."""
    return _keyed_hmac(domain, value)


def hash_token(token: str) -> str:
    """Unkeyed SHA-256 digest of a high-entropy (256-bit random) web access token."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_web_token() -> str:
    """Generate a new opaque, high-entropy (256-bit) web access token."""
    return secrets.token_urlsafe(32)
