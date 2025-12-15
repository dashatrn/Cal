# backend/app/schemas.py
from __future__ import annotations

from typing import Optional, List
from datetime import datetime, date

from pydantic import BaseModel, ConfigDict, Field


class EventIn(BaseModel):
    """Request/response schema for event creation/update."""
    title: str
    start: datetime  # UTC ISO string in/out
    end:   datetime
    description: Optional[str] = None
    location:    Optional[str] = None


class EventOut(EventIn):
    """Response schema for an event row (includes ID)."""
    id: int

    # Recurrence metadata (present for recurring occurrences; null/false for one-offs)
    series_id: Optional[int] = None
    original_start: Optional[datetime] = None
    is_exception: bool = False

    model_config = ConfigDict(from_attributes=True)  # allow from ORM


class SeriesIn(BaseModel):
    """Create a recurring series.

    Payload is intentionally aligned with the existing UI fields:
      - repeatDays (0=Sun..6=Sat)
      - repeatEveryWeeks (defaults to 1)
      - repeatUntil (YYYY-MM-DD, interpreted in tz)
    """
    title: str
    start: datetime
    end: datetime
    description: Optional[str] = None
    location: Optional[str] = None

    tz: str

    repeat_days: List[int] = Field(default_factory=list, alias="repeatDays")
    repeat_every_weeks: int = Field(default=1, alias="repeatEveryWeeks")
    repeat_until: date = Field(..., alias="repeatUntil")

    # Future-proofing: we can extend to DAILY/MONTHLY later without breaking the API
    freq: str = "WEEKLY"

    model_config = ConfigDict(populate_by_name=True)


class SeriesCreateOut(BaseModel):
    series_id: int = Field(..., alias="seriesId")
    events: list[EventOut]

    model_config = ConfigDict(populate_by_name=True)