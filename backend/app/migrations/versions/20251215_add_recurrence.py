"""add recurrence series + exceptions and link events to a series

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
    bind = op.get_bind()
    insp = inspect(bind)

    tables = set(insp.get_table_names())

    # ── recurrence_series ──────────────────────────────────────────────
    if "recurrence_series" not in tables:
        op.create_table(
            "recurrence_series",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end",   sa.DateTime(timezone=True), nullable=False),
            sa.Column("tz", sa.String(length=64), nullable=False, server_default="UTC"),
            sa.Column("freq", sa.String(length=16), nullable=False, server_default="WEEKLY"),
            sa.Column("interval", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("byweekday", sa.String(length=32), nullable=True),
            sa.Column("until", sa.Date(), nullable=False),
            sa.Column("description", sa.String(length=2000), nullable=True),
            sa.Column("location",    sa.String(length=255),  nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # Refresh inspector after schema changes
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    # ── recurrence_exceptions ──────────────────────────────────────────
    if "recurrence_exceptions" not in tables:
        op.create_table(
            "recurrence_exceptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("series_id", sa.Integer(), sa.ForeignKey("recurrence_series.id", ondelete="CASCADE"), nullable=False),
            sa.Column("original_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("override_title", sa.String(length=200), nullable=True),
            sa.Column("override_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("override_end",   sa.DateTime(timezone=True), nullable=True),
            sa.Column("override_description", sa.String(length=2000), nullable=True),
            sa.Column("override_location",    sa.String(length=255),  nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("series_id", "original_start", name="uq_series_original_start"),
        )

    # ── events table: add recurrence linkage columns if missing ─────────
    cols = {c["name"] for c in insp.get_columns("events")}

    if "series_id" not in cols:
        op.add_column("events", sa.Column("series_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_events_series_id",
            "events",
            "recurrence_series",
            ["series_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_events_series_id", "events", ["series_id"])

    if "original_start" not in cols:
        op.add_column("events", sa.Column("original_start", sa.DateTime(timezone=True), nullable=True))

    if "is_exception" not in cols:
        op.add_column(
            "events",
            sa.Column("is_exception", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "events" in tables:
        cols = {c["name"] for c in insp.get_columns("events")}
        if "is_exception" in cols:
            op.drop_column("events", "is_exception")
        if "original_start" in cols:
            op.drop_column("events", "original_start")
        if "series_id" in cols:
            try:
                op.drop_index("ix_events_series_id", table_name="events")
            except Exception:
                pass
            try:
                op.drop_constraint("fk_events_series_id", "events", type_="foreignkey")
            except Exception:
                pass
            op.drop_column("events", "series_id")

    if "recurrence_exceptions" in tables:
        op.drop_table("recurrence_exceptions")
    if "recurrence_series" in tables:
        op.drop_table("recurrence_series")