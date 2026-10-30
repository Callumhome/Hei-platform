"""Add cloud-first property, meter, consent and energy ingestion models.

Revision ID: 0006_cloud_platform
Revises: 0005_home_assistant
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_cloud_platform"
down_revision = "0005_home_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("address_encrypted", sa.String(8192), nullable=False),
        sa.Column("postcode_fingerprint", sa.String(64), nullable=False),
        sa.Column("country_code", sa.String(2), server_default="GB", nullable=False),
        sa.Column("address_provider", sa.String(40), nullable=True),
        sa.Column("address_provider_ref", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_properties_household_id", "properties", ["household_id"])
    op.create_index("ix_properties_postcode_fingerprint", "properties", ["postcode_fingerprint"])

    op.create_table(
        "meter_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("property_id", sa.String(36), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fuel", sa.String(16), nullable=False),
        sa.Column("identifier_encrypted", sa.String(8192), nullable=False),
        sa.Column("identifier_fingerprint", sa.String(64), nullable=False),
        sa.Column("meter_serial_encrypted", sa.String(8192), nullable=True),
        sa.Column("is_smart_meter", sa.Boolean(), nullable=True),
        sa.Column("data_source", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("identifier_fingerprint", name="uq_meter_point_identifier_fingerprint"),
    )
    op.create_index("ix_meter_points_property_id", "meter_points", ["property_id"])
    op.create_index("ix_meter_points_property_fuel", "meter_points", ["property_id", "fuel"])

    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(60), nullable=False),
        sa.Column("external_account_ref", sa.String(200), nullable=True),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("credential_encrypted", sa.String(16384), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("household_id", "provider_id", "external_account_ref", name="uq_household_provider_external_account"),
    )
    op.create_index("ix_provider_connections_household_id", "provider_connections", ["household_id"])
    op.create_index("ix_provider_connections_household_status", "provider_connections", ["household_id", "status"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("provider_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("scopes", sa.String(1000), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consent_records_connection_id", "consent_records", ["connection_id"])
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])
    op.create_index("ix_consent_records_connection_created", "consent_records", ["connection_id", "recorded_at"])

    op.create_table(
        "energy_data_readings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meter_point_id", sa.String(36), sa.ForeignKey("meter_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement", sa.String(40), nullable=False),
        sa.Column("direction", sa.String(16), server_default="consumption", nullable=False),
        sa.Column("value", sa.Numeric(16, 6), nullable=False),
        sa.Column("unit", sa.String(12), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_provider", sa.String(60), nullable=False),
        sa.Column("source_record_ref", sa.String(200), nullable=False),
        sa.Column("quality", sa.String(24), server_default="raw", nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("meter_point_id", "measurement", "interval_start", "interval_end", "source_record_ref", name="uq_energy_reading_source_interval"),
    )
    op.create_index("ix_energy_data_readings_meter_point_id", "energy_data_readings", ["meter_point_id"])
    op.create_index("ix_energy_readings_meter_start", "energy_data_readings", ["meter_point_id", "interval_start"])

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), server_default="queued", nullable=False),
        sa.Column("records_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_jobs_household_id", "sync_jobs", ["household_id"])
    op.create_index("ix_sync_jobs_household_created", "sync_jobs", ["household_id", "created_at"])


def downgrade() -> None:
    op.drop_table("sync_jobs")
    op.drop_table("energy_data_readings")
    op.drop_table("consent_records")
    op.drop_table("provider_connections")
    op.drop_table("meter_points")
    op.drop_table("properties")
