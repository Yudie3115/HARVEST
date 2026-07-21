"""
Access & quota service — code normalization/generation/hashing, grant resolution,
atomic quota reservation, and redemption throttling.

All functions here take a SQLAlchemy Session explicitly and raise AccessError
subclasses (see the error-contract section added in a later task) rather than
FastAPI HTTPExceptions, so this module has no framework dependency.
"""
import hashlib
import hmac
import re
import secrets
from pathlib import Path

from src.config.settings import settings

DOMAIN_ACCESS_CODE = "access_code"
DOMAIN_WHATSAPP_GRANT = "whatsapp_grant_identifier"
DOMAIN_REDEMPTION_THROTTLE = "redemption_throttle"

_WORDLIST_PATH = Path(__file__).parent / "wordlists" / "access_code_words_v1.txt"
_WORDS: list[str] = _WORDLIST_PATH.read_text().split()

_SEPARATOR_RE = re.compile(r"[\s_\-]+")


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
