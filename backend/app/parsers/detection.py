"""
Format detection.

Deliberately does NOT trust the file extension alone. A `.pdf` that isn't
actually a PDF, or a `.docx` that's actually a renamed `.zip`, should be
caught here with a clear error rather than crashing deep inside a parser
later (or worse, silently misparsing).

DOCX/XLSX/PPTX are all just zip files, so distinguishing between them
needs one extra step beyond "starts with PK\\x03\\x04" — we peek inside
the zip's file listing for a part that's unique to each format
(`word/document.xml`, `xl/workbook.xml`, `ppt/presentation.xml`).

CSV has no magic bytes at all — it's just text — so CSV detection is
extension + UTF-8-decodability only, same as .txt/.md. The real
correctness check for CSV happens in the parser (can it actually be
parsed as rows), not here.

PNG and JPEG do have real magic bytes (PNG's 8-byte signature, JPEG's
0xFFD8FF marker) and are checked the same way as PDF.
"""

from __future__ import annotations

import io
import zipfile

from app.parsers.errors import DocumentParseError

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".xlsx", ".csv", ".pptx", ".png", ".jpg", ".jpeg"}

_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _looks_like_pdf(raw: bytes) -> bool:
    return raw[:5] == _PDF_MAGIC


def _looks_like_png(raw: bytes) -> bool:
    return raw[:8] == _PNG_MAGIC


def _looks_like_jpeg(raw: bytes) -> bool:
    return raw[:3] == _JPEG_MAGIC


def _zip_contains(raw: bytes, part_name: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            return part_name in zf.namelist()
    except zipfile.BadZipFile:
        return False


def _looks_like_docx(raw: bytes) -> bool:
    return _zip_contains(raw, "word/document.xml")


def _looks_like_xlsx(raw: bytes) -> bool:
    return _zip_contains(raw, "xl/workbook.xml")


def _looks_like_pptx(raw: bytes) -> bool:
    return _zip_contains(raw, "ppt/presentation.xml")


def _looks_like_utf8_text(raw: bytes) -> bool:
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def detect_format(filename: str, raw: bytes) -> str:
    """Returns one of "text", "pdf", "docx", "xlsx", "csv", "pptx".
    Raises DocumentParseError with a user-facing message if the extension
    is unsupported or the content doesn't actually match what the
    extension claims."""

    name = (filename or "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""

    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            f"'{filename}' isn't a supported file type. "
            f"Supported so far: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    if ext == ".pdf":
        if not _looks_like_pdf(raw):
            raise DocumentParseError(
                f"'{filename}' has a .pdf extension, but its contents don't look like a real PDF. "
                "It may be corrupted or mislabeled."
            )
        return "pdf"

    if ext == ".docx":
        if not _looks_like_docx(raw):
            raise DocumentParseError(
                f"'{filename}' has a .docx extension, but doesn't look like a real Word document. "
                "It may be corrupted, mislabeled, or an older .doc file (not yet supported)."
            )
        return "docx"

    if ext == ".xlsx":
        if not _looks_like_xlsx(raw):
            raise DocumentParseError(
                f"'{filename}' has an .xlsx extension, but doesn't look like a real Excel file. "
                "It may be corrupted, mislabeled, or an older .xls file (not yet supported)."
            )
        return "xlsx"

    if ext == ".pptx":
        if not _looks_like_pptx(raw):
            raise DocumentParseError(
                f"'{filename}' has a .pptx extension, but doesn't look like a real PowerPoint file. "
                "It may be corrupted, mislabeled, or an older .ppt file (not yet supported)."
            )
        return "pptx"

    if ext == ".csv":
        if not _looks_like_utf8_text(raw):
            raise DocumentParseError(f"Could not read '{filename}' as UTF-8 text. Is this really a CSV file?")
        return "csv"

    if ext == ".png":
        if not _looks_like_png(raw):
            raise DocumentParseError(
                f"'{filename}' has a .png extension, but doesn't look like a real PNG image. "
                "It may be corrupted or mislabeled."
            )
        return "image"

    if ext in (".jpg", ".jpeg"):
        if not _looks_like_jpeg(raw):
            raise DocumentParseError(
                f"'{filename}' has a .{ext.lstrip('.')} extension, but doesn't look like a real JPEG image. "
                "It may be corrupted or mislabeled."
            )
        return "image"

    # .txt / .md
    if not _looks_like_utf8_text(raw):
        raise DocumentParseError(
            f"Could not read '{filename}' as UTF-8 text. Is this really a plain-text file?"
        )
    return "text"
