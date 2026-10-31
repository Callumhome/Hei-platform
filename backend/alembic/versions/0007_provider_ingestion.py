"""Add provider sync jobs and richer reading provenance.

Revision ID: 0007_provider_ingestion
Revises: 0006_property_consent
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_provider_ingestion"
down_revision = "0006_property_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("electricity_readings"):
        columns = {column["name"] for column in sa.inspect(bind).get_columns("electricity_readings")}
        if "export_kwh" not in columns:
            op.add_column("electricity_readings", sa.Column("export_kwh", sa.Numeric(14, 6), nullable=True))
        if "source_provider" not in columns:
            op.add_column("electricity_readings", sa.Column("source_provider", sa.String(60), nullable=True))
        if "quality" not in columns:
            op.add_column("electricity_readings", sa.Column("quality", sa.String(24), nullable=False, server_default="unknown"))
    if not inspector.has_table("sync_jobs"):
        op.create_table(
            "sync_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(60), nullable=False),
            sa.Column("job_type", sa.String(40), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
            sa.Column("cursor", sa.String(500), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(80), nullable=True),
            sa.Column("error_message", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("sync_jobs")}
    for name, columns in (
        ("ix_sync_jobs_household_id", ["household_id"]),
        ("ix_sync_jobs_household_created", ["household_id", "created_at"]),
        ("ix_sync_jobs_status_next", ["status", "next_attempt_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "sync_jobs", columns)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("sync_jobs"):
        for item in sa.inspect(bind).get_indexes("sync_jobs"):
            op.drop_index(item["name"], table_name="sync_jobs")
        op.drop_table("sync_jobs")
    if sa.inspect(bind).has_table("electricity_readings"):
        columns = {column["name"] for column in sa.inspect(bind).get_columns("electricity_readings")}
        for name in ("quality", "source_provider", "export_kwh"):
            if name in columns:
                op.drop_column("electricity_readings", name)
