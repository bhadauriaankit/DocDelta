"""
Three tables, matching the roadmap's Phase 4 plan:

    Document          — one row per uploaded file (original or modified),
                         pointing at where its bytes live in object storage
    ComparisonJob      — one row per comparison request, tracking status
                         through queued -> processing -> done|failed
    DifferenceResult   — one row per *completed* job, holding the actual
                         diff output (1:1 with ComparisonJob)

Keeping these three separate (rather than one big table) mirrors the real
tradeoff: Document rows could be reused across jobs later (e.g. "compare
this new file against last week's approved version" without re-uploading),
and DifferenceResult is naturally optional (a queued/failed job has none
yet) — a nullable JSON blob bolted onto ComparisonJob would work today but
fights the shape of where this is headed.

IDs are UUID strings rather than auto-increment integers on purpose: a job
ID gets handed to the browser for polling, and UUIDs don't leak "how many
jobs has this system processed" the way sequential integers do.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ComparisonJob(Base):
    __tablename__ = "comparison_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|done|failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    original_document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    modified_document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    original_document: Mapped[Document] = relationship(foreign_keys=[original_document_id])
    modified_document: Mapped[Document] = relationship(foreign_keys=[modified_document_id])
    result: Mapped["DifferenceResult | None"] = relationship(back_populates="job", uselist=False)


class DifferenceResult(Base):
    __tablename__ = "difference_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("comparison_jobs.id"), unique=True)

    similarity: Mapped[float] = mapped_column(Float)
    stats: Mapped[dict] = mapped_column(JSON)
    segments: Mapped[list] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    # Phase 5: populated only when both documents have spreadsheet-like
    # tables (XLSX/CSV/PPTX tables) — nullable since most comparisons
    # (plain text, PDF, DOCX) never have one. Stored as a plain JSON blob
    # (dataclasses.asdict() output from table_diff.SpreadsheetDiff)
    # rather than its own set of tables — it's always read/written as one
    # unit alongside the rest of a job's result, never queried into on
    # its own, so normalizing it further would add joins without benefit.
    table_diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 6: populated only when both documents are PDFs — a list of
    # {"page": int, "similarity": float, "diff_image_key": str}. Same
    # "always read as one unit" reasoning as table_diff above.
    visual_diff: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Phase 7: paragraph-level semantic comparison — populated whenever
    # both documents have any extractable text (which is almost always).
    # Same JSON-blob reasoning as table_diff/visual_diff.
    semantic_diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Formatting comparison: font/size/bold/italic/underline/color, DOCX
    # and PDF only — populated when both documents are one of those two
    # formats (independently; a DOCX vs PDF comparison still works).
    formatting_diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    job: Mapped[ComparisonJob] = relationship(back_populates="result")
