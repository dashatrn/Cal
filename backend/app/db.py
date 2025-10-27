# backend/app/db.py
"""Database session and base model setup."""

from __future__ import annotations

from typing import Generator
from os import getenv
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _normalize_db_url(url: str) -> str:
    """Normalize common Postgres URLs to the psycopg2 driver form."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


RAW_URL = getenv("DATABASE_URL")
if RAW_URL:
    DB_URL = _normalize_db_url(RAW_URL)
else:
    DB_URL = f"sqlite:///{(Path(__file__).resolve().parents[1] / 'cal.db')}"

is_sqlite = DB_URL.startswith("sqlite")

engine = create_engine(
    DB_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=({} if not is_sqlite else {"check_same_thread": False}),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


def get_db() -> Generator:
    """
    FastAPI dependency that yields a session per request
    and guarantees it is closed afterwards.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()