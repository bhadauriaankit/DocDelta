from dataclasses import dataclass, field


@dataclass
class TableData:
    """One sheet (XLSX), one CSV file, or one slide's table (PPTX).

    Rows are always list[str] — every cell gets stringified at parse
    time. This is deliberate: comparing "45000" (from a CSV) against
    45000.0 (from a spreadsheet library's float parsing) as if they were
    different types would produce false differences. Normalizing to
    strings once here means the diff algorithm never has to think about
    types at all.
    """

    name: str
    rows: list[list[str]]


@dataclass
class ExtractedDocument:
    """The common internal representation every parser normalizes into.

    `text` is always populated — a flattened representation used for the
    word-level diff and for comparing across formats (e.g. a CSV against
    a plain-text export of the same data). `tables` is only populated for
    spreadsheet-like formats (XLSX, CSV, and any tables found inside a
    PPTX) — Phase 5's row/column-aware diffing runs on this instead of
    the flattened text.
    """

    text: str
    format: str  # "text" | "pdf" | "docx" | "xlsx" | "csv" | "pptx"
    warnings: list[str] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
