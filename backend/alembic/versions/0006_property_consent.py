"""Add household properties, protected supply points and consent grants.

Revision ID: 0006_property_consent
Revises: 0005_home_assistant
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_property_consent"
down_revision = "0005_home_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("properties"):
        op.create_table(
            "properties",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
            sa.Column("property_ref", sa.String(80), nullable=False),
            sa.Column("address_line_1", sa.String(160), nullable=False),
            sa.Column("address_line_2", sa.String(160), nullable=True),
            sa.Column("town", sa.String(120), nullable=False),
            sa.Column("county", sa.String(120), nullable=True),
            sa.Column("postcode", sa.String(12), nullable=False),
            sa.Column("country_code", sa.String(2), nullable=False, server_default="GB"),
            sa.Column("address_source", sa.String(40), nullable=True),
            sa.Column("address_source_ref", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("household_id", "property_ref", name="uq_property_household_ref"),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("properties")}
    if "ix_properties_household_id" not in indexes:
        op.create_index("ix_properties_household_id", "properties", ["household_id"])
    if "ix_properties_postcode" not in indexes:
        op.create_index("ix_properties_postcode", "properties", ["postcode"])

    if not sa.inspect(bind).has_table("supply_points"):
        op.create_table(
            "supply_points",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("property_id", sa.String(36), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fuel", sa.String(16), nullable=False),
            sa.Column("identifier_encrypted", sa.String(2048), nullable=False),
            sa.Column("identifier_hash", sa.String(64), nullable=False),
            sa.Column("identifier_last4", sa.String(4), nullable=False),
            sa.Column("supplier_name", sa.String(120), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="unverified"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("property_id", "fuel", "identifier_hash", name="uq_supply_point_property_fuel_hash"),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("supply_points")}
    if "ix_supply_points_property_id" not in indexes:
        op.create_index("ix_supply_points_property_id", "supply_points", ["property_id"])
    if "ix_supply_points_identifier_hash" not in indexes:
        op.create_index("ix_supply_points_identifier_hash", "supply_points", ["identifier_hash"])

    if not sa.inspect(bind).has_table("consent_grants"):
        op.create_table(
            "consent_grants",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
            sa.Column("property_id", sa.String(36), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=True),
            sa.Column("provider", sa.String(60), nullable=False),
            sa.Column("purpose", sa.String(200), nullable=False),
            sa.Column("scopes_json", sa.String(2000), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
            sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("consent_grants")}
    for name, columns in (
        ("ix_consent_grants_household_id", ["household_id"]),
        ("ix_consent_grants_property_id", ["property_id"]),
        ("ix_consent_household_status", ["household_id", "status"]),
    ):
        if name not in indexes:
            op.create_index(name, "consent_grants", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("consent_grants"):
        for item in inspector.get_indexes("consent_grants"):
            op.drop_index(item["name"], table_name="consent_grants")
        op.drop_table("consent_grants")
    if inspector.has_table("supply_points"):
        for item in inspector.get_indexes("supply_points"):
            op.drop_index(item["name"], table_name="supply_points")
        op.drop_table("supply_points")
    if inspector.has_table("properties"):
        for item in inspector.get_indexes("properties"):
            op.drop_index(item["name"], table_name="properties")
        op.drop_table("properties")
