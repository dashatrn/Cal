from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
'''Set up a DB connection (create_engine)
Create reusable sessions to interact with DB (sessionmaker)
Define base classes for your DB models (DeclarativeBase)'''



# SQLite chosen because: zero install, single file committed to .gitignore.
# Swap to Postgres later by replacing this URL with:
# "postgresql+asyncpg://user:pass@host:5432/dbname"

#Sets up SQLite file path one folder up(backend/cal.db)
#sqlite:///path/to/file is the format sql expects
#path(__file__) get the current file's path. We go up one level so the .db file lives in backend root
SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parents[1] / 'cal.db'}"



'''engine manages the connection to the SQLite file.
echo=False: don’t print every query to the terminal.
future=True: use newer SQLAlchemy behavior.'''

engine = create_engine(SQLITE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
'''This factory makes sessions, single-use database connections per request.
autoflush and autocommit set to False means control when changes get saved, which is safer'''




class Base(DeclarativeBase):
    """Foundation class for all DB models, every model will inherit from this so SQLAlchemy can track.
    Declarative base every model inherits—keeps metadata in one place."""
    pass

def get_db() -> Generator:
    """FastAPI dependency: gives a DB session and guarantees close().
    injects database session into route. yield db give fresh connection when request omes in, close when done"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()