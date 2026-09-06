from __future__ import annotations

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.parsers.errors import DocumentParseError

# Below this many non-whitespace characters, treat the PDF as "probably
# scanned" and fall back to OCR instead of giving up.
MIN_MEANINGFUL_CHARS = 20

OCR_RENDER_DPI = 200  # good balance of OCR accuracy vs. rendering time/memory
MAX_OCR_PAGES = 20  # cap OCR cost for very long scanned documents


def _ocr_page(page: fitz.Page) -> str:
    zoom = OCR_RENDER_DPI / 72  # PDF page coordinates are in points, 72 per inch
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(image)


def parse_pdf(raw: bytes, filename: str = "document") -> tuple[str, list[str]]:
    """Extract text from a PDF, page by page.

    Returns (text, warnings). A password-protected PDF raises a friendly
    DocumentParseError. A PDF that opens fine but yields almost no text
    from its text layer is very likely a scanned image — Phase 3 just
    warned about this; Phase 6 now actually OCRs it (Tesseract, via
    pytesseract) so the comparison has real text to work with instead of
    diffing two near-empty strings.
    """
    try:
        document = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        # PyMuPDF's exact exception type for "this isn't a valid PDF" has
        # varied across versions (FileDataError in some, an internal
        # mupdf.FzErrorFormat in others) — catching broadly here and
        # converting to one friendly message is more robust than chasing
        # the library's internal exception hierarchy.
        raise DocumentParseError(
            f"'{filename}' couldn't be opened as a PDF. It may be corrupted."
        ) from exc

    if document.needs_pass:
        document.close()
        raise DocumentParseError(
            f"'{filename}' is password protected. Password-protected PDF support "
            "arrives in a later phase — for now, please upload an unlocked copy."
        )

    pages_text = [page.get_text() for page in document]
    text = "\n".join(pages_text)
    warnings: list[str] = []

    if len(text.strip()) < MIN_MEANINGFUL_CHARS:
        page_count = len(document)
        pages_to_ocr = min(page_count, MAX_OCR_PAGES)

        ocr_text = "\n".join(_ocr_page(document[i]) for i in range(pages_to_ocr))
        text = ocr_text

        warnings.append(
            f"'{filename}' had no usable embedded text layer and was processed with OCR "
            "instead — accuracy may be lower than a document with real embedded text, "
            "especially for stylized fonts or low-resolution scans."
        )
        if page_count > MAX_OCR_PAGES:
            warnings.append(
                f"'{filename}' has {page_count} pages; only the first {MAX_OCR_PAGES} were "
                "processed with OCR to keep this comparison reasonably fast."
            )
        if len(text.strip()) < MIN_MEANINGFUL_CHARS:
            warnings.append(f"OCR found little to no readable text in '{filename}'.")

    document.close()
    return text, warnings
