"""
DocCompare AI — backend entrypoint.

Phase 0: /health only.
Phase 1: /compare — synchronous plain-text diff.
Phase 3: /compare gains PDF/DOCX support.
Phase 6: adds OCR (scanned PDFs and standalone images) and page-level
visual comparison for PDF vs PDF. Visual diff images are served through
GET /files/{key} rather than exposing MinIO directly to the browser —
see that endpoint's docstring for why.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.db import check_schema_up_to_date, get_db, init_db
from app.db_models import ComparisonJob, Document
from app.schemas import (
    DiffSegmentResponse,
    FormattingDiffResponse,
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
    PageVisualDiffResponse,
    PasteCompareRequest,
    SemanticDiffResponse,
    SpreadsheetDiffResponse,
)
from app.storage import get_storage
from app.tasks import process_comparison_job

APP_VERSION = "0.7.0-phase7"

# PDFs/DOCX are naturally bigger than plain text; 20MB comfortably covers
# most everyday documents while bounding worst-case memory use.
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

# Cap pasted text to 100,000 characters per side — generous enough for
# long legal agreements or multi-page drafts while bounding memory.
MAX_PASTE_CHARS = 100_000


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    check_schema_up_to_date()
    if settings.STORAGE_BACKEND == "memory" and not settings.CELERY_TASK_ALWAYS_EAGER:
        # InMemoryStorage is a per-process dict — it cannot be shared
        # between the API process and a separate Celery worker process.
        # This combination only makes sense in tests (where the worker
        # runs eagerly, in the same process). Outside of tests, this
        # would look like it works when creating a job and then fail
        # with a confusing KeyError the moment the worker tries to fetch
        # the uploaded bytes — surfacing it here, loudly, at startup
        # instead is a much shorter debugging session.
        import warnings

        warnings.warn(
            "STORAGE_BACKEND=memory with a real (non-eager) Celery worker will fail as "
            "soon as a job is processed — the worker runs in a different process and "
            "can't see the API process's in-memory storage. Use STORAGE_BACKEND=minio "
            "for anything beyond the test suite.",
            stacklevel=1,
        )
    yield


app = FastAPI(
    title="DocCompare AI",
    version=APP_VERSION,
    description="Phase 7: adds paragraph-level semantic comparison.",
    lifespan=lifespan,
)

# Wide-open CORS is fine for local dev only. Tighten this before Phase 8
# deployment (allow only the real frontend origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=APP_VERSION)


async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"'{file.filename}' exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit.",
        )
    return raw


def _create_job_and_enqueue(
    db: Session,
    *,
    original_filename: str,
    original_bytes: bytes,
    modified_filename: str,
    modified_bytes: bytes,
) -> JobCreateResponse:
    storage = get_storage()

    original_doc = Document(
        filename=original_filename,
        storage_key=f"uploads/{uuid4()}",
        size_bytes=len(original_bytes),
    )
    modified_doc = Document(
        filename=modified_filename,
        storage_key=f"uploads/{uuid4()}",
        size_bytes=len(modified_bytes),
    )

    storage.put_bytes(original_doc.storage_key, original_bytes)
    storage.put_bytes(modified_doc.storage_key, modified_bytes)

    db.add(original_doc)
    db.add(modified_doc)
    db.flush()  # assigns IDs without ending the transaction

    job = ComparisonJob(
        original_document_id=original_doc.id,
        modified_document_id=modified_doc.id,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job_id = job.id
    initial_status = job.status  # captured now — see note in tasks.py re: eager mode

    process_comparison_job.delay(job_id)

    return JobCreateResponse(id=job_id, status=initial_status)


@app.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def create_job(
    original: UploadFile = File(..., description="The original / baseline document"),
    modified: UploadFile = File(..., description="The modified / new document"),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Accepts two files, stores them, and enqueues a background
    comparison job. Deliberately does NOT parse/diff the documents here —
    that's the whole point of moving this to a worker: the request
    returns fast regardless of how big or slow-to-parse the files are.

    Format validation (magic bytes, not just extension) still happens,
    but inside the worker now, not here — see app/tasks.py.
    """
    original_bytes = await _read_upload(original)
    modified_bytes = await _read_upload(modified)

    return _create_job_and_enqueue(
        db,
        original_filename=original.filename or "original",
        original_bytes=original_bytes,
        modified_filename=modified.filename or "modified",
        modified_bytes=modified_bytes,
    )


@app.post("/jobs/text", response_model=JobCreateResponse, status_code=202)
async def create_text_job(
    payload: PasteCompareRequest,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Accepts two plain text snippets via JSON, stores them as synthetic
    .txt files, and enqueues the comparison pipeline. Reuses the exact same
    worker pipeline as file uploads."""
    if len(payload.original_text) > MAX_PASTE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Original text exceeds the {MAX_PASTE_CHARS:,} character limit.",
        )
    if len(payload.modified_text) > MAX_PASTE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Modified text exceeds the {MAX_PASTE_CHARS:,} character limit.",
        )

    return _create_job_and_enqueue(
        db,
        original_filename="pasted-original.txt",
        original_bytes=payload.original_text.encode("utf-8"),
        modified_filename="pasted-modified.txt",
        modified_bytes=payload.modified_text.encode("utf-8"),
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = db.get(ComparisonJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No job found with that id.")

    response = JobStatusResponse(id=job.id, status=job.status, error=job.error_message)

    if job.status == "done" and job.result is not None:
        response.similarity = job.result.similarity
        response.stats = job.result.stats
        response.segments = [DiffSegmentResponse(**seg) for seg in job.result.segments]
        response.warnings = job.result.warnings
        if job.result.table_diff is not None:
            response.table_diff = SpreadsheetDiffResponse(**job.result.table_diff)
        if job.result.visual_diff is not None:
            response.visual_diff = [PageVisualDiffResponse(**p) for p in job.result.visual_diff]
        if job.result.semantic_diff is not None:
            response.semantic_diff = SemanticDiffResponse(**job.result.semantic_diff)
        if job.result.formatting_diff is not None:
            response.formatting_diff = FormattingDiffResponse(**job.result.formatting_diff)

    return response


# Only "diffs/<uuid>.png" keys are servable here — deliberately not the
# "uploads/<uuid>" keys that hold the actual uploaded documents. Job
# responses never expose a Document's storage_key to the frontend (see
# JobStatusResponse), so there's no *intended* way to reach an uploaded
# original through this route — but this regex is the actual enforcement,
# not the response shape. Even if a key were guessed or leaked some other
# way, this endpoint still couldn't be used to read back someone's
# original document, only a generated diff image. This also incidentally
# rules out path traversal (no "..", no leading "/") without needing a
# separate check for it.
_SERVABLE_FILE_KEY = re.compile(r"^diffs/[0-9a-fA-F\-_]+\.png$")


@app.get("/files/{storage_key:path}")
async def get_file(storage_key: str) -> Response:
    if not _SERVABLE_FILE_KEY.match(storage_key):
        raise HTTPException(status_code=403, detail="This file cannot be accessed directly.")

    storage = get_storage()
    try:
        data = storage.get_bytes(storage_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc

    return Response(content=data, media_type="image/png")
