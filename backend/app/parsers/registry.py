from __future__ import annotations

from app.parsers.csv_parser import parse_csv
from app.parsers.detection import detect_format
from app.parsers.docx_parser import parse_docx
from app.parsers.image_parser import parse_image
from app.parsers.models import ExtractedDocument
from app.parsers.pdf_parser import parse_pdf
from app.parsers.pptx_parser import parse_pptx
from app.parsers.text_parser import parse_text
from app.parsers.xlsx_parser import parse_xlsx


def extract_text(filename: str, raw: bytes) -> ExtractedDocument:
    """Detect the format and return a normalized ExtractedDocument.

    This is the one function the API layer calls — it doesn't need to know
    which parser handled the file. Adding a new format means adding one
    branch here plus one new parser module; nothing above this layer
    changes. Phase 5 added xlsx/csv/pptx this way without touching
    anything in app/tasks.py or app/main.py beyond what table-diffing
    itself required.
    """
    fmt = detect_format(filename, raw)

    if fmt == "text":
        return ExtractedDocument(text=parse_text(raw), format="text")

    if fmt == "docx":
        return ExtractedDocument(text=parse_docx(raw, filename), format="docx")

    if fmt == "pdf":
        text, warnings = parse_pdf(raw, filename)
        return ExtractedDocument(text=text, format="pdf", warnings=warnings)

    if fmt == "xlsx":
        text, tables, warnings = parse_xlsx(raw, filename)
        return ExtractedDocument(text=text, format="xlsx", tables=tables, warnings=warnings)

    if fmt == "csv":
        text, tables, warnings = parse_csv(raw, filename)
        return ExtractedDocument(text=text, format="csv", tables=tables, warnings=warnings)

    if fmt == "pptx":
        text, tables, warnings = parse_pptx(raw, filename)
        return ExtractedDocument(text=text, format="pptx", tables=tables, warnings=warnings)

    if fmt == "image":
        text, warnings = parse_image(raw, filename)
        return ExtractedDocument(text=text, format="image", warnings=warnings)

    # detect_format only ever returns one of the above — this is a safety
    # net in case a new format gets added to detection.py without a
    # matching branch here.
    raise AssertionError(f"Unhandled format '{fmt}' — add a branch in registry.py")
