from __future__ import annotations

from contextlib import contextmanager
import time

from sqlalchemy import create_engine, Column, Integer, String, Float, Text, event
from sqlalchemy.orm import declarative_base, sessionmaker

import config

Base = declarative_base()


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    created_at = Column(Text, nullable=True)     # ISO UTC
    last_seen_at = Column(Text, nullable=True)   # ISO UTC
    confirmations = Column(Integer, nullable=True)
    bearing = Column(Float, nullable=True)       # degrees 0..360 (optional)


def _make_engine():
    url = (config.DATABASE_URL or "sqlite:///./data.db").strip()

    connect_args = {}
    if url.lower().startswith("sqlite"):
        connect_args = {
            "check_same_thread": False,
            "timeout": 30,  # важно против "database is locked"
        }

    engine = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )

    # Включаем WAL и нормальный sync для стабильности SQLite
    if url.lower().startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def commit_with_retry(s, retries: int = 8, base_delay: float = 0.2):
    last = None
    for i in range(retries):
        try:
            s.commit()
            return
        except Exception as e:
            last = e
            s.rollback()
            time.sleep(base_delay * (i + 1))
    raise last
