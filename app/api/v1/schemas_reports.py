from pydantic import BaseModel
from datetime import date
from typing import Optional,Literal

class CategoryAgg(BaseModel):
    category_id: str
    total: float

class MethodAgg(BaseModel):
    payment_method: str
    total: float

class ReportItemOut(BaseModel):
    id: str
    kind: Literal["INCOME", "EXPENSE"]
    occurred_on: date
    due_on: Optional[date] = None
    impact_on: date
    amount: float
    description: Optional[str] = None
    category_id: Optional[str] = None
    payment_method: Optional[str] = None
    card_id: Optional[str] = None
    paid_on: Optional[date] = None

class MonthlyReportOut(BaseModel):
    month_start: date
    month_end: date

    total_income: float
    total_expense: float
    balance: float

    pending_count: int
    pending_total: float

    by_category_expense: list[CategoryAgg]
    by_category_income: list[CategoryAgg]
    by_method: list[MethodAgg]
    items: list[ReportItemOut] = []
    is_closed: bool = False
    previous_month_is_closed: bool = True