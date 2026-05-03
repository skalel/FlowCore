import uuid
import sqlalchemy as sa
from sqlalchemy.orm import Session

def require_membership(db: Session, *, environment_id: uuid.UUID, user_id: uuid.UUID) -> None:
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
        raise PermissionError("Not a member")

def get_member_role_name(db: Session, *, environment_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    row = db.execute(
        sa.text("""
            SELECT r.name
            FROM environment_members em
            JOIN roles r ON r.id = em.role_id
            WHERE em.environment_id = :eid
              AND em.user_id = :uid
              AND em.status = 'ACTIVE'
            LIMIT 1
        """),
        {"eid": str(environment_id), "uid": str(user_id)},
    ).first()
    return row[0] if row else None

def require_owner_or_admin(db: Session, *, environment_id: uuid.UUID, user_id: uuid.UUID) -> None:
    role = get_member_role_name(db, environment_id=environment_id, user_id=user_id)
    if role not in ("Owner", "Admin"):
        raise PermissionError("Not allowed")
