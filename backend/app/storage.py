"""
A tiny abstraction over "put bytes somewhere, get bytes back by key."

This exists so the rest of the app (API handlers, Celery tasks) never
imports the `minio` SDK directly — they just call `get_storage()` and use
the interface. That's what makes it possible to run the full test suite
without a real MinIO server: swap in InMemoryStorage and nothing else
changes. It's also what Phase 13/26 in the original spec calls the
"modular AI provider" idea, applied here to storage instead.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod

from app.config import settings


class ObjectStorage(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes: ...


class InMemoryStorage(ObjectStorage):
    """Used in tests, and as a fallback for running the API without MinIO
    set up. Data only lives as long as the process does — never use this
    for anything you actually want to keep."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self._data[key]


class MinioStorage(ObjectStorage):
    def __init__(self) -> None:
        # Imported lazily so environments running with STORAGE_BACKEND=memory
        # (like the test suite) never need the `minio` package importable
        # in the first place.
        from minio import Minio

        self._client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._bucket = settings.MINIO_BUCKET
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def put_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(self._bucket, key, io.BytesIO(data), length=len(data))

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


_storage_instance: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    """Lazily-constructed singleton. Constructing MinioStorage does a
    network round-trip (bucket_exists/make_bucket), so we only pay that
    cost once per process, not once per request."""
    global _storage_instance
    if _storage_instance is None:
        if settings.STORAGE_BACKEND == "memory":
            _storage_instance = InMemoryStorage()
        else:
            _storage_instance = MinioStorage()
    return _storage_instance
