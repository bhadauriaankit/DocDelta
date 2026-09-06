import io

import fitz
import pytest
from PIL import Image, ImageDraw

from app.parsers.detection import detect_format
from app.parsers.errors import DocumentParseError
from app.parsers.image_parser import parse_image
from app.parsers.pdf_parser import parse_pdf


def _make_text_image(text: str, size=(600, 150)) -> bytes:
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 50), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_detects_real_png():
    raw = _make_text_image("hello")
    assert detect_format("scan.png", raw) == "image"


def test_rejects_fake_png():
    with pytest.raises(DocumentParseError, match="doesn't look like a real PNG"):
        detect_format("scan.png", b"not a real png")


def test_detects_real_jpeg():
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    assert detect_format("photo.jpg", buf.getvalue()) == "image"


def test_parse_image_extracts_text_via_ocr():
    raw = _make_text_image("INVOICE TOTAL 4500")
    text, warnings = parse_image(raw, "invoice.png")

    # Real OCR on a real rendered image — don't assert exact output
    # (font rendering makes OCR imperfect even on clean synthetic text,
    # confirmed while building this), just that it found *something*
    # recognizable.
    assert "INVOICE" in text.upper() or "TOTAL" in text.upper()
    assert any("OCR" in w for w in warnings)


def test_parse_image_warns_on_blank_image():
    blank = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    blank.save(buf, format="PNG")
    text, warnings = parse_image(buf.getvalue(), "blank.png")
    assert len(warnings) == 2  # the standard OCR-accuracy note + "found little text"


def test_parse_image_rejects_corrupted_file():
    with pytest.raises(DocumentParseError, match="couldn't be opened as an image"):
        parse_image(b"not a real image at all", "broken.png")


def _make_scanned_pdf_bytes(text: str) -> bytes:
    """Build a PDF with NO real text layer — just an image of text
    embedded on the page, simulating a scanned document."""
    image_bytes = _make_text_image(text, size=(800, 200))
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(0, 0, 400, 100), stream=image_bytes)
    raw = doc.tobytes()
    doc.close()
    return raw


def test_parse_pdf_ocrs_a_scanned_document():
    raw = _make_scanned_pdf_bytes("PROJECT DEADLINE AUGUST")
    text, warnings = parse_pdf(raw, "scanned.pdf")

    assert len(text.strip()) > 0
    assert any("OCR" in w for w in warnings)


def test_parse_pdf_with_real_text_layer_does_not_trigger_ocr():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This PDF has a real text layer, not a scan.")
    raw = doc.tobytes()
    doc.close()

    text, warnings = parse_pdf(raw, "normal.pdf")
    assert "real text layer" in text
    assert not any("OCR" in w for w in warnings)
