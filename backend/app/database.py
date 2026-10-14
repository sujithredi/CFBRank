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
from sqlalchemy import create_engine, inspect, text
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


def _add_missing_columns():
    """
    `create_all` skips tables that already exist, so a column added to a model
    after the database file was first created (e.g. power_ratings.offense_rating)
    never appears in it -- and every query touching that table then fails with
    "no such column". Add any such columns with ALTER TABLE.

    Only nullable columns are handled, since those can be added to a table that
    already has rows without a default. Stopgap until Alembic migrations.
    """
    inspector = inspect(engine)
    preparer = engine.dialect.identifier_preparer
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                conn.execute(
                    text(
                        f"ALTER TABLE {preparer.quote(table.name)} "
                        f"ADD COLUMN {preparer.quote(column.name)} {column_type}"
                    )
                )


def init_db():
    """
    Create tables that don't exist yet, and add newly-introduced nullable
    columns to tables that do.

    Fine for MVP/SQLite. Once the schema needs to evolve in ways this can't
    handle (renames, NOT NULL columns, backfills -- Milestone 2+), switch to
    Alembic migrations instead of calling this on every startup.
    """
    import app.models  # noqa: F401  (ensures models are registered on Base)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
