import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.infra.db.orm_models import Category, Environment

EXPENSE_DEFAULTS = [
    "Contas",
    "Mercado",
    "Educação",
    "Saúde",
    "Comida",
    "Assinaturas",
    "Transporte",
    "Lazer",
    "Moradia",
]

INCOME_DEFAULTS = [
    "Salário",
    "Freelance",
    "Vendas",
    "Reembolso",
    "Outros",
]


def seed_environment_categories(db: Session, env_id: uuid.UUID) -> int:
    """
    Initializes the default categories for a single environment.
    """
    existing = db.execute(
        sa.select(Category.kind, Category.name).where(
            Category.environment_id == env_id,
            Category.is_default.is_(True),
            Category.deleted_at.is_(None),
        )
    ).all()

    existing_set = {(k, n) for (k, n) in existing}
    categories_to_insert = []

    for name in EXPENSE_DEFAULTS:
        if ("EXPENSE", name) not in existing_set:
            categories_to_insert.append(
                Category(
                    environment_id=env_id,
                    kind="EXPENSE",
                    name=name,
                    is_default=True,
                    owner_user_id=None,
                )
            )

    for name in INCOME_DEFAULTS:
        if ("INCOME", name) not in existing_set:
            categories_to_insert.append(
                Category(
                    environment_id=env_id,
                    kind="INCOME",
                    name=name,
                    is_default=True,
                    owner_user_id=None,
                )
            )

    if categories_to_insert:
        db.add_all(categories_to_insert)
        db.flush()

    return len(categories_to_insert)


def seed_all_environments(db: Session) -> dict:
    """
    Initializes the default categories for all environments.
    """
    env_ids = db.execute(sa.select(Environment.id)).scalars().all()

    if not env_ids:
        return {"environments": 0, "created": 0}

    total_created = 0

    for env_id in env_ids:
        created = seed_environment_categories(db, env_id)
        total_created += created

    db.commit()
    return {"environments": len(env_ids), "created": total_created}
