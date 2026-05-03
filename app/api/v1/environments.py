import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.v1.schemas_env import (
    AcceptInviteIn,
    CreateEnvironmentIn,
    EnvironmentOut,
    EnvironmentSettings,
    UpdateEnvironmentIn,
)
from app.infra.db.orm_models import (
    CardHolder,
    Environment,
    EnvironmentMember,
    Invite,
    User,
)
from app.services.category_service import seed_environment_categories
from app.services.fiscal_closing_service import close_past_months_for_new_environment

router = APIRouter(prefix="/environments", tags=["environments"])


def _role_id_by_name(db: Session, name: str) -> uuid.UUID:
    row = db.execute(
        sa.text("SELECT id FROM roles WHERE name = :n LIMIT 1"), {"n": name}
    ).first()
    if not row:
        raise HTTPException(
            status_code=500, detail=f"Role '{name}' not found (seed missing?)"
        )
    return uuid.UUID(str(row[0]))


@router.get("", response_model=list[EnvironmentOut])
def list_my_environments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.execute(
            sa.text("""
            SELECT e.id, e.type, e.name, e.owner_user_id, u.name as owner_name, e.expires_at, e.is_archived, e.settings -- <--- ADICIONE e.settings AQUI
            FROM environments e
            JOIN environment_members em ON em.environment_id = e.id
            JOIN users u ON u.id = e.owner_user_id
            WHERE em.user_id = :uid
            AND em.status = 'ACTIVE'
            AND (e.expires_at IS NULL OR e.expires_at > :now)
            ORDER BY
                CASE WHEN e.type = 'SOLO' THEN 0 ELSE 1 END ASC,
                e.created_at DESC
        """),
            {"uid": str(current_user.id), "now": datetime.now(timezone.utc)},
        )
        .mappings()
        .all()
    )

    return [
        EnvironmentOut(
            id=str(r["id"]),
            type=r["type"],
            name=r["name"],
            owner_user_id=str(r["owner_user_id"]),
            owner_name=r["owner_name"],
            is_owner=(str(r["owner_user_id"]) == str(current_user.id)),
            expires_at=r["expires_at"],
            is_archived=r["is_archived"],
            settings=EnvironmentSettings(**(r["settings"] or {})),
        )
        for r in rows
    ]


@router.post("", response_model=EnvironmentOut)
def create_environment(
    payload: CreateEnvironmentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.expires_at:
        payload.expires_at = None

    if payload.type == "BUSINESS":
        if payload.expires_at and payload.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=422, detail="A data de expiração deve estar no futuro."
            )
    else:
        payload.expires_at = None

    env = Environment(
        type=payload.type,
        name=payload.name,
        owner_user_id=current_user.id,
        expires_at=payload.expires_at,
        is_archived=False,
        settings={"auto_fiscal_closing": True},
    )
    db.add(env)
    db.flush()

    if current_user.cpf:
        default_holder = CardHolder(
            environment_id=env.id,
            created_by_user_id=current_user.id,
            cpf=current_user.cpf,
            name=current_user.name,
        )
        db.add(default_holder)

    close_past_months_for_new_environment(db, env)
    seed_environment_categories(db, env.id)

    owner_role_id = _role_id_by_name(db, "Owner")
    member = EnvironmentMember(
        environment_id=env.id,
        user_id=current_user.id,
        role_id=owner_role_id,
        status="ACTIVE",
    )
    db.add(member)
    db.commit()
    db.refresh(env)

    return EnvironmentOut(
        id=str(env.id),
        type=env.type,
        name=env.name,
        owner_user_id=str(env.owner_user_id),
        owner_name=current_user.name,
        is_owner=True,
        expires_at=env.expires_at,
        is_archived=env.is_archived,
        settings=EnvironmentSettings(**(env.settings or {})),
    )


@router.patch("/{environment_id}")
def update_environment(
    environment_id: str,
    payload: UpdateEnvironmentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        eid = uuid.UUID(environment_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de ambiente inválido.")

    env = db.get(Environment, eid)
    if not env:
        raise HTTPException(status_code=404, detail="Ambiente não encontrado.")

    if env.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Apenas o proprietário pode alterar este ambiente."
        )

    if payload.name is not None:
        if len(payload.name.strip()) < 2:
            raise HTTPException(
                status_code=422, detail="O nome deve ter pelo menos 2 caracteres."
            )
        env.name = payload.name.strip()

    if payload.is_archived is not None:
        if env.type == "SOLO" and payload.is_archived:
            raise HTTPException(
                status_code=400, detail="O ambiente pessoal não pode ser arquivado."
            )
        env.is_archived = payload.is_archived

    if payload.model_fields_set.intersection({"expires_at"}):
        if env.type == "BUSINESS":
            env.expires_at = payload.expires_at
        else:
            env.expires_at = None

    if payload.settings is not None:
        env.settings = payload.settings.model_dump()

    env.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "success"}


@router.delete("/{environment_id}")
def delete_environment(
    environment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        eid = uuid.UUID(environment_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de ambiente inválido.")

    env = db.get(Environment, eid)
    if not env:
        raise HTTPException(status_code=404, detail="Ambiente não encontrado.")

    if env.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Apenas o proprietário pode excluir este ambiente."
        )

    if env.type == "SOLO":
        raise HTTPException(
            status_code=400, detail="O ambiente pessoal não pode ser excluído."
        )

    db.delete(env)
    db.commit()

    return {"status": "success"}


@router.post("/accept-invite")
def accept_invite(
    payload: AcceptInviteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invite = db.execute(
        sa.select(Invite).where(Invite.token == payload.token)
    ).scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=404, detail="Convite inválido ou não encontrado."
        )

    if invite.accepted_at:
        raise HTTPException(
            status_code=400, detail="Este convite já foi aceito anteriormente."
        )

    if invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="Este convite já expirou. Solicite um novo."
        )

    if current_user.email.lower() != invite.email.lower():
        raise HTTPException(
            status_code=403,
            detail="Este convite foi enviado para outro endereço de e-mail. Faça login com a conta correta.",
        )

    existing_member = db.execute(
        sa.select(EnvironmentMember)
        .where(EnvironmentMember.environment_id == invite.environment_id)
        .where(EnvironmentMember.user_id == current_user.id)
    ).scalar_one_or_none()

    if not existing_member:
        new_member = EnvironmentMember(
            environment_id=invite.environment_id,
            user_id=current_user.id,
            role_id=invite.role_id,
            status="ACTIVE",
        )
        db.add(new_member)

    invite.accepted_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "success", "environment_id": str(invite.environment_id)}


@router.get("/invites/info/{token}")
def get_invite_info(token: str, db: Session = Depends(get_db)):
    row = (
        db.execute(
            sa.text("""
        SELECT i.email, i.expires_at, i.accepted_at,
               u.name AS inviter_name,
               e.name AS environment_name
        FROM invites i
        JOIN users u ON u.id = i.created_by_user_id
        JOIN environments e ON e.id = i.environment_id
        WHERE i.token = :token
    """),
            {"token": token},
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404, detail="Convite inválido ou não encontrado."
        )

    if row["accepted_at"]:
        raise HTTPException(status_code=400, detail="Este convite já foi aceito.")

    if row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="Este convite expirou. Solicite um novo."
        )

    return {
        "email": row["email"],
        "inviter_name": row["inviter_name"],
        "environment_name": row["environment_name"],
    }
