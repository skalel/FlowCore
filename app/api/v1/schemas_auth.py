from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    requires_2fa: bool = False
    temp_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    plan_tier: str


class Enable2FAIn(BaseModel):
    secret: str
    code: str


class Verify2FAIn(BaseModel):
    temp_token: str
    code: str
