import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.domain.policies.permissions import has_permission
from app.infra.db.orm_models import User


def require_permission(permission_code: str, env_id_dep):
    def _dep(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        env_id: uuid.UUID = Depends(env_id_dep),
    ):
        if not env_id:
            raise HTTPException(status_code=400, detail="Ambiente não selecionado.")

        if not has_permission(
            db,
            environment_id=env_id,
            user_id=current_user.id,
            permission_code=permission_code,
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

        return True

    return _dep


def get_current_superadmin(current_user=Depends(get_current_user)):
    """Garante que a rota só seja acessada pelo Master do Sistema."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado. Esta área é restrita a administradores do sistema.",
        )
    return current_user
