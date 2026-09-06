"""
SQLAlchemy setup. Handles one wrinkle: tests use an in-memory SQLite
database (fast, no external service needed), which requires a couple of
non-default settings — a single shared connection via StaticPool, since
each new connection to ":memory:" SQLite is otherwise a *different*,
empty database, and `check_same_thread=False` since FastAPI's TestClient
can call in from a different thread than the one that created the engine.
Postgres (used everywhere outside tests) needs neither.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_is_sqlite_memory = settings.DATABASE_URL.startswith("sqlite") and ":memory:" in settings.DATABASE_URL

_engine_kwargs: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if _is_sqlite_memory:
        _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — one session per request, always closed after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def new_session() -> Session:
    """For code that isn't a FastAPI request handler (e.g. Celery tasks),
    which need to manage a session's lifecycle themselves."""
    return SessionLocal()


def init_db() -> None:
    """Create tables if they don't exist yet.

    A real migration tool (Alembic) is worth adding once the schema starts
    changing after data already exists in a real deployment — for a
    from-scratch learning project, `create_all` is the right amount of
    complexity for now. Revisit this before Phase 8 if you want zero-
    downtime schema changes to matter.
    """
    from app import db_models  # noqa: F401 — import registers models on Base.metadata

    Base.metadata.create_all(bind=engine)


def check_schema_up_to_date() -> None:
    """Compares the live database's actual columns against what the ORM
    models expect, and raises immediately and loudly if they don't match.

    This exists because `create_all()` above only creates MISSING
    tables — it never alters an existing one. Pull a new version of this
    project that added a column to `difference_results` (which has
    happened in nearly every feature added after Phase 4) without
    resetting your local Postgres volume, and the mismatch used to only
    surface as a confusing `psycopg2.errors.UndefinedColumn` deep in a
    worker's stack trace, the moment a job tried to write its result —
    often *after* the actual comparison work had already succeeded, which
    made it look like something more mysterious had gone wrong than "the
    schema is stale." Calling this at startup (see main.py's lifespan and
    celery_app.py's worker_process_init handler) turns that into an
    immediate, clear failure instead.
    """
    from sqlalchemy import inspect

    from app import db_models  # noqa: F401 — ensure models are registered before inspecting

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing_by_table: dict[str, list[str]] = {}

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # a brand-new table — create_all() already handled this case
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        expected_columns = {col.name for col in table.columns}
        missing = sorted(expected_columns - existing_columns)
        if missing:
            missing_by_table[table.name] = missing

    if missing_by_table:
        details = "; ".join(f"'{table}' is missing column(s) {cols}" for table, cols in missing_by_table.items())
        raise RuntimeError(
            f"Database schema is out of date: {details}. This project doesn't use a "
            "migration tool yet (see the note in init_db() above), so schema changes "
            "require a fresh database. Reset your local dev database with "
            "`docker compose down -v` and then `docker compose up --build` again."
        )
