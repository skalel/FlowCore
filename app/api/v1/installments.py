import calendar
import uuid
from datetime import date

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.api.v1.schemas_installments import InstallmentCreateIn
from app.infra.db.orm_models import (
    FiscalClosure,
    Installment,
    InstallmentOccurrence,
    Transaction,
    User,
)

router = APIRouter(tags=["installments"])


def add_months(sourcedate: date, months: int) -> date:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@router.post(
    "/installments",
    dependencies=[
        Depends(require_permission("ledger:create", get_environment_id_from_header))
    ],
)
def create_installment(
    payload: InstallmentCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    if payload.current_installment > payload.total_installments:
        raise HTTPException(
            422, "A parcela atual não pode ser maior que o total de parcelas."
        )

    months_to_subtract = payload.current_installment - 1
    first_due_date = add_months(payload.current_due_date, -months_to_subtract)

    base_installment_amount = round(
        payload.total_amount / payload.total_installments, 2
    )
    total_base = base_installment_amount * payload.total_installments
    difference = round(payload.total_amount - total_base, 2)

    inst = Installment(
        environment_id=env_id,
        kind="PURCHASE",
        title=payload.title,
        principal_amount=payload.total_amount,
        total_installments=payload.total_installments,
        installment_amount=base_installment_amount,
        first_due_on=first_due_date,
        current_installment=payload.current_installment,
        card_id=payload.card_id,
        created_by_user_id=current_user.id,
    )
    db.add(inst)
    db.flush()

    created_txs = 0
    first_generated_index = (
        1 if payload.generate_retroactive else payload.current_installment
    )

    for i in range(1, payload.total_installments + 1):
        occ_due_date = add_months(first_due_date, i - 1)
        is_retroactive = i < payload.current_installment

        if is_retroactive and not payload.generate_retroactive:
            continue

        closure = db.execute(
            sa.select(FiscalClosure).where(
                FiscalClosure.environment_id == env_id,
                FiscalClosure.year == occ_due_date.year,
                FiscalClosure.month == occ_due_date.month,
                FiscalClosure.status == "CLOSED",
            )
        ).scalar_one_or_none()

        if closure:
            if is_retroactive:
                closure.status = "OPEN"
                closure.updated_at = sa.func.now()
                db.execute(
                    sa.text("""
                    INSERT INTO audit_log (id, environment_id, actor_user_id, action, entity_type, entity_id)
                    VALUES (gen_random_uuid(), :eid, :uid, 'FISCAL_AUTO_REOPEN', 'fiscal_closures', :cid)
                    """),
                    {
                        "eid": str(env_id),
                        "uid": str(current_user.id),
                        "cid": str(closure.id),
                    },
                )
            else:
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail=f"O mês fiscal {occ_due_date.month:02d}/{occ_due_date.year} está fechado.",
                )

        current_amount = (
            base_installment_amount + difference
            if i == first_generated_index
            else base_installment_amount
        )

        paid_on_date = occ_due_date if is_retroactive else None

        tx = Transaction(
            environment_id=env_id,
            created_by_user_id=current_user.id,
            kind="EXPENSE",
            occurred_on=payload.purchase_date,
            due_on=occ_due_date,
            amount=current_amount,
            description=f"{payload.title} ({i}/{payload.total_installments})",
            category_id=payload.category_id,
            payment_method=payload.payment_method,
            card_id=payload.card_id,
            installment_id=inst.id,
            paid_on=paid_on_date,
        )
        db.add(tx)
        db.flush()

        occ = InstallmentOccurrence(
            installment_id=inst.id,
            installment_number=i,
            due_on=occ_due_date,
            transaction_id=tx.id,
        )
        db.add(occ)
        created_txs += 1

    db.commit()

    return {
        "id": str(inst.id),
        "title": inst.title,
        "transactions_generated": created_txs,
    }
