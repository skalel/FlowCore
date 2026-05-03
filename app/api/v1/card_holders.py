from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
import uuid
import re

from app.api.deps import get_db
from app.api.auth_deps import get_current_user
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.infra.db.orm_models import User, CardHolder, Card
from app.api.v1.schemas_cards import CardHolderOut, CardHolderCreateIn

router = APIRouter(prefix="/card-holders", tags=["card-holders"])

def clean_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)

@router.get(
    "",
    response_model=list[CardHolderOut],
    dependencies=[Depends(require_permission("cards:read", get_environment_id_from_header))],
)
def list_holders(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    rows = db.execute(
        sa.select(CardHolder).where(CardHolder.environment_id == env_id).order_by(CardHolder.name.asc())
    ).scalars().all()
    return [CardHolderOut(id=str(p.id), name=p.name, cpf=p.cpf) for p in rows]

@router.post(
    "",
    response_model=CardHolderOut,
    dependencies=[Depends(require_permission("cards:manage", get_environment_id_from_header))],
)
def create_holder(
    payload: CardHolderCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    cleaned_cpf = clean_cpf(payload.cpf)
    if len(cleaned_cpf) != 11:
        raise HTTPException(status_code=422, detail="O CPF deve conter exatamente 11 dígitos numéricos.")

    existing = db.execute(
        sa.select(CardHolder)
        .where(CardHolder.environment_id == env_id)
        .where(CardHolder.cpf == cleaned_cpf)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail="Já existe um titular com este CPF neste ambiente.")

    p = CardHolder(
        environment_id=env_id,
        name=payload.name.strip(),
        cpf=cleaned_cpf,
        created_by_user_id=current_user.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    
    return CardHolderOut(id=str(p.id), name=p.name, cpf=p.cpf)

@router.patch(
    "/{holder_id}",
    dependencies=[Depends(require_permission("cards:manage", get_environment_id_from_header))],
)
def update_holder(
    holder_id: str,
    payload: CardHolderCreateIn,
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        hid = uuid.UUID(holder_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de titular inválido.")

    holder = db.execute(
        sa.select(CardHolder).where(CardHolder.id == hid).where(CardHolder.environment_id == env_id)
    ).scalar_one_or_none()

    if not holder:
        raise HTTPException(status_code=404, detail="Titular não encontrado.")

    cleaned_cpf = clean_cpf(payload.cpf)
    if len(cleaned_cpf) != 11:
        raise HTTPException(status_code=422, detail="O CPF deve conter exatamente 11 dígitos numéricos.")

    if cleaned_cpf != holder.cpf:
        existing = db.execute(
            sa.select(CardHolder)
            .where(CardHolder.environment_id == env_id)
            .where(CardHolder.cpf == cleaned_cpf)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Outro titular já utiliza este CPF neste ambiente.")

    holder.name = payload.name.strip()
    holder.cpf = cleaned_cpf
    db.commit()

    return {"status": "success"}

@router.delete(
    "/{holder_id}",
    dependencies=[Depends(require_permission("cards:manage", get_environment_id_from_header))],
)
def delete_holder(
    holder_id: str,
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        hid = uuid.UUID(holder_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de titular inválido.")

    holder = db.execute(
        sa.select(CardHolder).where(CardHolder.id == hid).where(CardHolder.environment_id == env_id)
    ).scalar_one_or_none()

    if not holder:
        raise HTTPException(status_code=404, detail="Titular não encontrado.")

    linked_card = db.execute(
        sa.select(Card).where(Card.holder_id == hid).where(Card.deleted_at.is_(None))
    ).first()

    if linked_card:
        raise HTTPException(
            status_code=400, 
            detail="Não é possível excluir este titular pois existem cartões ativos vinculados a ele."
        )

    db.delete(holder)
    db.commit()

    return {"status": "success"}