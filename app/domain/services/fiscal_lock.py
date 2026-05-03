from datetime import date
import sqlalchemy as sa
from sqlalchemy.orm import Session
import uuid

def is_month_closed(db: Session, environment_id: uuid.UUID, ref_date: date) -> bool:
    row = db.execute(
        sa.text("""
            SELECT 1
            FROM fiscal_closures
            WHERE environment_id = :eid
              AND year = :y
              AND month = :m
              AND status = 'CLOSED'
            LIMIT 1
        """),
        {"eid": str(environment_id), "y": ref_date.year, "m": ref_date.month},
    ).first()
    return bool(row)