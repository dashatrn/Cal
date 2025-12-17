# backend/app/schemas.py
from __future__ import annotations
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)  # allow from ORM