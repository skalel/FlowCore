import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class ConnectionRequestCreate(BaseModel):
    email: EmailStr


class ConnectionActionResponse(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    addressee_id: uuid.UUID
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class FriendInfo(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    avatar_url: Optional[str] = None


class ConnectionListResponse(BaseModel):
    id: uuid.UUID
    status: str
    is_requester: bool
    friend: FriendInfo

    class Config:
        from_attributes = True
