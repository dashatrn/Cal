"""add description and location columns to events

Revision ID: 20250925_add_description_location
Revises: 6963768b591b
Create Date: 2025-09-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# ...
revision: str = "20250925_add_description_location"
down_revision: Union[str, Sequence[str], None] = "9e014ae1434f"  # ← was 6963...
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
# ...


def upgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("description", sa.String(length=2000), nullable=True))
        batch.add_column(sa.Column("location", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.drop_column("location")
        batch.drop_column("description")