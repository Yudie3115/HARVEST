"""
Admin API routes for managing access codes.

Endpoints:
  POST   /admin/access-codes             → create a code, returns plaintext once
  GET    /admin/access-codes             → paginated list
  PATCH  /admin/access-codes/{id}        → edit label/limit/org/contact
  POST   /admin/access-codes/{id}/revoke
  POST   /admin/access-codes/{id}/reactivate
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.models.requests import CreateAccessCodeRequest, UpdateAccessCodeRequest
from src.api.models.responses import (
    AccessCodeAdminResponse,
    AccessCodeCreatedResponse,
    AccessCodeListResponse,
)
from src.api.routes.admin import require_admin
from src.api.services import access_service
from src.storage.models import AccessCode, AccessCodeStatusEnum

router = APIRouter(prefix="/admin/access-codes", tags=["admin-access"])


def _to_admin_response(row: AccessCode) -> AccessCodeAdminResponse:
    return AccessCodeAdminResponse(
        id=str(row.id),
        label=row.label,
        organization_name=row.organization_name,
        contact_message=row.contact_message,
        monthly_limit=row.monthly_limit,
        status=row.status.value if hasattr(row.status, "value") else row.status,
        usage_count=row.usage_count,
        period_start=row.period_start.isoformat(),
        created_at=row.created_at.isoformat(),
        created_by=row.created_by,
    )


@router.post("", response_model=AccessCodeCreatedResponse, status_code=201)
def create_access_code(
    body: CreateAccessCodeRequest,
    admin_username: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccessCodeCreatedResponse:
    row, plaintext = access_service.create_access_code(
        db,
        label=body.label,
        monthly_limit=body.monthly_limit,
        created_by=admin_username,
        organization_name=body.organization_name,
        contact_message=body.contact_message,
    )
    return AccessCodeCreatedResponse(**_to_admin_response(row).model_dump(), code=plaintext)


@router.get("", response_model=AccessCodeListResponse)
def list_access_codes(
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccessCodeListResponse:
    query = db.query(AccessCode)
    if status:
        try:
            query = query.filter(AccessCode.status == AccessCodeStatusEnum(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")

    total = query.count()
    rows = (
        query.order_by(AccessCode.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AccessCodeListResponse(
        items=[_to_admin_response(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch("/{code_id}", response_model=AccessCodeAdminResponse)
def update_access_code(
    code_id: UUID,
    body: UpdateAccessCodeRequest,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccessCodeAdminResponse:
    row = db.get(AccessCode, code_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access code not found.")

    if body.label is not None:
        row.label = body.label
    if body.monthly_limit is not None:
        row.monthly_limit = body.monthly_limit
    if body.organization_name is not None:
        row.organization_name = body.organization_name
    if body.contact_message is not None:
        row.contact_message = body.contact_message
    db.commit()
    db.refresh(row)
    return _to_admin_response(row)


@router.post("/{code_id}/revoke", response_model=AccessCodeAdminResponse)
def revoke_access_code(
    code_id: UUID,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccessCodeAdminResponse:
    row = db.get(AccessCode, code_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access code not found.")
    row.status = AccessCodeStatusEnum.revoked
    db.commit()
    db.refresh(row)
    return _to_admin_response(row)


@router.post("/{code_id}/reactivate", response_model=AccessCodeAdminResponse)
def reactivate_access_code(
    code_id: UUID,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccessCodeAdminResponse:
    row = db.get(AccessCode, code_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access code not found.")
    row.status = AccessCodeStatusEnum.active
    db.commit()
    db.refresh(row)
    return _to_admin_response(row)
