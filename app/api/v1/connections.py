from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.deps import get_db
from app.api.v1.schemas_connections import (
    ConnectionActionResponse,
    ConnectionListResponse,
    ConnectionRequestCreate,
)
from app.infra.db.orm_models import User
from app.services.connection_service import ConnectionService

router = APIRouter(prefix="/connections", tags=["Connections"])


@router.get("", response_model=List[ConnectionListResponse])
def list_connections(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ConnectionService(db)
    return service.get_user_connections(user_id=current_user.id, status=status)


@router.post("/request", response_model=ConnectionActionResponse)
def send_connection_request(
    payload: ConnectionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ConnectionService(db)
    return service.request_connection(
        requester_id=current_user.id, addressee_email=payload.email
    )


@router.patch("/{connection_id}/accept", response_model=ConnectionActionResponse)
def accept_connection_request(
    connection_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ConnectionService(db)
    return service.accept_connection(
        user_id=current_user.id, connection_id=connection_id
    )


@router.delete("/{connection_id}")
def remove_connection(
    connection_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui uma amizade ou recusa/cancela um convite."""
    service = ConnectionService(db)
    return service.remove_connection(
        user_id=current_user.id, connection_id=connection_id
    )
