"""
The actual comparison work, moved out of the request/response cycle.

Extraction and text-diffing are the Phase 3 logic, unchanged. Phase 5
added table-diffing when both documents have tables. Phase 6 adds one
more optional layer: if BOTH documents are PDFs, also render each page
and run a visual (SSIM-based) comparison — this is deliberately kept
independent of whether the text/table diff succeeded, since a rendering
failure on an unusual PDF shouldn't take down a comparison that otherwise
worked fine.

A Celery task can't reuse the FastAPI request's DB session (it may well
run in a different process entirely) — it opens and closes its own.
"""

from __future__ import annotations

import dataclasses
import logging

from app.celery_app import celery_app
from app.db import new_session
from app.db_models import ComparisonJob, DifferenceResult
from app.diff_engine import compare_text
from app.parsers import DocumentParseError, extract_text
from app.formatting_diff import compare_formatting, extract_formatting
from app.semantic_diff import compare_semantic
from app.storage import ObjectStorage, get_storage
from app.table_diff import compare_tables
from app.visual_diff import compare_documents_visual, compare_pdf_pages, make_diff_storage_key

logger = logging.getLogger(__name__)


def _store_diff_image(storage: ObjectStorage, data: bytes) -> str:
    key = make_diff_storage_key()
    storage.put_bytes(key, data)
    return key


@celery_app.task(name="process_comparison_job")
def process_comparison_job(job_id: str) -> None:
    # Note on eager mode (used by tests): `.delay()` runs this function
    # synchronously, in-process, via a *different* DB session than the one
    # that created the job. That's fine — this task always re-fetches the
    # job fresh rather than trusting any state passed in — but it does
    # mean the caller's own in-memory `job` object won't reflect this
    # task's changes afterward without an explicit db.refresh(). The API
    # layer avoids relying on that (see main.py's `initial_status`).
    db = new_session()
    try:
        job = db.get(ComparisonJob, job_id)
        if job is None:
            # Job row vanished (shouldn't normally happen) — nothing to
            # do, and nowhere to report an error to.
            return

        job.status = "processing"
        db.commit()

        storage = get_storage()
        original_bytes = storage.get_bytes(job.original_document.storage_key)
        modified_bytes = storage.get_bytes(job.modified_document.storage_key)

        original_doc = extract_text(job.original_document.filename, original_bytes)
        modified_doc = extract_text(job.modified_document.filename, modified_bytes)

        diff = compare_text(original_doc.text, modified_doc.text)
        warnings = [*original_doc.warnings, *modified_doc.warnings]

        table_diff_dict: dict | None = None
        if original_doc.tables and modified_doc.tables:
            spreadsheet_diff = compare_tables(original_doc.tables, modified_doc.tables)
            table_diff_dict = dataclasses.asdict(spreadsheet_diff)
        elif original_doc.tables or modified_doc.tables:
            warnings.append(
                "Table structure comparison was skipped because only one of these "
                "documents has spreadsheet-like tables — showing text comparison only."
            )

        visual_diff_list: list[dict] | None = None
        visual_formats = {"pdf", "docx"}
        if original_doc.format in visual_formats and modified_doc.format in visual_formats:
            try:
                visual_diff_list = compare_documents_visual(
                    original_bytes,
                    original_doc.format,
                    modified_bytes,
                    modified_doc.format,
                    store_image=lambda data: _store_diff_image(storage, data),
                    store_all_assets=True,
                    include_extra_pages=True,
                )
            except Exception:
                # Visual diffing is an additional layer on top of a
                # text comparison that has already succeeded by this
                # point — an unusual document structure that breaks rendering
                # shouldn't fail the whole job, just skip this extra.
                logger.exception("Visual page comparison failed for job %s", job_id)
                warnings.append("Visual page comparison could not be completed for these documents.")

        semantic_diff_dict: dict | None = None
        if original_doc.text.strip() and modified_doc.text.strip():
            try:
                semantic = compare_semantic(original_doc.text, modified_doc.text)
                semantic_diff_dict = dataclasses.asdict(semantic)
            except Exception:
                # Same reasoning as visual diffing above: an additional
                # layer on top of an already-successful comparison, so a
                # failure here shouldn't fail the whole job.
                logger.exception("Semantic comparison failed for job %s", job_id)
                warnings.append("Semantic (meaning-based) comparison could not be completed.")

        formatting_diff_dict: dict | None = None
        original_formatting = extract_formatting(original_doc.format, original_bytes)
        modified_formatting = extract_formatting(modified_doc.format, modified_bytes)
        if original_formatting is not None and modified_formatting is not None:
            try:
                formatting = compare_formatting(original_formatting, modified_formatting)
                formatting_diff_dict = dataclasses.asdict(formatting)
            except Exception:
                logger.exception("Formatting comparison failed for job %s", job_id)
                warnings.append("Formatting comparison could not be completed.")
        elif (original_formatting is not None) != (modified_formatting is not None):
            warnings.append(
                "Formatting (font/style) comparison was skipped because it's only "
                "supported for DOCX and PDF, and only one of these documents is one "
                "of those formats."
            )

        db.add(
            DifferenceResult(
                job_id=job.id,
                similarity=diff.similarity,
                stats=diff.stats,
                segments=[
                    {"type": s.type, "original": s.original, "modified": s.modified}
                    for s in diff.segments
                ],
                warnings=warnings,
                table_diff=table_diff_dict,
                visual_diff=visual_diff_list,
                semantic_diff=semantic_diff_dict,
                formatting_diff=formatting_diff_dict,
            )
        )
        job.status = "done"
        db.commit()

    except DocumentParseError as exc:
        # Same "understandable to normal users" principle as the
        # synchronous Phase 3 errors — it just has to travel through a
        # job row instead of an HTTP response now.
        db.rollback()
        job = db.get(ComparisonJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = exc.user_message
            db.commit()

    except Exception:
        db.rollback()
        job = db.get(ComparisonJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = "Something went wrong while comparing these documents."
            db.commit()
        raise  # still surface unexpected errors in worker logs / Celery result backend

    finally:
        db.close()
