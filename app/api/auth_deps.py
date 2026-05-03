import uuid

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config.settings import settings
from app.infra.db.orm_models import User
from app.shared.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

SUPABASE_JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

jwks_client = PyJWKClient(SUPABASE_JWKS_URL)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Não autenticado")

    token = creds.credentials
    user_id = None

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
    except Exception:
        pass

    if not user_id:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience="authenticated",
            )
            user_id = payload.get("sub")

        except Exception as e:
            print(f"DEBUG ERRO FATAL JWT: {type(e).__name__} - {str(e)}")
            raise HTTPException(
                status_code=401, detail=f"Token Supabase inválido ou expirado: {str(e)}"
            )

    try:
        uid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Formato de ID de usuário inválido")

    user = db.get(User, uid)

    if not user:
        raise HTTPException(
            status_code=401, detail="Utilizador não encontrado no sistema local"
        )

    return user
