from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
from datetime import datetime, timezone

from app.api.deps import get_db
from app.api.auth_deps import get_current_user
from app.infra.db.orm_models import Invite, EnvironmentMember, User

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("/{token}/accept")
def accept_invite(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv: Invite | None = db.execute(sa.select(Invite).where(Invite.token == token)).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")

    now = datetime.now(timezone.utc)
    if inv.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invite already accepted")
    if inv.expires_at <= now:
        raise HTTPException(status_code=410, detail="Invite expired")

    if inv.email.lower() != current_user.email.lower():
        raise HTTPException(status_code=403, detail="Invite not for this user")

    exists = db.execute(
        sa.text("""
            SELECT 1 FROM environment_members
            WHERE environment_id = :eid AND user_id = :uid
            LIMIT 1
        """),
        {"eid": str(inv.environment_id), "uid": str(current_user.id)},
    ).first()

    if exists:
        db.execute(
            sa.text("""
                UPDATE environment_members
                SET role_id = :rid, status = 'ACTIVE'
                WHERE environment_id = :eid AND user_id = :uid
            """),
            {"rid": str(inv.role_id), "eid": str(inv.environment_id), "uid": str(current_user.id)},
        )
    else:
        db.add(EnvironmentMember(
            environment_id=inv.environment_id,
            user_id=current_user.id,
            role_id=inv.role_id,
            status="ACTIVE",
        ))

    inv.accepted_at = now
    db.commit()
    return {"status": "accepted", "environment_id": str(inv.environment_id)}
