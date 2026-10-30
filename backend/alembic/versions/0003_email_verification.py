"""Add email verification state and one-time tokens.

Revision ID: 0003_email_verification
Revises: 0002_refresh_sessions
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_email_verification"
down_revision = "0002_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "email_verified" not in user_columns:
        op.add_column(
            "users",
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("email_verification_tokens"):
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("email_verification_tokens")}
    if "ix_email_verification_tokens_user_id" not in indexes:
        op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    if "ix_email_verification_user_expiry" not in indexes:
        op.create_index("ix_email_verification_user_expiry", "email_verification_tokens", ["user_id", "expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("email_verification_tokens"):
        indexes = {index["name"] for index in inspector.get_indexes("email_verification_tokens")}
        for name in ("ix_email_verification_user_expiry", "ix_email_verification_tokens_user_id"):
            if name in indexes:
                op.drop_index(name, table_name="email_verification_tokens")
        op.drop_table("email_verification_tokens")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "email_verified" in columns:
        op.drop_column("users", "email_verified")
