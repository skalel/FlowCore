"""create initial schema

Revision ID: 4b9b9509abbe
Revises:
Create Date: 2026-04-08 13:58:06.973245

"""

from typing import Sequence, Union

import sqlalchemy as sa
import uuid6
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4b9b9509abbe"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    env_type = postgresql.ENUM(
        "SOLO",
        "FAMILY",
        "FRIENDS",
        "BUSINESS",
        name="environment_type",
        create_type=False,
    )
    member_status = postgresql.ENUM(
        "ACTIVE", "INVITED", "REMOVED", name="member_status", create_type=False
    )
    perm_effect = postgresql.ENUM(
        "ALLOW", "DENY", name="permission_effect", create_type=False
    )
    txn_kind = postgresql.ENUM(
        "INCOME", "EXPENSE", name="transaction_kind", create_type=False
    )
    txn_status = postgresql.ENUM(
        "POSTED", "VOID", name="transaction_status", create_type=False
    )
    pay_method = postgresql.ENUM(
        "CASH",
        "PIX",
        "DEBIT",
        "CREDIT",
        "TRANSFER",
        "OTHER",
        name="payment_method",
        create_type=False,
    )
    category_kind = postgresql.ENUM(
        "INCOME", "EXPENSE", name="category_kind", create_type=False
    )
    rule_kind = postgresql.ENUM(
        "INCOME", "EXPENSE", name="recurring_kind", create_type=False
    )
    schedule_type = postgresql.ENUM("MONTHLY", name="schedule_type", create_type=False)
    installment_kind = postgresql.ENUM(
        "EXPENSE",
        "PURCHASE",
        "LOAN",
        "OTHER",
        name="installment_kind",
        create_type=False,
    )
    fiscal_status = postgresql.ENUM(
        "OPEN", "PENDING_APPROVAL", "CLOSED", name="fiscal_status", create_type=False
    )

    for e in [
        env_type,
        member_status,
        perm_effect,
        txn_kind,
        txn_status,
        pay_method,
        category_kind,
        rule_kind,
        schedule_type,
        installment_kind,
        fiscal_status,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("plan_tier", sa.Text(), nullable=False, server_default="free"),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "environments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", env_type, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_environments_owner_user_id", "environments", ["owner_user_id"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("environment_type", env_type, nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_roles_envtype_name", "roles", ["environment_type", "name"], unique=False
    )

    op.create_table(
        "permissions",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_code",
            sa.Text(),
            sa.ForeignKey("permissions.code", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "environment_members",
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", member_status, nullable=False, server_default="ACTIVE"),
    )
    op.create_index(
        "ix_env_members_env_user", "environment_members", ["environment_id", "user_id"]
    )

    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_invites_environment_id", "invites", ["environment_id"])
    op.create_index("ix_invites_email", "invites", ["email"])

    op.create_table(
        "member_permission_overrides",
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_code",
            sa.Text(),
            sa.ForeignKey("permissions.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("effect", perm_effect, nullable=False),
    )

    op.create_table(
        "card_holders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("cpf", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last4", sa.String(length=4), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("pay_day", sa.Integer(), nullable=False),
        sa.Column(
            "holder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("card_holders.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cards_environment_id", "cards", ["environment_id"])
    op.create_index("ix_cards_holder_id", "cards", ["holder_id"])
    op.create_index(
        "ux_cards_env_holder_last4",
        "cards",
        ["environment_id", "holder_id", "last4"],
        unique=True,
    )

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", category_kind, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_categories_env_kind", "categories", ["environment_id", "kind"])
    op.create_index("ix_categories_owner_user_id", "categories", ["owner_user_id"])

    op.create_table(
        "category_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("old_name", sa.Text(), nullable=False),
        sa.Column("new_name", sa.Text(), nullable=False),
        sa.Column("old_kind", category_kind, nullable=False),
        sa.Column("new_kind", category_kind, nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_category_changes_cat", "category_changes", ["category_id"])

    op.create_table(
        "installments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", installment_kind, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("principal_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_installments", sa.Integer(), nullable=False),
        sa.Column("installment_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("interest_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("first_due_on", sa.Date(), nullable=False),
        sa.Column(
            "current_installment", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cards.id"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_installments_environment_id", "installments", ["environment_id"]
    )
    op.create_index("ix_installments_card_id", "installments", ["card_id"])

    op.create_table(
        "installment_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "installment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("installments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "installment_id",
            "installment_number",
            name="uq_installment_occurrence_number",
        ),
    )
    op.create_index(
        "ix_installment_occurrences_installment_id",
        "installment_occurrences",
        ["installment_id"],
    )

    op.create_table(
        "recurring_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", rule_kind, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id"),
            nullable=False,
        ),
        sa.Column(
            "schedule_type", schedule_type, nullable=False, server_default="MONTHLY"
        ),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("end_on", sa.Date(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_recurring_rules_environment_id", "recurring_rules", ["environment_id"]
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("kind", txn_kind, nullable=False),
        sa.Column("status", txn_status, nullable=False, server_default="POSTED"),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "currency", sa.String(length=3), nullable=False, server_default="BRL"
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id"),
            nullable=False,
        ),
        sa.Column("payment_method", pay_method, nullable=False, server_default="OTHER"),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cards.id"),
            nullable=True,
        ),
        sa.Column(
            "installment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("installments.id"),
            nullable=True,
        ),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_transactions_env_occurred",
        "transactions",
        ["environment_id", "occurred_on"],
    )
    op.create_index(
        "ix_transactions_env_kind_occurred",
        "transactions",
        ["environment_id", "kind", "occurred_on"],
    )
    op.create_index("ix_transactions_card_id", "transactions", ["card_id"])
    op.create_index(
        "ix_transactions_installment_id", "transactions", ["installment_id"]
    )
    op.create_index(
        "ix_transactions_env_due_on", "transactions", ["environment_id", "due_on"]
    )

    op.create_foreign_key(
        "fk_installment_occurrences_transaction_id",
        "installment_occurrences",
        "transactions",
        ["transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "fiscal_closures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", fiscal_status, nullable=False),
        sa.Column(
            "closed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ux_fiscal_closures_env_ym",
        "fiscal_closures",
        ["environment_id", "year", "month"],
        unique=True,
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_log_environment_id", "audit_log", ["environment_id"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])

    conn = op.get_bind()

    permissions = [
        ("env:read", "Read environments"),
        ("env:manage", "Manage environments"),
        ("members:invite", "Invite members"),
        ("members:manage", "Manage members"),
        ("ledger:read", "Read transactions"),
        ("ledger:create", "Create transactions"),
        ("ledger:update", "Update transactions"),
        ("ledger:delete_soft", "Soft delete transactions"),
        ("ledger:delete_hard", "Hard delete within 24h"),
        ("categories:read", "Read categories"),
        ("categories:manage_own", "Manage own categories"),
        ("cards:read", "Read cards"),
        ("cards:manage", "Manage cards"),
        ("recurring:manage", "Manage recurring rules/installments"),
        ("fiscal:read", "Read fiscal summaries"),
        ("fiscal:close", "Close month"),
        ("fiscal:reopen", "Reopen month"),
        ("imports:ofx", "Import OFX"),
        ("imports:csv", "Import CSV"),
        ("integrations:ai_run", "Run AI insights"),
        ("integrations:telegram_manage", "Manage telegram integration"),
        ("reports:read", "Read reports"),
    ]

    conn.execute(
        sa.text("""
        INSERT INTO permissions(code, description)
        VALUES (:code, :desc)
        ON CONFLICT (code) DO NOTHING
        """),
        [{"code": c, "desc": d} for c, d in permissions],
    )

    role_owner = uuid6.uuid7()
    role_admin = uuid6.uuid7()
    role_member = uuid6.uuid7()
    role_viewer = uuid6.uuid7()

    conn.execute(
        sa.text("""
        INSERT INTO roles(id, environment_type, name, is_system)
        VALUES
        (:owner_id, NULL, 'Owner', true),
        (:admin_id, NULL, 'Admin', true),
        (:member_id, NULL, 'Member', true),
        (:viewer_id, NULL, 'Viewer', true)
        ON CONFLICT DO NOTHING
        """),
        {
            "owner_id": str(role_owner),
            "admin_id": str(role_admin),
            "member_id": str(role_member),
            "viewer_id": str(role_viewer),
        },
    )

    all_perms = [p[0] for p in permissions]
    owner_perms = all_perms
    admin_perms = [p for p in all_perms if p not in ("ledger:delete_hard",)]
    member_perms = [
        "env:read",
        "members:invite",
        "ledger:read",
        "ledger:create",
        "ledger:update",
        "ledger:delete_soft",
        "categories:read",
        "categories:manage_own",
        "cards:read",
        "recurring:manage",
        "fiscal:read",
        "reports:read",
    ]
    viewer_perms = [
        "env:read",
        "ledger:read",
        "categories:read",
        "cards:read",
        "fiscal:read",
        "reports:read",
    ]

    def upsert_role_perms(role_id, perm_codes):
        conn.execute(
            sa.text("""
          INSERT INTO role_permissions(role_id, permission_code)
          VALUES (:rid, :p)
          ON CONFLICT DO NOTHING
          """),
            [{"rid": str(role_id), "p": p} for p in perm_codes],
        )

    upsert_role_perms(role_owner, owner_perms)
    upsert_role_perms(role_admin, admin_perms)
    upsert_role_perms(role_member, member_perms)
    upsert_role_perms(role_viewer, viewer_perms)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("audit_log")
    op.drop_table("fiscal_closures")
    op.drop_constraint(
        "fk_installment_occurrences_transaction_id",
        "installment_occurrences",
        type_="foreignkey",
    )
    op.drop_table("transactions")
    op.drop_table("recurring_rules")
    op.drop_table("installment_occurrences")
    op.drop_table("installments")
    op.drop_table("category_changes")
    op.drop_table("categories")
    op.drop_table("cards")
    op.drop_table("card_holders")
    op.drop_table("member_permission_overrides")
    op.drop_table("invites")
    op.drop_table("environment_members")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("environments")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in [
        "fiscal_status",
        "installment_kind",
        "schedule_type",
        "recurring_kind",
        "category_kind",
        "payment_method",
        "transaction_status",
        "transaction_kind",
        "permission_effect",
        "member_status",
        "environment_type",
    ]:
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
