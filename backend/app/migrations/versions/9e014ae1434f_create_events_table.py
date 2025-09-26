"""create events table

Revision ID: 9e014ae1434f
Revises:
Create Date: 2025-07-31 18:10:32.187037
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9e014ae1434f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end",   sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("events")