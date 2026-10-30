"""Add refresh sessions and account token versions.

Revision ID: 0002_refresh_sessions
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_refresh_sessions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "token_version" not in user_columns:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("refresh_sessions"):
        op.create_table(
            "refresh_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("refresh_sessions")}
    if "ix_refresh_sessions_user_id" not in indexes:
        op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    if "ix_refresh_sessions_user_active" not in indexes:
        op.create_index("ix_refresh_sessions_user_active", "refresh_sessions", ["user_id", "revoked_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("refresh_sessions"):
        indexes = {index["name"] for index in inspector.get_indexes("refresh_sessions")}
        if "ix_refresh_sessions_user_active" in indexes:
            op.drop_index("ix_refresh_sessions_user_active", table_name="refresh_sessions")
        if "ix_refresh_sessions_user_id" in indexes:
            op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
        op.drop_table("refresh_sessions")
    user_columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "token_version" in user_columns:
        op.drop_column("users", "token_version")
