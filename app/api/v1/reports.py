from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
import uuid
from datetime import date, datetime, timezone

from app.api.deps import get_db
from app.api.auth_deps import get_current_user
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.infra.db.orm_models import User
from app.api.v1.schemas_reports import ReportItemOut, MonthlyReportOut, CategoryAgg, MethodAgg

router = APIRouter(prefix="/reports", tags=["reports"])

def _month_range(ref: date) -> tuple[date, date]:
    start = date(ref.year, ref.month, 1)
    if ref.month == 12:
        end = date(ref.year + 1, 1, 1)
    else:
        end = date(ref.year, ref.month + 1, 1)
    return start, end

@router.get(
    "/monthly",
    response_model=MonthlyReportOut,
    dependencies=[Depends(require_permission("reports:read", get_environment_id_from_header))],
)
def monthly_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID | None = Depends(get_environment_id_from_header),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
):
    if not env_id:
        raise HTTPException(
            status_code=400, 
            detail="Selecione um ambiente para gerar o relatório mensal."
        )

    today = datetime.now(timezone.utc).date()
    
    if year and month:
        ref = date(year, month, 1)
    else:
        ref = today
        
    start, end = _month_range(ref)

    base_where = """
      environment_id = :eid
      AND deleted_at IS NULL
      AND COALESCE(due_on, occurred_on) >= :start
      AND COALESCE(due_on, occurred_on) < :end
      AND status = 'POSTED'
    """

    params = {
        "eid": str(env_id), 
        "start": start, 
        "end": end, 
        "today": today
    }

    items = db.execute(sa.text(f"""
    SELECT
      id::text AS id,
      kind,
      occurred_on,
      due_on,
      COALESCE(due_on, occurred_on) AS impact_on,
      amount,
      description,
      category_id::text AS category_id,
      payment_method,
      card_id::text AS card_id,
      paid_on
    FROM transactions
    WHERE {base_where}
    ORDER BY COALESCE(due_on, occurred_on) ASC, occurred_on ASC
    """), params).mappings().all()

    totals = db.execute(sa.text(f"""
        SELECT
          COALESCE(SUM(CASE WHEN kind='INCOME' THEN amount END), 0) AS total_income,
          COALESCE(SUM(CASE WHEN kind='EXPENSE' THEN amount END), 0) AS total_expense
        FROM transactions
        WHERE {base_where}
    """), params).mappings().one()

    total_income = float(totals["total_income"])
    total_expense = float(totals["total_expense"])
    balance = total_income - total_expense

    pending = db.execute(sa.text(f"""
        SELECT
          COUNT(*) AS pending_count,
          COALESCE(SUM(amount), 0) AS pending_total
        FROM transactions
        WHERE {base_where}
          AND paid_on IS NULL
          AND kind = 'EXPENSE'
          AND COALESCE(due_on, occurred_on) < :today
    """), params).mappings().one()

    by_cat_exp = db.execute(sa.text(f"""
        SELECT category_id::text AS category_id, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE {base_where} AND kind='EXPENSE'
        GROUP BY category_id
        ORDER BY total DESC
        LIMIT 12
    """), params).mappings().all()

    by_cat_inc = db.execute(sa.text(f"""
        SELECT category_id::text AS category_id, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE {base_where} AND kind='INCOME'
        GROUP BY category_id
        ORDER BY total DESC
        LIMIT 12
    """), params).mappings().all()

    by_method = db.execute(sa.text(f"""
        SELECT payment_method AS payment_method, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE {base_where}
        GROUP BY payment_method
        ORDER BY total DESC
    """), params).mappings().all()

    # --- VERIFICAÇÃO FISCAL ---
    is_closed = db.execute(sa.text("""
        SELECT 1 FROM fiscal_closures 
        WHERE environment_id = :eid AND year = :y AND month = :m AND status = 'CLOSED'
    """), {"eid": str(env_id), "y": ref.year, "m": ref.month}).scalar() is not None

    prev_y = ref.year if ref.month > 1 else ref.year - 1
    prev_m = ref.month - 1 if ref.month > 1 else 12
    
    prev_is_closed = db.execute(sa.text("""
        SELECT 1 FROM fiscal_closures 
        WHERE environment_id = :eid AND year = :y AND month = :m AND status = 'CLOSED'
    """), {"eid": str(env_id), "y": prev_y, "m": prev_m}).scalar() is not None

    return MonthlyReportOut(
        month_start=start,
        month_end=end,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        pending_count=int(pending["pending_count"]),
        pending_total=float(pending["pending_total"]),
        by_category_expense=[CategoryAgg(**{"category_id": r["category_id"], "total": float(r["total"])}) for r in by_cat_exp],
        by_category_income=[CategoryAgg(**{"category_id": r["category_id"], "total": float(r["total"])}) for r in by_cat_inc],
        by_method=[MethodAgg(**{"payment_method": r["payment_method"], "total": float(r["total"])}) for r in by_method],
        items=[ReportItemOut(**item) for item in items],
        is_closed=is_closed,
        previous_month_is_closed=prev_is_closed
    )