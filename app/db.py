from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _normalize_db_url(url: str) -> str:
    # SQLAlchemy expects sqlite+pysqlite for modern usage; sqlite:/// works too.
    return url


db_url = _normalize_db_url(settings.database_url)

# SQLite note:
# FastAPI will run sync endpoints in a threadpool. With SQLite + connection pooling,
# you must disable sqlite3's thread check or you can hit:
# "SQLite objects created in a thread can only be used in that same thread"
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

