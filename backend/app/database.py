"""
Database engine/session setup.

Local dev / MVP: SQLite file (backend/cfbrank.db), zero setup required.
Later (Milestone 3 deploy): set DATABASE_URL to a Postgres URL, e.g.
    postgresql+psycopg2://user:password@host:5432/cfbrank
and nothing else in the app needs to change -- models.py and every
router/script that imports `SessionLocal` / `get_db` from here keeps working.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cfbrank.db")

# check_same_thread is only needed for SQLite; harmless to guard on the URL.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create tables that don't exist yet.

    Fine for MVP/SQLite. Once the schema needs to evolve without dropping
    data (Milestone 2+), switch to Alembic migrations instead of calling
    this on every startup.
    """
    import app.models  # noqa: F401  (ensures models are registered on Base)

    Base.metadata.create_all(bind=engine)
