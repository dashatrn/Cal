"""restore missing revision so production DB can migrate

Revision ID: 20251215_add_recurrence
Revises: 20250925_add_desc_loc
Create Date: 2025-12-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20251215_add_recurrence"
down_revision: Union[str, Sequence[str], None] = "20250925_add_desc_loc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    This revision existed in prod at some point (per alembic_version),
    but the file got removed when history was rewritten.

    Keep this migration SAFE:
    - If recurrence columns exist, do nothing.
    - If they don't exist (fresh DB), add them.
    """
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("events")}

    # Optional recurrence storage (harmless if your app ignores it)
    if "repeat_days" not in cols:
        op.add_column("events", sa.Column("repeat_days", sa.JSON(), nullable=True))
    if "repeat_until" not in cols:
        op.add_column("events", sa.Column("repeat_until", sa.Date(), nullable=True))
    if "repeat_every_weeks" not in cols:
        op.add_column("events", sa.Column("repeat_every_weeks", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("events")}

    if "repeat_every_weeks" in cols:
        op.drop_column("events", "repeat_every_weeks")
    if "repeat_until" in cols:
        op.drop_column("events", "repeat_until")
    if "repeat_days" in cols:
        op.drop_column("events", "repeat_days")