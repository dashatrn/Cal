from __future__ import annotations
from typing import Optional
from datetime import datetime

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

class Event(Base):
    __tablename__ = "events"

    id:    Mapped[int]       = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str]       = mapped_column(String(200), nullable=False)
    start: Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)
    end:   Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    location:    Mapped[Optional[str]] = mapped_column(String(255),   nullable=True)