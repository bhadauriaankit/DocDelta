"""
Row-level diffing for spreadsheet-like data (XLSX sheets, CSV files,
tables found inside PPTX slides).

The approach: treat each row as one "token" and run the same
difflib.SequenceMatcher LCS-style algorithm the Phase 1 text diff engine
uses on words — just one level up, on rows instead of characters/words.
This gets pure insertions, deletions, and appends right essentially for
free, since that's exactly what SequenceMatcher is good at.

What it does NOT do: detect that "row 3 moved to row 40" as a single
"moved" operation. A row that's been relocated will show up as one
removal + one (probably-matched-as-"replace") insertion elsewhere,
depending on what else changed around it. Real move-detection needs a
similarity-scored bipartite matching between all rows (compare every
original row against every modified row, not just nearby ones) — that's
a meaningfully harder and slower algorithm, and a good candidate for a
future improvement, not a Phase 5 requirement. Documenting the boundary
here rather than pretending this handles reordering perfectly.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from app.parsers.models import TableData

_ROW_SEPARATOR = "\x1f"  # unit separator — vanishingly unlikely to appear in real cell data


@dataclass
class CellChange:
    row: int  # index into the *original* table's rows
    col: int
    original: str
    modified: str


@dataclass
class TableRowDiff:
    type: str  # "equal" | "added" | "removed" | "modified"
    original: list[str] | None = None
    modified: list[str] | None = None
    cell_changes: list[CellChange] = field(default_factory=list)


@dataclass
class TableDiff:
    name: str
    stats: dict[str, int]
    rows: list[TableRowDiff]


@dataclass
class SpreadsheetDiff:
    tables: list[TableDiff]
    added_tables: list[str]  # sheet/table names only present in the modified doc
    removed_tables: list[str]  # sheet/table names only present in the original doc


def _row_key(row: list[str]) -> str:
    return _ROW_SEPARATOR.join(row)


def _diff_cells(row_index: int, original: list[str], modified: list[str]) -> list[CellChange]:
    """Cell-by-cell comparison for a pair of rows matched as "this row
    became that row". Handles rows of different lengths (e.g. a column
    added mid-sheet shifts everything after it) by padding the shorter
    row with empty cells rather than crashing."""
    width = max(len(original), len(modified))
    changes = []
    for col in range(width):
        o = original[col] if col < len(original) else ""
        m = modified[col] if col < len(modified) else ""
        if o != m:
            changes.append(CellChange(row=row_index, col=col, original=o, modified=m))
    return changes


def _diff_rows(original_rows: list[list[str]], modified_rows: list[list[str]]) -> tuple[list[TableRowDiff], dict[str, int]]:
    matcher = difflib.SequenceMatcher(
        a=[_row_key(r) for r in original_rows],
        b=[_row_key(r) for r in modified_rows],
        autojunk=False,
    )

    row_diffs: list[TableRowDiff] = []
    stats = {"added": 0, "removed": 0, "modified": 0, "equal": 0}

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for oi in range(i1, i2):
                row_diffs.append(TableRowDiff(type="equal", original=original_rows[oi], modified=original_rows[oi]))
                stats["equal"] += 1

        elif tag == "delete":
            for oi in range(i1, i2):
                row_diffs.append(TableRowDiff(type="removed", original=original_rows[oi]))
                stats["removed"] += 1

        elif tag == "insert":
            for mj in range(j1, j2):
                row_diffs.append(TableRowDiff(type="added", modified=modified_rows[mj]))
                stats["added"] += 1

        elif tag == "replace":
            # A block of rows changed on both sides but SequenceMatcher
            # couldn't line any of them up as "equal" — pair them off
            # positionally (1st-with-1st, 2nd-with-2nd, ...) and diff
            # cells within each pair. Leftover rows on the longer side
            # are genuinely added/removed, not modifications of anything.
            o_count, m_count = i2 - i1, j2 - j1
            paired = min(o_count, m_count)

            for k in range(paired):
                o_row = original_rows[i1 + k]
                m_row = modified_rows[j1 + k]
                row_diffs.append(
                    TableRowDiff(
                        type="modified",
                        original=o_row,
                        modified=m_row,
                        cell_changes=_diff_cells(i1 + k, o_row, m_row),
                    )
                )
                stats["modified"] += 1

            for oi in range(i1 + paired, i2):
                row_diffs.append(TableRowDiff(type="removed", original=original_rows[oi]))
                stats["removed"] += 1
            for mj in range(j1 + paired, j2):
                row_diffs.append(TableRowDiff(type="added", modified=modified_rows[mj]))
                stats["added"] += 1

    return row_diffs, stats


def compare_tables(original_tables: list[TableData], modified_tables: list[TableData]) -> SpreadsheetDiff:
    """Match tables (sheets) by name, then row-diff each matched pair.

    Matching by name rather than by position means reordering *sheets*
    (not rows) is handled correctly — "Q1" is still compared against
    "Q1" even if it moved from the first tab to the third. A sheet
    renamed between versions won't be matched at all and will show up as
    one removed + one added table; teaching the matcher to recognize
    "this is probably the same sheet, just renamed" would need content-
    similarity matching similar to the row-move-detection gap above.
    """
    original_by_name = {t.name: t for t in original_tables}
    modified_by_name = {t.name: t for t in modified_tables}

    common_names = [t.name for t in original_tables if t.name in modified_by_name]
    removed_tables = [name for name in original_by_name if name not in modified_by_name]
    added_tables = [name for name in modified_by_name if name not in original_by_name]

    tables: list[TableDiff] = []
    for name in common_names:
        rows, stats = _diff_rows(original_by_name[name].rows, modified_by_name[name].rows)
        tables.append(TableDiff(name=name, rows=rows, stats=stats))

    return SpreadsheetDiff(tables=tables, added_tables=added_tables, removed_tables=removed_tables)
