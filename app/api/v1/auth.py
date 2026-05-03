import uuid
from datetime import datetime, timezone

import pyotp
import sqlalchemy as sa
import uuid6
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.v1.schemas_auth import (
    Enable2FAIn,
    LoginIn,
    RegisterIn,
    TokenOut,
    Verify2FAIn,
)
from app.api.v1.users import UserPreferences
from app.config.settings import settings
from app.domain.services.email_service import send_password_reset_email
from app.infra.db.orm_models import Environment, EnvironmentMember, User
from app.infra.integrations.supabase import supabase_anon
from app.services.category_service import seed_environment_categories
from app.services.fiscal_closing_service import close_past_months_for_new_environment
from app.shared.security import (
    create_access_token,
    create_password_reset_token,
    create_pre_auth_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_password_reset_token,
    verify_pre_auth_token,
    verify_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


class RefreshIn(BaseModel):
    refresh_token: str


def get_role_id_by_name(db: Session, name: str):
    """
    Returns the role ID by name.
    """
    role = db.execute(
        sa.text("SELECT id FROM roles WHERE name = :n LIMIT 1"), {"n": name}
    ).first()
    if not role:
        raise HTTPException(status_code=500, detail=f"Role seed '{name}' not found.")
    return role[0]


def create_user_onboarding(db: Session, user: User):
    """
    Creates the user's onboarding environment and default categories.
    """
    env = Environment(
        id=uuid6.uuid7(),
        type="SOLO",
        name="Meu ambiente",
        owner_user_id=user.id,
        is_archived=False,
        settings={"auto_fiscal_closing": True},
    )
    db.add(env)
    db.flush()

    close_past_months_for_new_environment(db, env)
    seed_environment_categories(db, env.id)

    owner_role_id = get_role_id_by_name(db, "Owner")

    member = EnvironmentMember(
        environment_id=env.id,
        user_id=user.id,
        role_id=owner_role_id,
        status="ACTIVE",
    )
    db.add(member)
    return env


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """
    Registers a new user with the provided email and password.
    """
    exists = db.execute(
        sa.select(User).where(User.email == payload.email)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="E-mail já registrado")

    user_id = uuid6.uuid7()
    user = User(
        id=user_id,
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        plan_tier="free",
        preferences=UserPreferences().model_dump(),
    )
    db.add(user)
    db.flush()

    create_user_onboarding(db, user)
    db.commit()

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return TokenOut(access_token=access, refresh_token=refresh, token_type="bearer")


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    """
    Logs the user in using the provided email and password.
    """
    user = db.execute(
        sa.select(User).where(User.email == payload.email)
    ).scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    if user.totp_secret:
        temp_token = create_pre_auth_token(str(user.id))
        return TokenOut(requires_2fa=True, temp_token=temp_token)

    user_role = "ADMIN" if user.is_superadmin else "USER"

    access = create_access_token(sub=str(user.id), role=user_role)
    refresh = create_refresh_token(str(user.id))
    return TokenOut(access_token=access, refresh_token=refresh, token_type="bearer")


@router.post("/login/2fa", response_model=TokenOut)
def login_2fa(payload: Verify2FAIn, db: Session = Depends(get_db)):
    """
    Verifies the 2FA code and logs the user in.
    """
    user_id = verify_pre_auth_token(payload.temp_token)
    if not user_id:
        raise HTTPException(
            status_code=401, detail="Sessão de login expirou. Tente novamente."
        )

    user = db.get(User, uuid.UUID(user_id))
    if not user or not user.totp_secret:
        raise HTTPException(
            status_code=400, detail="2FA não configurado para este utilizador."
        )

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.code):
        raise HTTPException(status_code=401, detail="Código 2FA inválido.")

    user_role = "ADMIN" if user.is_superadmin else "USER"
    access = create_access_token(sub=str(user.id), role=user_role)
    refresh = create_refresh_token(str(user.id))

    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Sends a password reset email to the user.
    """
    user = db.execute(
        sa.select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()

    if user:
        reset_token = create_password_reset_token(str(user.id))

        background_tasks.add_task(
            send_password_reset_email,
            to_email=user.email,
            user_name=user.name,
            token=reset_token,
        )

    return {
        "status": "success",
        "message": "Se o e-mail existir, um link de recuperação foi enviado.",
    }


@router.post("/reset-password")
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    """
    Resets the user's password using the provided token and new password.
    """
    user_id = verify_password_reset_token(payload.token)

    if not user_id:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    user = db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=422, detail="A nova senha deve ter pelo menos 6 caracteres."
        )

    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "success"}


@router.post("/refresh", response_model=TokenOut)
def refresh_session(
    payload: RefreshIn, response: Response, db: Session = Depends(get_db)
):
    """
    Refreshes the session using the provided refresh token.
    """
    refresh_token = payload.refresh_token
    new_access = None
    new_refresh = None
    user_id = None

    try:
        auth_res = supabase_anon.auth.refresh_session(refresh_token)
        if auth_res and auth_res.session:
            new_access = auth_res.session.access_token
            new_refresh = auth_res.session.refresh_token
            if auth_res.session.user:
                user_id = auth_res.session.user.id
    except Exception:
        pass

    if not new_access:
        user_id = verify_refresh_token(refresh_token)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Refresh token inválido ou expirado. Faça login novamente.",
            )

        new_access = create_access_token(str(user_id))
        new_refresh = create_refresh_token(str(user_id))

    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    user = db.get(User, uuid.UUID(str(user_id)))
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    response.set_cookie(
        key="flowspace_token",
        value=new_access,
        httponly=False,
        secure=True,
        samesite="lax",
        max_age=3600,
    )

    if new_refresh:
        response.set_cookie(
            key="flowspace_refresh",
            value=new_refresh,
            httponly=False,
            secure=True,
            samesite="lax",
            max_age=604800,
        )

    return TokenOut(
        access_token=new_access, refresh_token=new_refresh, token_type="bearer"
    )


@router.get("/oauth/login/{provider}")
def oauth_login(provider: str, next: str = "/dashboard"):
    """
    Gets the OAuth login URL and returns it to the frontend.
    """
    callback_url = f"{settings.API_BASE_URL}/api/v1/auth/oauth/callback?provider={provider}&next={next}"

    res = supabase_anon.auth.sign_in_with_oauth(
        {
            "provider": provider,
            "options": {
                "redirect_to": callback_url,
                "skip_browser_redirect": True,
            },
        }
    )

    return {"url": res.url}


@router.get("/oauth/callback")
def oauth_callback(
    code: str, provider: str, next: str = "/dashboard", db: Session = Depends(get_db)
):
    """
    Callback from OAuth
    Exchange the code for a session and synchronize the database.
    """
    try:
        session_data = supabase_anon.auth.exchange_code_for_session({"auth_code": code})
        session = session_data.session
        user_info = session_data.user

        if not session or not user_info:
            raise ValueError("Sessão ou usuário não retornados pelo Supabase.")

    except Exception as e:
        print(f"Erro no callback OAuth: {e}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=oauth_failed")

    user_id = uuid.UUID(user_info.id)
    email = user_info.email or ""
    metadata = user_info.user_metadata or {}
    name = metadata.get("full_name", email.split("@")[0] if "@" in email else "Usuário")
    avatar_url = metadata.get("avatar_url") or metadata.get("picture")

    local_user = db.get(User, user_id)

    if not local_user:
        local_user = User(
            id=user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            password_hash=None,
            plan_tier="free",
            preferences=UserPreferences().model_dump(),
        )
        db.add(local_user)
        db.flush()

        create_user_onboarding(db, local_user)
        db.commit()

    refresh_param = (
        f"&refresh_token={session.refresh_token}" if session.refresh_token else ""
    )

    redirect_url = f"{settings.FRONTEND_URL}/auth/success#access_token={session.access_token}{refresh_param}&provider={provider}&next={next}"

    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/2fa/setup")
def setup_2fa(current_user: User = Depends(get_current_user)):
    """
    Generates the secret and URL for the Frontend to mount the QR Code.
    """
    if current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA já está ativado.")

    secret = pyotp.random_base32()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email, issuer_name="FlowSpace"
    )

    return {"secret": secret, "uri": uri}


@router.post("/2fa/enable")
def enable_2fa(
    payload: Enable2FAIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enables 2FA for the current user.
    """
    totp = pyotp.TOTP(payload.secret)

    if not totp.verify(payload.code):
        raise HTTPException(status_code=400, detail="Código inválido. Tente novamente.")

    current_user.totp_secret = payload.secret
    db.commit()

    return {"message": "2FA ativado com sucesso!"}


@router.post("/2fa/disable")
def disable_2fa(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Disables 2FA for the current user.
    """
    current_user.totp_secret = None
    db.commit()
    return {"message": "2FA desativado com sucesso."}
