import secrets
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.api.v1.schemas_env import (
    InviteDetailOut,
    InviteIn,
    InviteOut,
    MemberOut,
    RoleOut,
)
from app.config.settings import settings
from app.domain.services.email_service import send_invite_email
from app.infra.db.orm_models import Environment, EnvironmentMember, Invite, Role, User
from app.infra.integrations.email import EmailToSend, send_email

router = APIRouter(prefix="/environment", tags=["environment-settings"])


def _role_id_by_name(db: Session, name: str) -> uuid.UUID:
    row = db.execute(
        sa.text("SELECT id FROM roles WHERE name = :n LIMIT 1"), {"n": name}
    ).first()
    if not row:
        raise HTTPException(
            status_code=500, detail=f"Role '{name}' not found (seed missing?)"
        )
    return uuid.UUID(str(row[0]))


@router.get(
    "/members",
    response_model=list[MemberOut],
    dependencies=[
        Depends(require_permission("env:read", get_environment_id_from_header))
    ],
)
def list_members(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    rows = (
        db.execute(
            sa.text("""
        SELECT em.user_id, u.name, u.email, r.name as role_name, em.status, em.joined_at
        FROM environment_members em
        JOIN users u ON u.id = em.user_id
        JOIN roles r ON r.id = em.role_id
        WHERE em.environment_id = :eid
        ORDER BY em.joined_at ASC
    """),
            {"eid": str(env_id)},
        )
        .mappings()
        .all()
    )

    return [
        MemberOut(
            user_id=str(r["user_id"]),
            name=r["name"],
            email=r["email"],
            role_name=r["role_name"],
            status=r["status"],
            joined_at=r["joined_at"],
        )
        for r in rows
    ]


@router.delete(
    "/members/{user_id}",
    dependencies=[
        Depends(require_permission("env:manage", get_environment_id_from_header))
    ],
)
def remove_member(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de utilizador inválido")

    env = db.get(Environment, env_id)
    if env.owner_user_id == uid:
        raise HTTPException(
            status_code=403, detail="O proprietário do ambiente não pode ser removido."
        )
    if current_user.id == uid:
        raise HTTPException(
            status_code=403, detail="Não pode remover a sua própria conta por aqui."
        )

    member = db.execute(
        sa.select(EnvironmentMember)
        .where(EnvironmentMember.environment_id == env_id)
        .where(EnvironmentMember.user_id == uid)
    ).scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=404, detail="Membro não encontrado neste ambiente."
        )

    db.delete(member)
    db.commit()
    return {"status": "success"}


@router.get(
    "/invites",
    response_model=list[InviteDetailOut],
    dependencies=[
        Depends(require_permission("env:read", get_environment_id_from_header))
    ],
)
def list_invites(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    rows = (
        db.execute(
            sa.text("""
        SELECT i.id, i.email, r.name as role_name, i.token, i.expires_at, i.accepted_at, i.created_at
        FROM invites i
        JOIN roles r ON r.id = i.role_id
        WHERE i.environment_id = :eid
        ORDER BY i.created_at DESC
    """),
            {"eid": str(env_id)},
        )
        .mappings()
        .all()
    )

    now = datetime.now(timezone.utc)
    result = []

    for r in rows:
        status = "PENDING"
        if r["accepted_at"]:
            status = "ACCEPTED"
        elif r["expires_at"].replace(tzinfo=timezone.utc) < now:
            status = "EXPIRED"

        result.append(
            InviteDetailOut(
                id=str(r["id"]),
                email=r["email"],
                role_name=r["role_name"],
                token=r["token"],
                status=status,
                created_at=r["created_at"],
                expires_at=r["expires_at"],
            )
        )
    return result


@router.post(
    "/invites",
    response_model=InviteOut,
    dependencies=[
        Depends(require_permission("env:manage", get_environment_id_from_header))
    ],
)
def create_invite(
    payload: InviteIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    role_id = _role_id_by_name(db, payload.role_name)

    existing_user = db.execute(
        sa.select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    if existing_user:
        is_member = db.execute(
            sa.select(EnvironmentMember)
            .where(EnvironmentMember.environment_id == env_id)
            .where(EnvironmentMember.user_id == existing_user.id)
        ).scalar_one_or_none()
        if is_member:
            raise HTTPException(
                status_code=409, detail="Este utilizador já é membro do ambiente."
            )

    env = db.execute(
        sa.select(Environment).where(Environment.id == env_id)
    ).scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Ambiente não encontrado.")

    db.execute(
        sa.delete(Invite)
        .where(Invite.environment_id == env_id)
        .where(Invite.email == payload.email.lower())
        .where(Invite.accepted_at.is_(None))
    )

    invite_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)

    invite = Invite(
        environment_id=env_id,
        email=payload.email.lower(),
        role_id=role_id,
        token=invite_token,
        expires_at=expires_at,
        created_by_user_id=current_user.id,
    )
    db.add(invite)
    db.commit()

    background_tasks.add_task(
        send_invite_email,
        to_email=payload.email.lower(),
        inviter_name=current_user.name,
        env_name=env.name,
        token=invite_token,
        expires_at=expires_at,
    )

    return InviteOut(token=invite.token, expires_at=invite.expires_at)


@router.delete(
    "/invites/{invite_id}",
    dependencies=[
        Depends(require_permission("env:manage", get_environment_id_from_header))
    ],
)
def cancel_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        iid = uuid.UUID(invite_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de convite inválido")

    invite = db.execute(
        sa.select(Invite).where(Invite.id == iid).where(Invite.environment_id == env_id)
    ).scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    if invite.accepted_at:
        raise HTTPException(
            status_code=400, detail="Não pode cancelar um convite já aceite."
        )

    db.delete(invite)
    db.commit()
    return {"status": "success"}


@router.get(
    "/roles",
    response_model=list[RoleOut],
    dependencies=[
        Depends(require_permission("env:read", get_environment_id_from_header))
    ],
)
def list_available_roles(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    env = db.get(Environment, env_id)
    roles = (
        db.execute(
            sa.select(Role)
            .where(
                sa.or_(
                    Role.environment_type == env.type, Role.environment_type.is_(None)
                )
            )
            .order_by(Role.name)
        )
        .scalars()
        .all()
    )

    return [RoleOut(id=str(r.id), name=r.name, is_system=r.is_system) for r in roles]
