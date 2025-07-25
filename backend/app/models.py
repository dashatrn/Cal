from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base

#importing column types, integer, string, DateTime
#modern SQLAlchemy 2.0 syntax for declaring table columns.
#needed to type start and end as real datetime objects
#pulls Base clas defined in db.py, connecting model to db metadata system so SQLAlchemy knows how to turn class into real table when app starts

#defining a table called events, real table in db, each Event(is like one row in the table). tablename = events tells SQL to make table called events into db
#id is uniqeu identified for each row, numbered label for each event, primkey=t tells sql to auto increment and use as unique row identifier
#name of event, string up to 200 characters, required can't be false
#event start and end times, stored as datetime values so can be filtered, sorted, and renderd on calendar. also required

class Event(Base):
    __tablename__ = "events"
#unique id number for each row, event name, start time, end time
    id:    Mapped[int]      = mapped_column(Integer, primary_key=True)
    title: Mapped[str]      = mapped_column(String(200), nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end:   Mapped[datetime] = mapped_column(DateTime, nullable=False)





'''
“Hey SQLAlchemy, when the app starts, please create a table called events with these columns:”
id      INTEGER PRIMARY KEY
title   VARCHAR(200) NOT NULL
start   DATETIME NOT NULL
end     DATETIME NOT NULL

defines db structure
defines shape of database tables
defines Event model, which becomes actual events table in db
Base.metadata.create_all(engine)
A class Event that inherits from Base. create SQL table called events, with columns id, title, start, end
'''