import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.infra.db.orm_models import FiscalClosure, User

router = APIRouter(prefix="/fiscal", tags=["fiscal"])


@router.post(
    "/{year}/{month}/close",
    dependencies=[
        Depends(require_permission("fiscal:close", get_environment_id_from_header))
    ],
)
def close_month(
    year: int,
    month: int,
    note: str | None = Query(default=None, max_length=400),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    closure = db.execute(
        sa.select(FiscalClosure)
        .where(FiscalClosure.environment_id == env_id)
        .where(FiscalClosure.year == year)
        .where(FiscalClosure.month == month)
    ).scalar_one_or_none()

    if closure:
        if closure.status == "CLOSED":
            return {"status": "already_closed"}

        closure.status = "CLOSED"
        closure.closed_by_user_id = current_user.id
        closure.closed_at = datetime.now(timezone.utc)
        if note:
            closure.note = note
        closure.updated_at = datetime.now(timezone.utc)
    else:
        closure = FiscalClosure(
            environment_id=env_id,
            year=year,
            month=month,
            status="CLOSED",
            closed_by_user_id=current_user.id,
            closed_at=datetime.now(timezone.utc),
            note=note,
        )
        db.add(closure)

    db.commit()
    return {"status": "closed"}


@router.post(
    "/{year}/{month}/reopen",
    dependencies=[
        Depends(require_permission("fiscal:reopen", get_environment_id_from_header))
    ],
)
def reopen_month(
    year: int,
    month: int,
    note: str | None = Query(default=None, max_length=400),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    closure = db.execute(
        sa.select(FiscalClosure)
        .where(FiscalClosure.environment_id == env_id)
        .where(FiscalClosure.year == year)
        .where(FiscalClosure.month == month)
    ).scalar_one_or_none()

    if not closure or closure.status == "OPEN":
        return {"status": "already_open"}

    closure.status = "OPEN"
    if note:
        closure.note = note
    closure.updated_at = datetime.now(timezone.utc)

    db.commit()
    return {"status": "reopened"}
