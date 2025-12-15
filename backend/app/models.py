from __future__ import annotations

from typing import Optional
from datetime import datetime, date

from sqlalchemy import (
    Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class RecurrenceSeries(Base):
    """A recurring-series definition.

    We materialize occurrences into the `events` table (so the UI stays simple),
    and keep a series + exception registry so we can represent "recurrence with
    exceptions" truthfully and regenerate safely later.
    """

    __tablename__ = "recurrence_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # Stored in UTC (timezone-aware)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end:   Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Timezone name used to interpret repeatUntil and local-time anchoring (DST-safe)
    tz: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    # Currently supported: WEEKLY, DAILY, MONTHLY
    freq: Mapped[str] = mapped_column(String(16), nullable=False, default="WEEKLY")

    # Repeat interval: every N weeks/days/months
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # For weekly recurrence: comma-separated weekday numbers (0=Sun ... 6=Sat)
    byweekday: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Last local date (in `tz`) on which an occurrence may start
    until: Mapped[date] = mapped_column(nullable=False)

    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    location:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["Event"]] = relationship(back_populates="series", cascade="all, delete-orphan")
    exceptions: Mapped[list["RecurrenceException"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class RecurrenceException(Base):
    """An exception for a specific original occurrence (identified by original_start).

    kind:
      - skip: that occurrence should not exist
      - override: occurrence exists but was edited (title/time/etc.)
    """

    __tablename__ = "recurrence_exceptions"
    __table_args__ = (
        UniqueConstraint("series_id", "original_start", name="uq_series_original_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("recurrence_series.id", ondelete="CASCADE"), nullable=False)

    # The original occurrence start time (UTC, tz-aware) before any edits
    original_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "skip" | "override"

    # Override payload (only used when kind == "override")
    override_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    override_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    override_end:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    override_description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    override_location:    Mapped[Optional[str]] = mapped_column(String(255),   nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    series: Mapped["RecurrenceSeries"] = relationship(back_populates="exceptions")


class Event(Base):
    __tablename__ = "events"

    id:    Mapped[int]       = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str]       = mapped_column(String(200), nullable=False)
    start: Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)
    end:   Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)

    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    location:    Mapped[Optional[str]] = mapped_column(String(255),   nullable=True)

    # Recurrence linkage (nullable for one-off events)
    series_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recurrence_series.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # For series events, this is the original start time of the occurrence (UTC) before any edits.
    original_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # True if this specific occurrence was edited (override exception)
    is_exception: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    series: Mapped[Optional["RecurrenceSeries"]] = relationship(back_populates="events")