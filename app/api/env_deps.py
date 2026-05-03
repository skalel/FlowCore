import uuid
import sqlalchemy as sa
from fastapi import Header, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.auth_deps import get_current_user
from app.infra.db.orm_models import User


def _require_membership(db: Session, *, environment_id: uuid.UUID, user_id: uuid.UUID) -> None:
    row = db.execute(
        sa.text("""
            SELECT 1
            FROM environment_members
            WHERE environment_id = :eid
              AND user_id = :uid
              AND status = 'ACTIVE'
            LIMIT 1
        """),
        {"eid": str(environment_id), "uid": str(user_id)},
    ).first()

    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this environment")


def get_environment_id_from_header(
    x_environment_id: str | None = Header(default=None, alias="X-Environment-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> uuid.UUID | None: 
    
    if not x_environment_id:
        return None

    try:
        env_id = uuid.UUID(x_environment_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid X-Environment-Id format")

    _require_membership(db, environment_id=env_id, user_id=current_user.id)
    
    return env_id


def get_environment_id_from_path(
    environment_id: str = Path(..., description="Environment UUID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> uuid.UUID:
    try:
        env_id = uuid.UUID(environment_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid environment_id")

    _require_membership(db, environment_id=env_id, user_id=current_user.id)
    return env_id
