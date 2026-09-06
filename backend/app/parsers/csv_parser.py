from __future__ import annotations

import csv
import io

from app.parsers.models import TableData


def parse_csv(raw: bytes, filename: str = "document") -> tuple[str, list[TableData], list[str]]:
    """Parse a CSV into a single TableData.

    Deliberately uses the stdlib `csv` module instead of pandas (which
    the original spec suggested). Pandas infers column dtypes — a column
    of "1", "2", "3" becomes int64, an empty cell becomes NaN — which is
    exactly the wrong behavior for exact-value diffing: it would silently
    turn "1" into 1.0 or an empty string into "nan" before comparison
    even starts, producing false differences that have nothing to do
    with the actual file contents. Reading everything as plain strings
    sidesteps that class of bug entirely. The tradeoff is losing pandas'
    delimiter/encoding auto-sniffing — this phase assumes comma-delimited,
    UTF-8 CSV, which covers the common case.

    detection.py already confirmed this decodes as UTF-8, so no need to
    re-guard that here.
    """
    text = raw.decode("utf-8")
    rows = [row for row in csv.reader(io.StringIO(text))]

    table = TableData(name="csv", rows=rows)
    flattened = "\n".join(" | ".join(row) for row in rows)

    warnings: list[str] = []
    if not rows:
        warnings.append(f"'{filename}' appears to be empty.")

    return flattened, [table], warnings
