import uuid
from datetime import date, datetime, timezone
from typing import Optional

import sqlalchemy as sa
import uuid6
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ENVIRONMENT_TYPE = postgresql.ENUM(
    "SOLO", "FAMILY", "FRIENDS", "BUSINESS", name="environment_type", create_type=False
)
TRANSACTION_KIND = postgresql.ENUM(
    "INCOME", "EXPENSE", name="transaction_kind", create_type=False
)
TRANSACTION_STATUS = postgresql.ENUM(
    "POSTED", "VOID", name="transaction_status", create_type=False
)
PAYMENT_METHOD = postgresql.ENUM(
    "CASH",
    "PIX",
    "DEBIT",
    "CREDIT",
    "TRANSFER",
    "OTHER",
    name="payment_method",
    create_type=False,
)
CATEGORY_KIND = postgresql.ENUM(
    "INCOME", "EXPENSE", name="category_kind", create_type=False
)
FISCAL_STATUS = postgresql.ENUM(
    "OPEN", "CLOSED", name="fiscal_status", create_type=False
)
INSTALLMENT_KIND = postgresql.ENUM(
    "LOAN", "PURCHASE", "OTHER", name="installment_kind", create_type=False
)
RULE_KIND = postgresql.ENUM("INCOME", "EXPENSE", name="rule_kind", create_type=False)
SCHEDULE_TYPE = postgresql.ENUM("MONTHLY", name="schedule_type", create_type=False)
MEMBER_STATUS = postgresql.ENUM(
    "ACTIVE", "INACTIVE", "BANNED", name="member_status", create_type=False
)
CONNECTION_STATUS = postgresql.ENUM(
    "PENDING", "ACCEPTED", "BLOCKED", name="connection_status", create_type=False
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cpf: Mapped[str | None] = mapped_column(sa.String(11), unique=True, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_tier: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    totp_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferences: Mapped[dict] = mapped_column(
        JSONB, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    is_superadmin: Mapped[bool] = mapped_column(default=False)


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    type: Mapped[str] = mapped_column(ENVIRONMENT_TYPE, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment_type: Mapped[str | None] = mapped_column(
        ENVIRONMENT_TYPE, nullable=True
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class EnvironmentMember(Base):
    __tablename__ = "environment_members"

    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    status: Mapped[str] = mapped_column(
        MEMBER_STATUS, nullable=False, server_default="ACTIVE"
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(sa.Text, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(TRANSACTION_KIND, nullable=False)
    status: Mapped[str] = mapped_column(
        TRANSACTION_STATUS, nullable=False, server_default="POSTED"
    )
    occurred_on: Mapped[date] = mapped_column(sa.Date(), nullable=False)
    due_on: Mapped[date | None] = mapped_column(sa.Date(), nullable=True)
    paid_on: Mapped[date | None] = mapped_column(sa.Date(), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    amount: Mapped[float] = mapped_column(sa.Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        sa.String(3), nullable=False, server_default="BRL"
    )
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(
        PAYMENT_METHOD, nullable=False, server_default="OTHER"
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cards.id"), nullable=True
    )
    installment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("installments.id"), nullable=True
    )
    meta: Mapped[dict | None] = mapped_column(postgresql.JSONB(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(CATEGORY_KIND, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class CategoryChange(Base):
    __tablename__ = "category_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    old_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    new_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    old_kind: Mapped[str] = mapped_column(CATEGORY_KIND, nullable=False)
    new_kind: Mapped[str] = mapped_column(CATEGORY_KIND, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class CardHolder(Base):
    __tablename__ = "card_holders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    cpf: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    last4: Mapped[str] = mapped_column(sa.String(4), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    due_day: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    pay_day: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    holder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("card_holders.id"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class FiscalClosure(Base):
    __tablename__ = "fiscal_closures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    month: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(FISCAL_STATUS, nullable=False)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class Installment(Base):
    __tablename__ = "installments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(INSTALLMENT_KIND, nullable=False)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    principal_amount: Mapped[float | None] = mapped_column(
        sa.Numeric(14, 2), nullable=True
    )
    total_installments: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    installment_amount: Mapped[float] = mapped_column(sa.Numeric(14, 2), nullable=False)
    interest_rate: Mapped[float | None] = mapped_column(
        sa.Numeric(10, 6), nullable=True
    )
    first_due_on: Mapped[date] = mapped_column(sa.Date(), nullable=False)
    current_installment: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="1"
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cards.id"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class InstallmentOccurrence(Base):
    __tablename__ = "installment_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    installment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("installments.id", ondelete="CASCADE"),
        nullable=False,
    )
    installment_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    due_on: Mapped[date] = mapped_column(sa.Date(), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(RULE_KIND, nullable=False)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    amount: Mapped[float] = mapped_column(sa.Numeric(14, 2), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=False
    )
    schedule_type: Mapped[str] = mapped_column(
        SCHEDULE_TYPE, nullable=False, server_default="MONTHLY"
    )
    day_of_month: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    start_on: Mapped[date] = mapped_column(sa.Date(), nullable=False)
    end_on: Mapped[date | None] = mapped_column(sa.Date(), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class ImportTask(Base):
    __tablename__ = "import_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="PROCESSING", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


class SystemFeedback(Base):
    __tablename__ = "system_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    feedback_type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserConnection(Base):
    __tablename__ = "user_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    addressee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        CONNECTION_STATUS, nullable=False, server_default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.UniqueConstraint("requester_id", "addressee_id", name="uq_user_connection"),
    )


class SharedCard(Base):
    __tablename__ = "shared_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (sa.UniqueConstraint("card_id", "user_id", name="uq_shared_card"),)
