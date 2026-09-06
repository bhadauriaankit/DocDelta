import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, check_schema_up_to_date


def test_check_schema_passes_on_a_freshly_created_database():
    """The test suite's own database (created via init_db() in
    conftest.py) should always pass this check — if it doesn't, something
    is wrong with the check itself, not the schema."""
    check_schema_up_to_date()  # should not raise


def test_check_schema_detects_a_missing_column():
    """Simulates exactly the real bug this check exists to catch: an
    existing table that predates a column the current ORM model expects.
    Built with a genuinely separate engine/metadata (not the app's real
    one) so this test doesn't disturb the shared test database used by
    every other test in the suite."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    # An intentionally "old" version of comparison_jobs missing the
    # error_message column that the real ORM model expects.
    old_metadata = MetaData()
    Table(
        "comparison_jobs",
        old_metadata,
        Column("id", String(36), primary_key=True),
        Column("status", String(20)),
        # error_message column deliberately omitted
        Column("original_document_id", String(36)),
        Column("modified_document_id", String(36)),
    )
    old_metadata.create_all(engine)

    import app.db as db_module

    original_engine = db_module.engine
    db_module.engine = engine
    try:
        with pytest.raises(RuntimeError, match="schema is out of date"):
            check_schema_up_to_date()
    finally:
        db_module.engine = original_engine


def test_check_schema_error_message_names_the_missing_column():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    old_metadata = MetaData()
    Table(
        "difference_results",
        old_metadata,
        Column("id", String(36), primary_key=True),
        Column("job_id", String(36)),
        # formatting_diff column deliberately omitted, mirroring the real
        # bug this check was built to catch
    )
    old_metadata.create_all(engine)

    import app.db as db_module

    original_engine = db_module.engine
    db_module.engine = engine
    try:
        with pytest.raises(RuntimeError, match="formatting_diff"):
            check_schema_up_to_date()
    finally:
        db_module.engine = original_engine
