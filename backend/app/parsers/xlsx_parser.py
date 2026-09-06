from __future__ import annotations

import io

import openpyxl

from app.parsers.errors import DocumentParseError
from app.parsers.models import TableData


def parse_xlsx(raw: bytes, filename: str = "document") -> tuple[str, list[TableData], list[str]]:
    """Extract every sheet as a TableData, plus a flattened text view for
    the word-level diff / cross-format comparisons.

    `data_only=False` keeps formulas as formula text (e.g. "=SUM(A1:A5)")
    rather than resolving to a value — a formula changing is exactly the
    kind of difference this tool should catch, and comparing formula text
    directly diffs it like any other text change, no special-casing
    needed. The tradeoff: if a cell's *computed result* changes because
    an upstream cell changed, but the formula itself is untouched, that
    won't show up as a difference. That's a reasonable line for this
    phase — real "recalculate and compare results" support would need an
    actual formula engine.

    Every cell value is stringified — see TableData's docstring for why.
    """
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw), data_only=False, read_only=True)
    except Exception as exc:
        # openpyxl's exception types for "not a real xlsx" have shifted
        # across versions (BadZipFile for non-zip input, KeyError for a
        # zip missing expected parts, InvalidFileException for others) —
        # catching broadly and converting to one friendly message avoided
        # a real bug in Phase 3 (see docx/pdf parsers) and does the same
        # job here.
        raise DocumentParseError(
            f"'{filename}' couldn't be opened as an Excel file. It may be corrupted or password protected."
        ) from exc

    tables: list[TableData] = []
    text_parts: list[str] = []

    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        rows: list[list[str]] = []
        for row in sheet.iter_rows(values_only=True):
            str_row = ["" if cell is None else str(cell) for cell in row]
            if any(cell for cell in str_row):  # skip fully-blank trailing rows
                rows.append(str_row)

        tables.append(TableData(name=sheet_name, rows=rows))
        for row in rows:
            text_parts.append(f"{sheet_name}: " + " | ".join(row))

    workbook.close()

    warnings: list[str] = []
    if not tables or all(not t.rows for t in tables):
        warnings.append(f"'{filename}' doesn't seem to have any data in it.")

    return "\n".join(text_parts), tables, warnings
