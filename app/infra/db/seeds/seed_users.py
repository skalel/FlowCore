import sqlalchemy as sa
import uuid6
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infra.db.orm_models import Environment, EnvironmentMember, User
from app.shared.security import hash_password


def get_role_id_by_name(db: Session, name: str):
    role = db.execute(
        sa.text("SELECT id FROM roles WHERE name = :n LIMIT 1"), {"n": name}
    ).first()
    if not role:
        raise HTTPException(status_code=500, detail=f"Role seed '{name}' not found.")
    return role[0]


def seed_default_user(db: Session) -> User:
    """
    Cria o usuário padrão de sistema e seu respectivo ambiente.
    Idempotente por email.
    """
    email = "mgmt@flowspace.com"

    existing_user = db.execute(
        sa.select(User).where(User.email == email)
    ).scalar_one_or_none()

    if existing_user:
        return existing_user

    new_user = User(
        id=uuid6.uuid7(),
        name="FlowSpace",
        email=email,
        password_hash=hash_password("Fl0wSp4ce#Finance"),
        plan_tier="free",
    )
    db.add(new_user)
    db.flush()

    env = Environment(
        id=uuid6.uuid7(),
        type="SOLO",
        name="Meu ambiente",
        owner_user_id=new_user.id,
        is_archived=False,
    )
    db.add(env)
    db.flush()

    owner_role_id = get_role_id_by_name(db, "Owner")

    member = EnvironmentMember(
        environment_id=env.id,
        user_id=new_user.id,
        role_id=owner_role_id,
        status="ACTIVE",
    )
    db.add(member)

    db.commit()
    db.refresh(new_user)

    return new_user
