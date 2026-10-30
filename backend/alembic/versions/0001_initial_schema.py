"""Create the initial HEI household and electricity schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401 - register all tables

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bootstrap migration: create the complete initial metadata schema.
    # Subsequent migrations should use explicit Alembic operations.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
