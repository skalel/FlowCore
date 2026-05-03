from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config.settings import settings

pwd = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(raw: str) -> str:
    return pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd.verify(raw, hashed)


def create_access_token(sub: str, role: str = "USER") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRES_MIN)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_refresh_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_access_token(token: str) -> dict:
    """Decodifica o access token aplicando rigorosamente a verificação de expiração."""
    options = {"require": ["exp", "iat", "sub", "iss", "type"]}

    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALG],
        issuer=settings.JWT_ISSUER,
        options=options,
    )

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token inválido. Esperado um access token.")

    return payload


def verify_refresh_token(token: str) -> str | None:
    """Decodifica e verifica se é um refresh token válido."""
    try:
        options = {"require": ["exp", "iat", "sub", "iss", "type"]}
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALG],
            issuer=settings.JWT_ISSUER,
            options=options,
        )
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except Exception:
        return None


def create_password_reset_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    to_encode = {"sub": user_id, "exp": expire, "type": "reset_password"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded_token = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG]
        )
        if decoded_token.get("type") != "reset_password":
            return None
        return decoded_token.get("sub")
    except Exception:
        return None


def create_pre_auth_token(sub: str) -> str:
    """Cria um token temporário de 5 minutos apenas para a ponte do 2FA."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode = {"sub": sub, "exp": expire, "type": "pre-auth"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def verify_pre_auth_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        if payload.get("type") != "pre-auth":
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
