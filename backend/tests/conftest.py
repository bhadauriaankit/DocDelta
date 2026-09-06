"""
These environment variables MUST be set before any `app.*` module gets
imported anywhere — app.db creates its SQLAlchemy engine, and
app.celery_app configures Celery's eager-mode flag, both at import time.
Pytest imports conftest.py before collecting test modules in the same
directory, which is what makes this ordering safe.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STORAGE_BACKEND", "memory")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

import pytest  # noqa: E402

from app.db import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Runs once for the whole test session — creates all tables against
    the in-memory SQLite database before any test touches the DB."""
    init_db()
