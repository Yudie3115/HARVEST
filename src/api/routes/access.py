"""
Public access routes — code redemption and status.

POST /access/redeem  → redeem a code, returns a one-time plaintext web token
GET  /access/status  → report the current token's code status/usage without gating on it
"""
from fastapi import APIRouter, Depends, Header, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.models.requests import RedeemCodeRequest
from src.api.models.responses import AccessStatusResponse, RedeemResponse
from src.api.services import access_service
from src.config.settings import settings

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/access", tags=["access"])


def _next_month_start_iso(period_start) -> str:
    return access_service.next_month_start(
        access_service.month_start(period_start)
    ).isoformat()


@router.post("/redeem", response_model=RedeemResponse)
@limiter.limit(f"{settings.api_rate_limit_web}/hour")
def redeem(
    request: Request,  # required by slowapi
    body: RedeemCodeRequest,
    db: Session = Depends(get_db),
) -> RedeemResponse:
    client_ip = get_remote_address(request)
    access_service.check_redemption_throttle(db, client_ip)

    try:
        result = access_service.redeem_web_code(db, body.code)
    except access_service.AccessError:
        access_service.record_failed_redemption_attempt(db, client_ip)
        raise

    access_service.clear_redemption_throttle(db, client_ip)

    return RedeemResponse(
        access_token=result.token,
        label=result.access_code.label,
        monthly_limit=result.access_code.monthly_limit,
        usage_count=result.access_code.usage_count,
        period_resets_at=_next_month_start_iso(result.access_code.period_start),
    )


@router.get("/status", response_model=AccessStatusResponse)
def status(
    x_access_token: str | None = Header(default=None, alias="X-Access-Token"),
    db: Session = Depends(get_db),
) -> AccessStatusResponse:
    resolved = access_service.resolve_web_grant(db, x_access_token)
    code = resolved.access_code
    code_status = code.status.value if hasattr(code.status, "value") else code.status
    return AccessStatusResponse(
        status=code_status,
        label=code.label,
        monthly_limit=code.monthly_limit,
        usage_count=code.usage_count,
        period_resets_at=_next_month_start_iso(code.period_start),
    )
