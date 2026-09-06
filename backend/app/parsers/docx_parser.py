from __future__ import annotations

import io
import zipfile

import docx
from docx.opc.exceptions import PackageNotFoundError

from app.parsers.errors import DocumentParseError


def parse_docx(raw: bytes, filename: str = "document") -> str:
    """Extract paragraph text from a .docx file.

    Phase 3 scope: paragraph text only, in document order, including text
    inside table cells (tables are common enough — think a table of
    contents or a summary table — that skipping them entirely would lose
    obviously-relevant content). Table *structure* comparison (added/
    removed rows, cell-level diffing) is Phase 5's job, not this one's.
    """
    try:
        document = docx.Document(io.BytesIO(raw))
    except (PackageNotFoundError, zipfile.BadZipFile) as exc:
        # python-docx raises BadZipFile directly (not its own
        # PackageNotFoundError) for input that isn't a zip at all — only
        # zip files that are structurally valid but missing the expected
        # parts get PackageNotFoundError. Catching both covers "not a
        # docx" regardless of which layer notices first.
        raise DocumentParseError(
            f"'{filename}' couldn't be opened as a Word document. It may be corrupted "
            "or password protected."
        ) from exc

    parts: list[str] = []

    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))

    return "\n".join(parts)
