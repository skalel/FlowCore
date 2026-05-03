from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime
import uuid

CategoryKind = Literal["INCOME", "EXPENSE"]

class CategoryOut(BaseModel):
    id: uuid.UUID
    kind: CategoryKind
    name: str
    is_default: bool
    owner_user_id: uuid.UUID | None

class CategoryCreateIn(BaseModel):
    kind: CategoryKind
    name: str = Field(min_length=2, max_length=80)

class CategoryUpdateIn(BaseModel):
    kind: CategoryKind | None = None
    name: str | None = Field(default=None, min_length=2, max_length=80)

class CategoryChangeOut(BaseModel):
    old_name: str
    new_name: str
    old_kind: CategoryKind
    new_kind: CategoryKind
    changed_at: datetime
    changed_by_user_id: uuid.UUID