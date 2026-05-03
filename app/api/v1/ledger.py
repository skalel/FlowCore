import uuid
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.api.v1.schemas_ledger import (
    TransactionCreateIn,
    TransactionOut,
    TransactionUpdateIn,
)
from app.api.v1.schemas_ledger_list import TransactionsListOut
from app.domain.policies.permissions import has_permission
from app.domain.services.due_date import next_due_date
from app.domain.services.fiscal_lock import is_month_closed
from app.infra.db.orm_models import Transaction, User

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _month_range(ref: date) -> tuple[date, date]:
    start = date(ref.year, ref.month, 1)
    if ref.month == 12:
        end = date(ref.year + 1, 1, 1)
    else:
        end = date(ref.year, ref.month + 1, 1)
    return start, end


def _get_card_due_day(db: Session, card_id: uuid.UUID, env_id: uuid.UUID) -> int:
    row = db.execute(
        sa.text(
            "SELECT due_day FROM cards WHERE id = :cid AND environment_id = :eid LIMIT 1"
        ),
        {"cid": str(card_id), "eid": str(env_id)},
    ).first()
    if not row:
        raise HTTPException(
            status_code=422, detail="Invalid card_id for this environment"
        )
    return int(row[0])


@router.post(
    "",
    response_model=TransactionOut,
    dependencies=[
        Depends(require_permission("ledger:create", get_environment_id_from_header))
    ],
)
def create_transaction(
    payload: TransactionCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    due_on = payload.due_on
    if due_on is None and payload.payment_method == "CREDIT" and payload.card_id:
        due_day = _get_card_due_day(db, payload.card_id, env_id)
        due_on = next_due_date(payload.occurred_on, due_day)

    ref_date = due_on or payload.occurred_on
    if is_month_closed(db, env_id, ref_date):
        raise HTTPException(
            status_code=409, detail="Month is closed for this transaction date"
        )

    tx = Transaction(
        environment_id=env_id,
        created_by_user_id=current_user.id,
        kind=payload.kind,
        occurred_on=payload.occurred_on,
        due_on=due_on,
        amount=payload.amount,
        description=payload.description,
        category_id=payload.category_id,
        payment_method=payload.payment_method,
        card_id=payload.card_id,
        paid_on=payload.paid_on,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    return TransactionOut(
        id=tx.id,
        kind=tx.kind,
        occurred_on=tx.occurred_on,
        due_on=tx.due_on,
        amount=float(tx.amount),
        description=tx.description,
        category_id=tx.category_id,
        payment_method=tx.payment_method,
        card_id=tx.card_id,
        paid_on=tx.paid_on,
    )


@router.get(
    "",
    response_model=TransactionsListOut,
    dependencies=[
        Depends(require_permission("ledger:read", get_environment_id_from_header))
    ],
)
def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    payment_methods: list[str] = Query(
        default=[], description="Lista de métodos de pagamento"
    ),
    card_ids: list[str] = Query(default=[], description="Lista de IDs de cartões"),
    search: str | None = Query(default=None, description="Termo de busca global"),
):
    today = datetime.now(timezone.utc).date()
    ref = date(year, month, 1) if (year and month) else today
    start, end = _month_range(ref)

    params = {"eid": str(env_id), "start": start, "end": end}

    extra_filters = ""

    if payment_methods:
        pm_binds = []
        for i, pm in enumerate(payment_methods):
            bind_name = f"pm_{i}"
            pm_binds.append(f":{bind_name}")
            params[bind_name] = pm
        extra_filters += f" AND payment_method IN ({', '.join(pm_binds)})"

    if card_ids:
        cid_binds = []
        for i, cid in enumerate(card_ids):
            bind_name = f"cid_{i}"
            cid_binds.append(f":{bind_name}")
            params[bind_name] = cid
        extra_filters += f" AND card_id IN ({', '.join(cid_binds)})"

    if search:
        search_clean = search.strip()
        params["search_like"] = f"%{search_clean}%"
        params["search_exact"] = search_clean

        search_clause = """ AND (
            description ILIKE :search_like
            OR card_id IN (SELECT id FROM cards WHERE last4 = :search_exact AND environment_id = :eid)
        """

        try:
            search_num = float(search_clean.replace(",", "."))
            params["search_num"] = search_num
            search_clause += " OR amount = :search_num"
        except ValueError:
            pass

        search_clause += ")"
        extra_filters += search_clause

    # Query do Mês Atual
    current_rows = (
        db.execute(
            sa.text(f"""
        SELECT id, kind, occurred_on, due_on, amount, description, category_id, payment_method, card_id, paid_on
        FROM transactions
        WHERE environment_id = :eid
          AND deleted_at IS NULL
          AND status = 'POSTED'
          AND COALESCE(due_on, occurred_on) >= :start
          AND COALESCE(due_on, occurred_on) < :end
          {extra_filters}
        ORDER BY COALESCE(due_on, occurred_on) ASC, occurred_on ASC
    """),
            params,
        )
        .mappings()
        .all()
    )

    # Query do Futuro
    future_rows = (
        db.execute(
            sa.text(f"""
        SELECT id, kind, occurred_on, due_on, amount, description, category_id, payment_method, card_id, paid_on
        FROM transactions
        WHERE environment_id = :eid
          AND deleted_at IS NULL
          AND status = 'POSTED'
          AND occurred_on >= :start
          AND occurred_on < :end
          AND due_on IS NOT NULL
          AND due_on >= :end
          {extra_filters}
        ORDER BY due_on ASC, occurred_on ASC
    """),
            params,
        )
        .mappings()
        .all()
    )

    def _map(r):
        return TransactionOut(
            id=str(r["id"]),
            kind=r["kind"],
            occurred_on=r["occurred_on"],
            due_on=r["due_on"],
            amount=float(r["amount"]),
            description=r["description"],
            category_id=str(r["category_id"]),
            payment_method=r["payment_method"],
            card_id=str(r["card_id"]) if r["card_id"] else None,
            paid_on=r["paid_on"],
        )

    is_closed = is_month_closed(db, env_id, ref)

    return TransactionsListOut(
        month_start=start,
        month_end=end,
        is_closed=is_closed,
        current_month=[_map(r) for r in current_rows],
        future=[_map(r) for r in future_rows],
    )


@router.patch(
    "/{transaction_id}",
    response_model=TransactionOut,
    dependencies=[
        Depends(require_permission("ledger:update", get_environment_id_from_header))
    ],
)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        tid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid transaction_id")

    tx: Transaction | None = db.get(Transaction, tid)
    if not tx or tx.environment_id != env_id or tx.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    new_occurred = payload.occurred_on or tx.occurred_on
    new_due = payload.due_on if payload.due_on is not None else tx.due_on
    ref_date = new_due or new_occurred
    if is_month_closed(db, env_id, ref_date):
        raise HTTPException(
            status_code=409, detail="Month is closed for this transaction date"
        )

    data = payload.model_dump(exclude_unset=True)

    if data.get("kind") == "INCOME" or (tx.kind == "INCOME" and "kind" not in data):
        if data.get("paid_on"):
            raise HTTPException(
                status_code=400, detail="Receitas não podem receber baixa."
            )
        data["paid_on"] = None

    for field, value in data.items():
        setattr(tx, field, value)

    db.commit()
    db.refresh(tx)

    return TransactionOut(
        id=tx.id,
        kind=tx.kind,
        occurred_on=tx.occurred_on,
        due_on=tx.due_on,
        amount=float(tx.amount),
        description=tx.description,
        category_id=tx.category_id,
        payment_method=tx.payment_method,
        card_id=tx.card_id,
        paid_on=tx.paid_on,
    )


@router.delete(
    "/{transaction_id}",
    dependencies=[
        Depends(
            require_permission("ledger:delete_soft", get_environment_id_from_header)
        )
    ],
)
def delete_transaction(
    transaction_id: str,
    hard: bool = Query(default=False, description="Hard delete (requires permission)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    try:
        tid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid transaction_id")

    tx: Transaction | None = db.get(Transaction, tid)
    if not tx or tx.environment_id != env_id or tx.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    ref_date = tx.due_on or tx.occurred_on
    if is_month_closed(db, env_id, ref_date):
        raise HTTPException(
            status_code=409, detail="Month is closed for this transaction date"
        )

    now = datetime.now(timezone.utc)

    within_24h = (now - tx.created_at) <= timedelta(hours=24)

    if hard:
        allowed_hard = has_permission(
            db,
            environment_id=env_id,
            user_id=current_user.id,
            permission_code="ledger:delete_hard",
        )

        if not allowed_hard:
            raise HTTPException(
                status_code=403, detail="Missing permission ledger:delete_hard"
            )

        db.execute(
            sa.text("""
        INSERT INTO audit_log (id, environment_id, actor_user_id, action, entity_type, entity_id, created_at)
        VALUES (gen_random_uuid(), :eid, :uid, 'TRANSACTION_HARD_DELETE', 'transaction', :tid, now())
        """),
            {
                "eid": str(env_id),
                "uid": str(current_user.id),
                "tid": str(tx.id),
            },
        )

        db.delete(tx)
        db.commit()
        return {"status": "hard_deleted"}

    if within_24h:
        db.execute(
            sa.text("""
        INSERT INTO audit_log (id, environment_id, actor_user_id, action, entity_type, entity_id, created_at)
        VALUES (gen_random_uuid(), :eid, :uid, 'TRANSACTION_HARD_DELETE', 'transaction', :tid, now())
        """),
            {
                "eid": str(env_id),
                "uid": str(current_user.id),
                "tid": str(tx.id),
            },
        )
        db.delete(tx)
        db.commit()
        return {"status": "hard_deleted"}

    tx.deleted_at = now
    db.commit()
    return {"status": "soft_deleted"}
