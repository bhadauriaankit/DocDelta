"""
Celery app. `include=["app.tasks"]` is what makes `celery -A app.celery_app
worker` actually find and register the task defined in tasks.py — without
it, the worker process starts up fine but has zero tasks registered,
which is a very confusing way to spend twenty minutes the first time you
hit it.
"""

from celery import Celery
from celery.signals import worker_process_init

from app.config import settings

celery_app = Celery(
    "doccompare",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Tests set this to True so `.delay(...)` runs the task synchronously,
    # in-process, instead of requiring a real worker listening on Redis.
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    # Explicit rather than relying on the current (soon-changing) default —
    # Celery 6 flips this behavior, so pin it now instead of being
    # surprised by an upgrade later.
    broker_connection_retry_on_startup=True,
)


@worker_process_init.connect
def _check_database_on_worker_start(**kwargs) -> None:
    """Runs once per worker process at startup — the same "fail loudly,
    immediately" check the API does in main.py's lifespan (see
    app.db.check_schema_up_to_date's docstring for why this exists at
    all). Without this, a stale schema let the worker start up looking
    healthy and only failed confusingly on the first job's final DB
    write — this makes the worker crash-loop with a clear message
    instead, which is a much shorter debugging session.

    Skipped in eager mode (tests) — there is no separate worker process
    to initialize in that case, and the API's own lifespan already ran
    this check in the same process.
    """
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return

    from app.db import check_schema_up_to_date, init_db

    init_db()
    check_schema_up_to_date()
