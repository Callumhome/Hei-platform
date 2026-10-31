"""Store verified Octopus credentials encrypted per household.

Revision ID: 0008_octopus_credentials
Revises: 0007_provider_ingestion
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_octopus_credentials"
down_revision = "0007_provider_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "octopus_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_number_encrypted", sa.String(2048), nullable=False),
        sa.Column("account_number_last4", sa.String(4), nullable=False),
        sa.Column("account_number_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("api_key_encrypted", sa.String(2048), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("household_id", name="uq_octopus_connection_household"),
    )
    op.create_index("ix_octopus_connections_household_id", "octopus_connections", ["household_id"])


def downgrade() -> None:
    op.drop_index("ix_octopus_connections_household_id", table_name="octopus_connections")
    op.drop_table("octopus_connections")
