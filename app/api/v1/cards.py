import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.api.v1.schemas_cards import (
    CardCreateIn,
    CardOut,
    CardShareRequest,
    CardShareResponse,
    CardUpdateIn,
)
from app.infra.db.orm_models import Card, CardHolder, User
from app.services.connection_service import ConnectionService

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get(
    "",
    response_model=list[CardOut],
    dependencies=[
        Depends(require_permission("cards:read", get_environment_id_from_header))
    ],
)
def list_cards(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    rows = (
        db.execute(
            sa.text("""
              SELECT
                          c.id,
                          c.last4,
                          c.description, -- Agora trazemos a descrição do banco!
                          c.brand,
                          c.due_day,
                          c.pay_day,
                          c.holder_id,
                          ch.name as holder_name
                      FROM cards c
                      LEFT JOIN card_holders ch ON ch.id = c.holder_id -- <-- A MÁGICA ACONTECE AQUI
                      WHERE c.environment_id = :eid
                        AND c.deleted_at IS NULL
                      ORDER BY ch.name ASC NULLS LAST, c.last4 ASC
    """),
            {"eid": str(env_id)},
        )
        .mappings()
        .all()
    )

    return [
        CardOut(
            id=str(r["id"]),
            last4=r["last4"],
            description=r["description"],
            brand=r["brand"],
            due_day=r["due_day"],
            pay_day=r["pay_day"],
            holder_id=str(r["holder_id"]) if r["holder_id"] else None,
            holder_name=r["holder_name"],
        )
        for r in rows
    ]


@router.post(
    "",
    response_model=CardOut,
    dependencies=[
        Depends(require_permission("cards:manage", get_environment_id_from_header))
    ],
)
def create_card(
    payload: CardCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    owner = db.execute(
        sa.select(CardHolder).where(
            CardHolder.id == payload.holder_id, CardHolder.environment_id == env_id
        )
    ).scalar_one_or_none()

    if not payload.last4.isdigit():
        raise HTTPException(
            status_code=422, detail="Os últimos 4 dígitos devem ser numéricos."
        )

    c = Card(
        environment_id=env_id,
        last4=payload.last4,
        brand=payload.brand,
        description=payload.description,
        due_day=payload.due_day,
        pay_day=payload.pay_day,
        holder_id=payload.holder_id,
        created_by_user_id=current_user.id,
    )
    db.add(c)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Este cartão já existe para este titular."
        )

    db.refresh(c)

    return CardOut(
        id=str(c.id),
        last4=c.last4,
        description=c.description,
        brand=c.brand,
        due_day=c.due_day,
        pay_day=c.pay_day,
        holder_id=str(c.holder_id) if c.holder_id else None,
        holder_name=owner.name if owner else "Desconhecido",
    )


@router.patch(
    "/{card_id}",
    response_model=CardOut,
    dependencies=[
        Depends(require_permission("cards:manage", get_environment_id_from_header))
    ],
)
def update_card(
    card_id: str,
    payload: CardUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        cid = uuid.UUID(card_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de cartão inválido.")

    c: Card | None = db.get(Card, cid)
    if not c or c.environment_id != env_id or c.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cartão não encontrado.")

    data = payload.model_dump(exclude_unset=True)
    holder_name = "Desconhecido"

    if "holder_id" in data:
        new_holder_id = data["holder_id"]

        if new_holder_id is not None:
            owner = db.execute(
                sa.select(CardHolder).where(
                    CardHolder.id == new_holder_id, CardHolder.environment_id == env_id
                )
            ).scalar_one_or_none()

            if not owner:
                raise HTTPException(status_code=422, detail="ID de titular inválido.")
            holder_name = owner.name
        else:
            holder_name = None
    else:
        if c.holder_id:
            owner = db.get(CardHolder, c.holder_id)
            if owner:
                holder_name = owner.name
        else:
            holder_name = None

    for k, v in data.items():
        setattr(c, k, v)

    c.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Este cartão já existe para este titular."
        )

    db.refresh(c)

    return CardOut(
        id=str(c.id),
        last4=c.last4,
        description=c.description,
        brand=c.brand,
        due_day=c.due_day,
        pay_day=c.pay_day,
        holder_id=str(c.holder_id) if c.holder_id else None,
        holder_name=holder_name,
    )


@router.delete(
    "/{card_id}",
    dependencies=[
        Depends(require_permission("cards:manage", get_environment_id_from_header))
    ],
)
def delete_card(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        cid = uuid.UUID(card_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de cartão inválido.")

    c: Card | None = db.get(Card, cid)
    if not c or c.environment_id != env_id or c.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cartão não encontrado.")

    c.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "deleted"}


@router.post("/{card_id}/share", response_model=CardShareResponse)
def share_card(
    card_id: uuid.UUID,
    payload: CardShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Empresta um cartão para um amigo.
    Se não forem amigos, envia o convite de amizade automaticamente e deixa o empréstimo pendente.
    """
    service = ConnectionService(db)
    return service.share_card(
        owner_id=current_user.id, card_id=card_id, target_email=payload.email
    )
