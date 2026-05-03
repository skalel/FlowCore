from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.infra.db.orm_models import Environment, FiscalClosure, Transaction


def process_automated_fiscal_closing(db: Session) -> dict:
    """
    Runs on the 1st of every month to auto-close the previous month
    for environments that have 'auto_fiscal_closing' enabled.
    """
    today = datetime.now(timezone.utc)
    first_day_current_month = today.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    last_day_prev_month = first_day_current_month - timedelta(days=1)

    target_month = last_day_prev_month.month
    target_year = last_day_prev_month.year

    eligible_envs = (
        db.execute(
            sa.select(Environment).where(
                Environment.settings["auto_fiscal_closing"].as_boolean().is_(True),
                Environment.is_archived.is_(False),
            )
        )
        .scalars()
        .all()
    )

    closed_count = 0

    for env in eligible_envs:
        existing_closure = db.execute(
            sa.select(FiscalClosure).where(
                FiscalClosure.environment_id == env.id,
                FiscalClosure.year == target_year,
                FiscalClosure.month == target_month,
                FiscalClosure.status == "CLOSED",
            )
        ).scalar_one_or_none()

        if existing_closure:
            continue

        transactions = (
            db.execute(
                sa.select(Transaction).where(
                    Transaction.environment_id == env.id,
                    sa.extract("month", Transaction.occurred_on) == target_month,
                    sa.extract("year", Transaction.occurred_on) == target_year,
                )
            )
            .scalars()
            .all()
        )

        should_close = False

        if not transactions:
            should_close = True
        else:
            expenses = [t for t in transactions if t.kind == "EXPENSE"]

            if all(expense.paid_on is not None for expense in expenses):
                should_close = True

        if should_close:
            _execute_system_closure(db, env, target_year, target_month)
            closed_count += 1

    db.commit()
    return {
        "message": f"Fechamento automático concluído. {closed_count} ambientes fechados."
    }


def _execute_system_closure(db: Session, env: Environment, year: int, month: int):
    """
    Executes the system closure for the given environment, year, and month.
    """
    closure = db.execute(
        sa.select(FiscalClosure)
        .where(FiscalClosure.environment_id == env.id)
        .where(FiscalClosure.year == year)
        .where(FiscalClosure.month == month)
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    system_note = "Fechamento automático realizado pelo sistema."

    if closure:
        closure.status = "CLOSED"
        closure.closed_by_user_id = env.owner_user_id
        closure.closed_at = now
        closure.note = system_note
        closure.updated_at = now
    else:
        new_closure = FiscalClosure(
            environment_id=env.id,
            year=year,
            month=month,
            status="CLOSED",
            closed_by_user_id=env.owner_user_id,
            closed_at=now,
            note=system_note,
        )
        db.add(new_closure)


def close_past_months_for_new_environment(db: Session, env: Environment):
    """
    Closes all months prior to the environment's creation month.
    """
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    start_point = current_month_start - relativedelta(months=12)

    cursor = start_point
    system_note = "Fechamento automático de boas-vindas (Proteção de histórico)."

    while cursor < current_month_start:
        closure = FiscalClosure(
            environment_id=env.id,
            year=cursor.year,
            month=cursor.month,
            status="CLOSED",
            closed_by_user_id=env.owner_user_id,
            closed_at=now,
            note=system_note,
        )
        db.add(closure)
        cursor += relativedelta(months=1)

    db.flush()
