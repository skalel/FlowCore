import io
import uuid

import sqlalchemy as sa
import uuid6
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.env_deps import get_environment_id_from_header
from app.api.perm_deps import require_permission
from app.infra.db.orm_models import ImportTask, User
from app.services.import_service import process_import_in_background

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "",
    dependencies=[
        Depends(require_permission("imports:ofx", get_environment_id_from_header))
    ],
)
async def upload_spreadsheet_for_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    filename = file.filename or ""
    if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
        raise HTTPException(
            status_code=400, detail="Apenas arquivos .csv ou .xlsx são permitidos."
        )

    file_contents = await file.read()
    task_id = uuid6.uuid7()

    new_task = ImportTask(
        id=task_id,
        environment_id=env_id,
        created_by_user_id=current_user.id,
        filename=filename,
        status="PROCESSING",
    )
    db.add(new_task)
    db.commit()

    background_tasks.add_task(
        process_import_in_background,
        task_id=str(task_id),
        file_contents=file_contents,
        filename=filename,
        env_id=env_id,
        user_id=current_user.id,
    )

    return {"message": "Importação iniciada", "task_id": str(task_id)}


@router.get(
    "/{task_id}/status",
    dependencies=[
        Depends(require_permission("imports:ofx", get_environment_id_from_header))
    ],
)
def get_import_status(
    task_id: str,
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    """
    Rota de Polling: O frontend bate aqui a cada 3 segundos.
    """
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="ID de tarefa inválido.")

    task = db.get(ImportTask, tid)
    if not task or task.environment_id != env_id:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    return {
        "task_id": str(task.id),
        "status": task.status,
        "error_message": task.error_message,
    }


@router.get("/template")
def download_import_template():
    """
    Devolve um arquivo CSV padrão para o usuário preencher.
    """
    csv_content = (
        "data,descricao,valor,tipo,metodo_pagamento,final_cartao,categoria\n"
        "10/04/2026,Geladeira Nova (2/10),400.00,EXPENSE,CREDIT,1234,Moradia\n"
        "12/04/2026,Salário Mensal,5000.00,INCOME,PIX,,Salário\n"
    )

    stream = io.StringIO(csv_content)

    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=flowspace_template_importacao.csv"
        },
    )


@router.get(
    "/history",
    dependencies=[
        Depends(require_permission("imports:ofx", get_environment_id_from_header))
    ],
)
def list_import_history(
    db: Session = Depends(get_db),
    env_id: uuid.UUID = Depends(get_environment_id_from_header),
):
    """Retorna as últimas 20 importações do ambiente."""
    tasks = (
        db.execute(
            sa.select(ImportTask)
            .where(ImportTask.environment_id == env_id)
            .order_by(ImportTask.created_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(task.id),
            "filename": task.filename,
            "status": task.status,
            "error_message": task.error_message,
            "created_at": task.created_at,
        }
        for task in tasks
    ]
