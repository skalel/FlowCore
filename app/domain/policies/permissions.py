import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.infra.db.orm_models import Card, CardHolder, User


def has_permission(
    db: Session,
    *,
    environment_id: uuid.UUID,
    user_id: uuid.UUID,
    permission_code: str,
) -> bool:
    if not environment_id or not user_id:
        return False

    deny = db.execute(
        sa.text("""
            SELECT 1
            FROM member_permission_overrides
            WHERE environment_id = :eid
              AND user_id = :uid
              AND permission_code = :p
              AND effect = 'DENY'
            LIMIT 1
        """),
        {"eid": str(environment_id), "uid": str(user_id), "p": permission_code},
    ).first()
    if deny:
        return False

    allow = db.execute(
        sa.text("""
            SELECT 1
            FROM member_permission_overrides
            WHERE environment_id = :eid
              AND user_id = :uid
              AND permission_code = :p
              AND effect = 'ALLOW'
            LIMIT 1
        """),
        {"eid": str(environment_id), "uid": str(user_id), "p": permission_code},
    ).first()
    if allow:
        return True

    role_perm = db.execute(
        sa.text("""
            SELECT 1
            FROM environment_members em
            JOIN role_permissions rp ON rp.role_id = em.role_id
            WHERE em.environment_id = :eid
              AND em.user_id = :uid
              AND em.status = 'ACTIVE'
              AND rp.permission_code = :p
            LIMIT 1
        """),
        {"eid": str(environment_id), "uid": str(user_id), "p": permission_code},
    ).first()
    return bool(role_perm)


def can_share_card(user: User, card: Card, holder: Optional[CardHolder]) -> bool:
    """
    Verifica se um usuário tem permissão para compartilhar um cartão específico.

    Regra de Negócio:
    O usuário só pode compartilhar o cartão se o CPF do Titular do cartão (CardHolder)
    for exatamente igual ao CPF do próprio usuário logado.
    """
    if not holder or not user.cpf:
        return False

    return holder.cpf == user.cpf
