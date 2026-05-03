import uuid
from typing import Optional

from pydantic import BaseModel, Field


class CardHolderOut(BaseModel):
    id: uuid.UUID
    cpf: str
    name: str


class CardHolderCreateIn(BaseModel):
    cpf: str = Field(min_length=5, max_length=20)
    name: str = Field(min_length=2, max_length=120)


class CardOut(BaseModel):
    id: uuid.UUID
    last4: str
    description: str | None = None
    brand: str | None
    due_day: int
    pay_day: int
    holder_id: uuid.UUID | None = None
    holder_name: str | None = None


class CardCreateIn(BaseModel):
    last4: str = Field(min_length=4, max_length=4)
    description: str | None = None
    brand: str | None = None
    due_day: int = Field(ge=1, le=31)
    pay_day: int = Field(ge=1, le=31)
    holder_id: uuid.UUID | None = None


class CardUpdateIn(BaseModel):
    brand: str | None = None
    description: str | None = None
    due_day: int | None = Field(default=None, ge=1, le=31)
    pay_day: int | None = Field(default=None, ge=1, le=31)
    holder_id: uuid.UUID | None = None


class CardShareRequest(BaseModel):
    email: str


class CardShareResponse(BaseModel):
    message: str
    status: str
    shared_card_id: Optional[uuid.UUID] = None
