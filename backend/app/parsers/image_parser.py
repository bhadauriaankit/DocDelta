from __future__ import annotations

import io

import pytesseract
from PIL import Image

from app.parsers.errors import DocumentParseError

MIN_MEANINGFUL_CHARS = 3


def parse_image(raw: bytes, filename: str = "document") -> tuple[str, list[str]]:
    """OCR a standalone image file (PNG/JPEG).

    Unlike PDFs — which usually have a real text layer and only fall back
    to OCR when they look scanned (see pdf_parser.py) — a bare image never
    has an embedded text layer at all. Every image goes through OCR,
    always, so the accuracy-warning is unconditional here rather than
    only appearing on the "looks scanned" path.
    """
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()  # force full decode now — a truncated file fails here with a clear message, not lazily later
    except Exception as exc:
        raise DocumentParseError(f"'{filename}' couldn't be opened as an image. It may be corrupted.") from exc

    text = pytesseract.image_to_string(image)

    warnings = [
        f"Text in '{filename}' was extracted using OCR — accuracy may be lower than a document "
        "with real embedded text, especially for stylized fonts, handwriting, or low-resolution images."
    ]
    if len(text.strip()) < MIN_MEANINGFUL_CHARS:
        warnings.append(f"OCR found little to no readable text in '{filename}'.")

    return text, warnings
