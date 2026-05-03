from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

EnvTypeCreate = Literal["FAMILY", "FRIENDS", "BUSINESS"]


class EnvironmentSettings(BaseModel):
    require_payment_confirmation: bool = False
    require_category_on_transactions: bool = False
    auto_fiscal_closing: bool = False


class EnvironmentOut(BaseModel):
    id: str
    type: str
    name: str
    owner_user_id: str
    owner_name: str
    is_owner: bool
    expires_at: datetime | None
    is_archived: bool
    settings: EnvironmentSettings


class UpdateEnvironmentIn(BaseModel):
    name: str | None = None
    expires_at: datetime | None = None
    is_archived: bool | None = None
    settings: EnvironmentSettings | None = None


class CreateEnvironmentIn(BaseModel):
    type: EnvTypeCreate
    name: str = Field(min_length=2, max_length=80)
    expires_at: Optional[datetime] = None


class InviteIn(BaseModel):
    email: str
    role_name: Literal["Admin", "Member", "Viewer"] = "Member"
    expires_in_hours: int = 24


class AcceptInviteIn(BaseModel):
    token: str


class InviteOut(BaseModel):
    token: str
    expires_at: datetime


class MemberOut(BaseModel):
    user_id: str
    name: str
    email: str
    role_name: str
    status: str
    joined_at: datetime


class InviteDetailOut(BaseModel):
    id: str
    email: str
    role_name: str
    status: str
    token: str
    created_at: datetime
    expires_at: datetime


class RoleOut(BaseModel):
    id: str
    name: str
    is_system: bool
