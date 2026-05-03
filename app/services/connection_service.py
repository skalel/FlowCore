from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain.policies.permissions import can_share_card
from app.infra.db.orm_models import Card, CardHolder, SharedCard, User, UserConnection


class ConnectionService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_connections(self, user_id: UUID, status: str | None = None):
        """Lista as conexões enriquecidas com os dados do 'amigo'."""
        query = select(UserConnection).where(
            or_(
                UserConnection.requester_id == user_id,
                UserConnection.addressee_id == user_id,
            )
        )
        if status:
            query = query.where(UserConnection.status == status)

        connections = self.db.execute(query).scalars().all()

        result = []
        for conn in connections:
            is_requester = conn.requester_id == user_id
            friend_id = conn.addressee_id if is_requester else conn.requester_id

            friend = self.db.execute(
                select(User).where(User.id == friend_id)
            ).scalar_one_or_none()

            if friend:
                result.append(
                    {
                        "id": conn.id,
                        "status": conn.status,
                        "is_requester": is_requester,
                        "friend": {
                            "id": friend.id,
                            "name": friend.name,
                            "email": friend.email,
                            "avatar_url": friend.avatar_url,
                        },
                    }
                )

        return result

    def request_connection(
        self, requester_id: UUID, addressee_email: str
    ) -> UserConnection:
        addressee = self.db.execute(
            select(User).where(User.email == addressee_email)
        ).scalar_one_or_none()

        if not addressee:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        if requester_id == addressee.id:
            raise HTTPException(
                status_code=400, detail="Não é possível adicionar a si mesmo."
            )

        existing = self.db.execute(
            select(UserConnection).where(
                or_(
                    and_(
                        UserConnection.requester_id == requester_id,
                        UserConnection.addressee_id == addressee.id,
                    ),
                    and_(
                        UserConnection.requester_id == addressee.id,
                        UserConnection.addressee_id == requester_id,
                    ),
                )
            )
        ).scalar_one_or_none()

        if existing:
            return existing

        new_connection = UserConnection(
            requester_id=requester_id, addressee_id=addressee.id, status="PENDING"
        )
        self.db.add(new_connection)
        self.db.commit()
        self.db.refresh(new_connection)

        # TODO: Chamar app.domain.services.email_service para disparar notificação

        return new_connection

    def share_card(self, owner_id: UUID, card_id: UUID, target_email: str):
        card = self.db.execute(
            select(Card).where(Card.id == card_id)
        ).scalar_one_or_none()
        if not card:
            raise HTTPException(status_code=404, detail="Cartão não encontrado.")

        holder = self.db.execute(
            select(CardHolder).where(CardHolder.id == card.holder_id)
        ).scalar_one_or_none()

        if not can_share_card(user_id=owner_id, card=card, holder=holder):
            raise HTTPException(
                status_code=403, detail="Apenas o titular pode emprestar este cartão."
            )

        target_user = self.db.execute(
            select(User).where(User.email == target_email)
        ).scalar_one_or_none()
        if not target_user:
            raise HTTPException(
                status_code=404, detail="Usuário alvo não encontrado na plataforma."
            )

        connection = self.db.execute(
            select(UserConnection).where(
                and_(
                    or_(
                        and_(
                            UserConnection.requester_id == owner_id,
                            UserConnection.addressee_id == target_user.id,
                        ),
                        and_(
                            UserConnection.requester_id == target_user.id,
                            UserConnection.addressee_id == owner_id,
                        ),
                    ),
                    UserConnection.status == "ACCEPTED",
                )
            )
        ).scalar_one_or_none()

        if not connection:
            self.request_connection(requester_id=owner_id, addressee_email=target_email)
            return {
                "message": "Solicitação de amizade enviada. O cartão será compartilhado assim que o convite for aceito.",
                "status": "CONNECTION_PENDING",
            }

        existing_share = self.db.execute(
            select(SharedCard).where(
                and_(
                    SharedCard.card_id == card_id, SharedCard.user_id == target_user.id
                )
            )
        ).scalar_one_or_none()

        if existing_share:
            raise HTTPException(
                status_code=400, detail="Cartão já compartilhado com este usuário."
            )

        new_share = SharedCard(card_id=card_id, user_id=target_user.id)
        self.db.add(new_share)
        self.db.commit()
        self.db.refresh(new_share)

        return {
            "message": "Cartão compartilhado com sucesso.",
            "status": "SHARED",
            "shared_card_id": new_share.id,
        }

    def accept_connection(self, user_id: UUID, connection_id: UUID):
        """Aceita um pedido de amizade."""
        connection = self.db.execute(
            select(UserConnection).where(UserConnection.id == connection_id)
        ).scalar_one_or_none()

        if not connection:
            raise HTTPException(status_code=404, detail="Conexão não encontrada.")

        if connection.addressee_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para aceitar este convite.",
            )

        if connection.status == "ACCEPTED":
            raise HTTPException(status_code=400, detail="Esta conexão já foi aceita.")

        connection.status = "ACCEPTED"
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def remove_connection(self, user_id: UUID, connection_id: UUID):
        """Remove uma conexão (cancela pendente, recusa recebido ou desfaz amizade)."""
        connection = self.db.execute(
            select(UserConnection).where(UserConnection.id == connection_id)
        ).scalar_one_or_none()

        if not connection:
            raise HTTPException(status_code=404, detail="Conexão não encontrada.")

        if user_id not in (connection.requester_id, connection.addressee_id):
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para alterar esta conexão.",
            )

        if connection.status == "ACCEPTED":
            has_shared_cards = self.db.execute(
                select(SharedCard.id)
                .join(Card, SharedCard.card_id == Card.id)
                .join(CardHolder, Card.holder_id == CardHolder.id)
                .where(
                    or_(
                        and_(
                            SharedCard.user_id == connection.addressee_id,
                            CardHolder.created_by_user_id == connection.requester_id,
                        ),
                        and_(
                            SharedCard.user_id == connection.requester_id,
                            CardHolder.created_by_user_id == connection.addressee_id,
                        ),
                    )
                )
            ).first()

            if has_shared_cards:
                raise HTTPException(
                    status_code=400,
                    detail="Não é possível desfazer a amizade. Existem cartões emprestados ativos entre vocês.",
                )

        self.db.delete(connection)
        self.db.commit()

        return {"message": "Conexão removida com sucesso."}
