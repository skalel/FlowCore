import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.api.v1.schemas_categories import (
    CategoryChangeOut,
    CategoryCreateIn,
    CategoryKind,
    CategoryOut,
    CategoryUpdateIn,
)
from app.infra.db.orm_models import Category, CategoryChange, Transaction, User
from app.services.ai_service import suggest_single_category

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "",
    response_model=list[CategoryOut],
    dependencies=[
        Depends(require_permission("categories:read", get_environment_id_from_header))
    ],
)
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
    kind: Optional[CategoryKind] = Query(default=None),
):
    q = sa.select(Category).where(
        Category.environment_id == env_id,
        Category.deleted_at.is_(None),
        sa.or_(
            Category.is_default.is_(True),
            Category.owner_user_id == current_user.id,
        ),
    )
    if kind:
        q = q.where(Category.kind == kind)

    q = q.order_by(Category.is_default.desc(), Category.kind.asc(), Category.name.asc())
    items = db.execute(q).scalars().all()

    return [
        CategoryOut(
            id=c.id,
            kind=c.kind,
            name=c.name,
            is_default=c.is_default,
            owner_user_id=c.owner_user_id,
        )
        for c in items
    ]


@router.post(
    "",
    response_model=CategoryOut,
    dependencies=[
        Depends(
            require_permission("categories:manage_own", get_environment_id_from_header)
        )
    ],
)
def create_category(
    payload: CategoryCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    c = Category(
        environment_id=env_id,
        kind=payload.kind,
        name=payload.name.strip(),
        is_default=False,
        owner_user_id=current_user.id,
    )
    db.add(c)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category already exists")
    db.refresh(c)

    return CategoryOut(
        id=c.id,
        kind=c.kind,
        name=c.name,
        is_default=c.is_default,
        owner_user_id=c.owner_user_id,
    )


@router.patch(
    "/{category_id}",
    response_model=CategoryOut,
    dependencies=[
        Depends(
            require_permission("categories:manage_own", get_environment_id_from_header)
        )
    ],
)
def update_category(
    category_id: str,
    payload: CategoryUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        cid = uuid.UUID(category_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid category_id")

    c: Category | None = db.get(Category, cid)
    if not c or c.environment_id != env_id or c.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    if c.is_default or c.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only edit your own custom categories"
        )

    old_name, old_kind = c.name, c.kind

    if payload.name is not None:
        c.name = payload.name.strip()
    if payload.kind is not None:
        c.kind = payload.kind

    db.add(
        CategoryChange(
            category_id=c.id,
            environment_id=env_id,
            changed_by_user_id=current_user.id,
            old_name=old_name,
            new_name=c.name,
            old_kind=old_kind,
            new_kind=c.kind,
        )
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category already exists")

    db.refresh(c)

    return CategoryOut(
        id=c.id,
        kind=c.kind,
        name=c.name,
        is_default=c.is_default,
        owner_user_id=c.owner_user_id,
    )


@router.get(
    "/{category_id}/history",
    response_model=list[CategoryChangeOut],
    dependencies=[
        Depends(require_permission("categories:read", get_environment_id_from_header))
    ],
)
def category_history(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        cid = uuid.UUID(category_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid category_id")

    c = db.execute(
        sa.select(Category).where(
            Category.id == cid,
            Category.environment_id == env_id,
            Category.deleted_at.is_(None),
            sa.or_(
                Category.is_default.is_(True), Category.owner_user_id == current_user.id
            ),
        )
    ).scalar_one_or_none()

    if not c:
        raise HTTPException(status_code=404, detail="Not found")

    rows = (
        db.execute(
            sa.select(CategoryChange)
            .where(
                CategoryChange.category_id == cid,
                CategoryChange.environment_id == env_id,
            )
            .order_by(CategoryChange.changed_at.desc())
        )
        .scalars()
        .all()
    )

    return [
        CategoryChangeOut(
            old_name=r.old_name,
            new_name=r.new_name,
            old_kind=r.old_kind,
            new_kind=r.new_kind,
            changed_at=r.changed_at,
            changed_by_user_id=r.changed_by_user_id,
        )
        for r in rows
    ]


@router.delete(
    "/{category_id}",
    dependencies=[
        Depends(
            require_permission("categories:manage_own", get_environment_id_from_header)
        )
    ],
)
def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        cid = uuid.UUID(category_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid category_id")

    c: Category | None = db.get(Category, cid)
    if not c or c.environment_id != env_id or c.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    if c.is_default or c.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only delete your own custom categories"
        )

    c.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "deleted"}


@router.get("/suggest")
def suggest_category(
    description: str = Query(..., min_length=2),
    kind: str = Query(..., pattern="^(INCOME|EXPENSE)$"),
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    """Retorna uma sugestão de categoria baseada no histórico ou na IA."""

    historic_cat = db.execute(
        sa.select(Category.id, Category.name)
        .join(Transaction, Transaction.category_id == Category.id)
        .where(
            Transaction.environment_id == env_id,
            Transaction.kind == kind,
            Transaction.description.ilike(f"%{description}%"),
        )
        .group_by(Category.id, Category.name)
        .order_by(sa.func.count(Transaction.id).desc())
        .limit(1)
    ).first()

    if historic_cat:
        return {"id": str(historic_cat.id), "name": historic_cat.name, "is_new": False}

    existing_cats = (
        db.execute(
            sa.select(Category.name).where(
                Category.environment_id == env_id, Category.kind == kind
            )
        )
        .scalars()
        .all()
    )

    suggested_name = suggest_single_category(description, kind, list(existing_cats))

    if suggested_name:
        existing = db.execute(
            sa.select(Category.id).where(
                Category.environment_id == env_id,
                sa.func.lower(Category.name) == suggested_name.lower(),
                Category.kind == kind,
            )
        ).scalar_one_or_none()

        if existing:
            return {"id": str(existing), "name": suggested_name, "is_new": False}

        return {"id": None, "name": suggested_name, "is_new": True}

    return None
