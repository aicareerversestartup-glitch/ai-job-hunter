"""Initial schema.

Creates every table from the SQLModel metadata so the baseline always matches the models.
Later schema changes are generated with: alembic revision --autogenerate -m "describe change"

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-21
"""
from alembic import op
from sqlmodel import SQLModel

import backend.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
