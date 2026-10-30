"""Add encrypted Home Assistant household connections.

Revision ID: 0005_home_assistant
Revises: 0004_password_reset
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_home_assistant"
down_revision = "0004_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("home_assistant_connections"):
        op.create_table(
            "home_assistant_connections",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("household_id", sa.String(length=36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("base_url", sa.String(length=300), nullable=False),
            sa.Column("token_encrypted", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("home_assistant_connections")}
    if "ix_home_assistant_connections_household_id" not in indexes:
        op.create_index("ix_home_assistant_connections_household_id", "home_assistant_connections", ["household_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("home_assistant_connections"):
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("home_assistant_connections")}
        if "ix_home_assistant_connections_household_id" in indexes:
            op.drop_index("ix_home_assistant_connections_household_id", table_name="home_assistant_connections")
        op.drop_table("home_assistant_connections")
