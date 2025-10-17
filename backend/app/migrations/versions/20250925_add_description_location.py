"""add description and location columns to events

Revision ID: 20250925_add_desc_loc
Revises: 9e014ae1434f
Create Date: 2025-09-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20250925_add_desc_loc"
down_revision: Union[str, Sequence[str], None] = "9e014ae1434f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("events")}

    # Add only if missing
    if "description" not in cols:
        op.add_column(
            "events",
            sa.Column("description", sa.String(length=2000), nullable=True),
        )
    if "location" not in cols:
        op.add_column(
            "events",
            sa.Column("location", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("events")}

    # Drop only if present
    if "location" in cols:
        op.drop_column("events", "location")
    if "description" in cols:
        op.drop_column("events", "description")