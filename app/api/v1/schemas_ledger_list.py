from pydantic import BaseModel
from datetime import date
from app.api.v1.schemas_ledger import TransactionOut

class TransactionsListOut(BaseModel):
    month_start: date
    month_end: date
    current_month: list[TransactionOut]
    future: list[TransactionOut]
    is_closed: bool = False