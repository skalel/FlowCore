import math
from datetime import datetime, timezone

import uuid6
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.infra.db.orm_models import SystemFeedback, User
from app.infra.integrations.supabase import supabase_admin

router = APIRouter(prefix="/feedbacks", tags=["feedbacks"])


class StatusUpdate(BaseModel):
    status: str


@router.get("")
def get_all_feedbacks(
    status: str = Query("PENDING"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna feedbacks com paginação e filtros diretamente no banco de dados."""

    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    base_query = db.query(SystemFeedback, User).join(
        User, SystemFeedback.user_id == User.id
    )

    base_query = base_query.filter(SystemFeedback.status == status)

    if start_date:
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d")
            if status == "CLOSED":
                base_query = base_query.filter(SystemFeedback.closed_at >= dt_start)
            else:
                base_query = base_query.filter(SystemFeedback.created_at >= dt_start)
        except ValueError:
            pass

    if end_date:
        try:
            dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            if status == "CLOSED":
                base_query = base_query.filter(SystemFeedback.closed_at <= dt_end)
            else:
                base_query = base_query.filter(SystemFeedback.created_at <= dt_end)
        except ValueError:
            pass

    total_items = base_query.count()
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    offset = (page - 1) * limit

    order_column = (
        SystemFeedback.closed_at.desc()
        if status == "CLOSED"
        else SystemFeedback.created_at.desc()
    )

    results = base_query.order_by(order_column).offset(offset).limit(limit).all()

    feedbacks_response = []
    for feedback, user in results:
        feedbacks_response.append(
            {
                "id": str(feedback.id),
                "feedback_type": feedback.feedback_type,
                "message": feedback.message,
                "image_url": feedback.image_url,
                "status": feedback.status,
                "created_at": feedback.created_at,
                "user": {"name": user.name, "email": user.email},
            }
        )

    return {
        "data": feedbacks_response,
        "meta": {
            "total_items": total_items,
            "current_page": page,
            "total_pages": total_pages,
            "items_per_page": limit,
        },
    }


@router.post("")
async def submit_feedback(
    feedback_type: str = Form(...),
    message: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rota para qualquer usuário enviar elogios, bugs ou sugestões, com suporte a anexo de imagem."""

    image_public_url = None

    if file:
        safe_content_type = file.content_type or ""
        safe_filename = file.filename or "imagem.png"

        if not safe_content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail="Formato inválido. Envie apenas imagens (JPEG, PNG, etc).",
            )

        try:
            file_extension = (
                safe_filename.split(".")[-1] if "." in safe_filename else "png"
            )
            file_name = f"{uuid6.uuid7()}.{file_extension}"
            storage_path = f"{current_user.id}/{file_name}"

            file_bytes = await file.read()

            supabase_admin.storage.from_("feedbacks").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": safe_content_type},
            )

            image_public_url = supabase_admin.storage.from_("feedbacks").get_public_url(
                storage_path
            )

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Erro ao salvar a imagem no servidor: {str(e)}"
            )

    new_feedback = SystemFeedback(
        user_id=current_user.id,
        feedback_type=feedback_type,
        message=message,
        image_url=image_public_url,
    )

    db.add(new_feedback)
    db.commit()

    return {"message": "Feedback enviado com sucesso!"}


@router.patch("/{feedback_id}/status")
def update_feedback_status(
    feedback_id: str,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza o status de um feedback (Ex: PENDING para CLOSED). Apenas Superadmins."""

    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    feedback = db.query(SystemFeedback).filter(SystemFeedback.id == feedback_id).first()

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback não encontrado.")

    feedback.status = payload.status

    if payload.status == "CLOSED":
        feedback.closed_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Status atualizado com sucesso!"}
