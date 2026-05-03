import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["INCOME", "EXPENSE"]
PayMethod = Literal["CASH", "PIX", "DEBIT", "CREDIT", "TRANSFER", "OTHER"]


class TransactionCreateIn(BaseModel):
    kind: Kind
    occurred_on: date
    amount: float = Field(gt=0)
    description: str = Field(min_length=2, max_length=300)
    category_id: uuid.UUID
    payment_method: PayMethod = "OTHER"
    card_id: uuid.UUID | None = None
    due_on: date | None = None
    paid_on: date | None = None


class TransactionUpdateIn(BaseModel):
    occurred_on: date | None = None
    due_on: date | None = None
    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=2, max_length=300)
    category_id: uuid.UUID | None = None
    payment_method: PayMethod | None = None
    card_id: uuid.UUID | None = None
    paid_on: date | None = None


class TransactionOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    occurred_on: date
    due_on: date | None
    amount: float
    description: str
    category_id: uuid.UUID
    payment_method: PayMethod
    card_id: uuid.UUID | None
    paid_on: date | None = None


class ListQuery(BaseModel):
    # não usado diretamente; só referência
    pass
