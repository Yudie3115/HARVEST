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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.storage.models import (
    AccessCode,
    AccessCodeStatusEnum,
    AccessGrant,
    AccessGrantStatusEnum,
    ChannelEnum,
    GlobalUsageCounter,
)

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


# ---------------------------------------------------------------------------
# Grant resolution and atomic quota reservation
# ---------------------------------------------------------------------------

@dataclass
class ResolvedGrant:
    grant: AccessGrant
    access_code: AccessCode


def month_start(dt: datetime) -> datetime:
    """First instant of dt's UTC calendar month. Public — also used by routes to compute
    period_resets_at for status/redemption responses."""
    return dt.astimezone(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


def next_month_start(period_start: datetime) -> datetime:
    """First instant of the UTC calendar month after *period_start*'s month."""
    if period_start.month == 12:
        return period_start.replace(year=period_start.year + 1, month=1)
    return period_start.replace(month=period_start.month + 1)


def resolve_web_grant(db: Session, token: str | None) -> ResolvedGrant:
    """Resolve the active web AccessGrant for *token*. Does not gate on code status."""
    if not token:
        raise AccessRequiredError("An access token is required.")

    token_hash = hash_token(token)
    grant = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.channel == ChannelEnum.web,
            AccessGrant.identifier_hash == token_hash,
            AccessGrant.status == AccessGrantStatusEnum.active,
        )
        .first()
    )
    if grant is None:
        raise AccessInvalidError("This access token is unknown or has been replaced.")

    access_code = db.get(AccessCode, grant.access_code_id)
    return ResolvedGrant(grant=grant, access_code=access_code)


def require_active_code(access_code: AccessCode) -> None:
    """Raise AccessRevokedError if *access_code* has been revoked."""
    if access_code.status == AccessCodeStatusEnum.revoked:
        raise AccessRevokedError(
            "This group's access has been revoked. Contact your administrator for a replacement code."
        )


def reserve_quota(db: Session, access_code_id: UUID) -> None:
    """
    Atomically reserve one message against both the code's and the global monthly
    quota, in one transaction, locking global-then-code to prevent deadlocks.
    """
    now = datetime.now(timezone.utc)
    current_period = month_start(now)

    global_row = (
        db.query(GlobalUsageCounter)
        .filter(GlobalUsageCounter.id == 1)
        .with_for_update()
        .one()
    )
    code_row = (
        db.query(AccessCode)
        .filter(AccessCode.id == access_code_id)
        .with_for_update()
        .one_or_none()
    )
    if code_row is None:
        db.rollback()
        raise AccessInvalidError("This access code no longer exists.")

    if global_row.period_start < current_period:
        global_row.usage_count = 0
        global_row.period_start = current_period
    if code_row.period_start < current_period:
        code_row.usage_count = 0
        code_row.period_start = current_period

    if code_row.status == AccessCodeStatusEnum.revoked:
        db.rollback()
        raise AccessRevokedError(
            "This group's access has been revoked. Contact your administrator for a replacement code."
        )

    if code_row.usage_count >= code_row.monthly_limit:
        db.rollback()
        raise QuotaExhaustedError(
            "This group's messages have been used for this month.",
            period_resets_at=next_month_start(current_period),
        )

    if global_row.usage_count >= settings.global_monthly_message_limit:
        db.rollback()
        raise GlobalLimitReachedError(
            "The system-wide message limit has been reached. Please try again later."
        )

    code_row.usage_count += 1
    global_row.usage_count += 1
    db.commit()


# ---------------------------------------------------------------------------
# Admin code creation and web code redemption
# ---------------------------------------------------------------------------

_MAX_CODE_GENERATION_ATTEMPTS = 10


def create_access_code(
    db: Session,
    *,
    label: str,
    monthly_limit: int,
    created_by: str,
    organization_name: str | None = None,
    contact_message: str | None = None,
) -> tuple[AccessCode, str]:
    """Generate a new access code, persist its hash, and return (row, plaintext_code)."""
    for _ in range(_MAX_CODE_GENERATION_ATTEMPTS):
        plaintext = generate_code()
        code_row = AccessCode(
            code_hash=hash_code(plaintext),
            label=label,
            organization_name=organization_name,
            contact_message=contact_message,
            monthly_limit=monthly_limit,
            created_by=created_by,
        )
        db.add(code_row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(code_row)
        return code_row, plaintext

    raise RuntimeError(
        f"Could not generate a unique access code after {_MAX_CODE_GENERATION_ATTEMPTS} attempts."
    )


@dataclass
class RedemptionResult:
    token: str
    grant: AccessGrant
    access_code: AccessCode


def redeem_web_code(db: Session, raw_code: str) -> RedemptionResult:
    """Redeem a web access code, creating a new active AccessGrant with a fresh token."""
    normalized = normalize_code(raw_code)
    code_row = (
        db.query(AccessCode)
        .filter(AccessCode.code_hash == hash_code(normalized))
        .first()
    )
    if code_row is None:
        raise AccessInvalidError("This access code is not recognized.")

    require_active_code(code_row)

    token = generate_web_token()
    grant = AccessGrant(
        access_code_id=code_row.id,
        channel=ChannelEnum.web,
        identifier_hash=hash_token(token),
        status=AccessGrantStatusEnum.active,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    return RedemptionResult(token=token, grant=grant, access_code=code_row)
