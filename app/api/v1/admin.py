import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.perm_deps import get_current_superadmin
from app.infra.db.orm_models import Environment, SystemFeedback, User


class FeedbackCreate(BaseModel):
    feedback_type: str
    message: str


router = APIRouter(
    prefix="/admin",
    tags=["superadmin"],
    dependencies=[Depends(get_current_superadmin)],
    include_in_schema=False,
)


@router.get("/stats")
def get_system_stats(db: Session = Depends(get_db)):
    """Retorna os indicadores globais de saúde do SaaS."""
    total_users = db.query(sa.func.count(User.id)).scalar()
    total_envs = db.query(sa.func.count(Environment.id)).scalar()

    total_imports = 0

    pending_feedbacks = (
        db.query(sa.func.count(SystemFeedback.id))
        .filter(SystemFeedback.status == "PENDING")
        .scalar()
    )

    return {
        "users": total_users,
        "environments": total_envs,
        "imports": total_imports,
        "pending_feedbacks": pending_feedbacks,
    }


@router.get("/feedbacks")
def list_feedbacks(db: Session = Depends(get_db)):
    """Lista os feedbacks para o Superadmin ler."""
    feedbacks = (
        db.execute(
            sa.text("""
            SELECT f.id, f.feedback_type, f.message, f.status, f.created_at, u.name as user_name, u.email as user_email
            FROM system_feedbacks f
            JOIN users u ON f.user_id = u.id
            ORDER BY f.created_at DESC
        """)
        )
        .mappings()
        .all()
    )

    return [dict(f) for f in feedbacks]
