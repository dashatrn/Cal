from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base

#defining a table called events, real table in db
class Event(Base):
    __tablename__ = "events"
#unique id number for each row, event name, start time, end time
    id:    Mapped[int]      = mapped_column(Integer, primary_key=True)
    title: Mapped[str]      = mapped_column(String(200), nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end:   Mapped[datetime] = mapped_column(DateTime, nullable=False)