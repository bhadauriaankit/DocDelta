"""
Phase 4 introduces enough moving parts (DB, broker, object storage) that
scattering `os.getenv()` calls through the codebase would get messy fast.
One settings object, read once at import time, gives every other module a
single source of truth — and a single place to look when something's
misconfigured.

Defaults point at the Docker Compose service names (postgres/redis/minio)
since Compose is the primary way to run Phase 4+. Override any of these
with real environment variables to run against something else.
"""

import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://doccompare:doccompare@postgres:5432/doccompare"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "doccompare")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "doccompare123")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "doccompare-uploads")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # "minio" for real object storage, "memory" for tests / no-MinIO envs.
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "minio")

    # Runs Celery tasks synchronously in-process instead of dispatching to
    # a real worker over Redis. Tests set this so they don't need a
    # separate worker process running.
    CELERY_TASK_ALWAYS_EAGER: bool = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"

    # "tfidf" (default) — local, lexical-overlap similarity via
    # scikit-learn, no downloads, no GPU. "sentence-transformers" — real
    # semantic embeddings, but requires the optional dependency in
    # requirements-semantic.txt AND a one-time model download; falls back
    # to "tfidf" automatically if that's not available. See app/embeddings.py.
    SEMANTIC_PROVIDER: str = os.getenv("SEMANTIC_PROVIDER", "tfidf")


settings = Settings()
