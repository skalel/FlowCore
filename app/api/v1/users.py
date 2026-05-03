from datetime import datetime, timezone

import sqlalchemy as sa
import uuid6
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.config.settings import settings
from app.infra.db.orm_models import CardHolder, Environment, User
from app.infra.integrations.supabase import supabase_admin
from app.shared.security import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


class UserPreferences(BaseModel):
    hide_values_by_default: bool = True
    has_2fa_enabled: bool = False
    default_dashboard_view: str = "charts"


class MeOut(BaseModel):
    id: str
    email: str
    name: str
    cpf: str | None = None
    avatar_url: str | None = None
    is_superadmin: bool = False
    plan_tier: str
    preferences: UserPreferences


class UpdateProfileIn(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    current_password: str | None = None
    new_password: str | None = None
    preferences: UserPreferences | None = None


class OnboardingRequest(BaseModel):
    cpf: str = Field(min_length=11, max_length=11)


@router.get("/me", response_model=MeOut)
def me(current_user: User = Depends(get_current_user)):
    """Get the current user's profile."""
    prefs = current_user.preferences or {}

    prefs["has_2fa_enabled"] = bool(getattr(current_user, "totp_secret", False))

    return MeOut(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        cpf=current_user.cpf,
        avatar_url=current_user.avatar_url,
        is_superadmin=current_user.is_superadmin,
        plan_tier=current_user.plan_tier,
        preferences=UserPreferences(**prefs),
    )


@router.patch("/me", response_model=MeOut)
def update_my_profile(
    payload: UpdateProfileIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the current user's profile."""
    if payload.name:
        if len(payload.name.strip()) < 2:
            raise HTTPException(
                status_code=422, detail="O nome deve ter pelo menos 2 caracteres."
            )
        current_user.name = payload.name.strip()

    if payload.email and payload.email.lower() != current_user.email:
        existing = db.execute(
            sa.select(User).where(User.email == payload.email.lower())
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409, detail="Este e-mail já está em uso por outra conta."
            )
        current_user.email = payload.email.lower()

    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(
                status_code=400,
                detail="A senha atual é obrigatória para definir uma nova senha.",
            )
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="A senha atual está incorreta.")
        if len(payload.new_password) < 8:
            raise HTTPException(
                status_code=422, detail="A nova senha deve ter pelo menos 8 caracteres."
            )

        current_user.password_hash = hash_password(payload.new_password)

    if payload.preferences is not None:
        current_prefs = current_user.preferences or {}
        new_prefs = payload.preferences.model_dump(exclude_unset=True)

        if "has_2fa_enabled" in new_prefs:
            del new_prefs["has_2fa_enabled"]

        current_user.preferences = {**current_prefs, **new_prefs}

        flag_modified(current_user, "preferences")

    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()

    final_prefs = current_user.preferences or {}
    final_prefs["has_2fa_enabled"] = bool(getattr(current_user, "totp_secret", False))

    return MeOut(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        plan_tier=current_user.plan_tier,
        preferences=UserPreferences(**final_prefs),
    )


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a new avatar for the current user."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="O arquivo deve ser uma imagem.")

    try:
        old_avatar = current_user.avatar_url
        if old_avatar and settings.SUPABASE_URL in old_avatar:
            try:
                prefix = f"{settings.SUPABASE_URL}/storage/v1/object/public/avatars/"
                if old_avatar.startswith(prefix):
                    old_path = old_avatar.replace(prefix, "")
                    supabase_admin.storage.from_("avatars").remove([old_path])
            except Exception as e:
                print(f"Aviso: Não foi possível deletar o avatar antigo: {e}")

        file_extension = file.filename.split(".")[-1] if "." in file.filename else "png"
        file_name = f"{current_user.id}_{uuid6.uuid7()}.{file_extension}"
        storage_path = f"profiles/{file_name}"

        file_bytes = await file.read()

        supabase_admin.storage.from_("avatars").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type},
        )

        image_public_url = supabase_admin.storage.from_("avatars").get_public_url(
            storage_path
        )

        current_user.avatar_url = image_public_url
        db.commit()

        return {
            "message": "Avatar atualizado com sucesso",
            "avatar_url": image_public_url,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao processar imagem: {str(e)}"
        )


@router.post("/onboarding")
def complete_onboarding(
    payload: OnboardingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.cpf = payload.cpf

    environments = (
        db.execute(
            select(Environment).where(Environment.owner_user_id == current_user.id)
        )
        .scalars()
        .all()
    )

    for env in environments:
        existing_holder = db.execute(
            select(CardHolder).where(
                and_(CardHolder.environment_id == env.id, CardHolder.cpf == payload.cpf)
            )
        ).scalar_one_or_none()

        if not existing_holder:
            new_holder = CardHolder(
                environment_id=env.id,
                created_by_user_id=current_user.id,
                cpf=payload.cpf,
                name=current_user.name,
            )
            db.add(new_holder)

    db.commit()
    return {"message": "Onboarding concluído e Titulares gerados."}
