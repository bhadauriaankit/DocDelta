import pytest

from app.parsers.detection import detect_format
from app.parsers.errors import DocumentParseError


def test_detects_plain_text():
    assert detect_format("notes.txt", b"hello world") == "text"


def test_detects_markdown_as_text():
    assert detect_format("notes.md", b"# hello") == "text"


def test_detects_real_pdf():
    assert detect_format("file.pdf", b"%PDF-1.7\n...") == "pdf"


def test_rejects_fake_pdf():
    with pytest.raises(DocumentParseError, match="don't look like a real PDF"):
        detect_format("file.pdf", b"this is not actually a pdf")


def test_rejects_unsupported_extension():
    with pytest.raises(DocumentParseError, match="isn't a supported file type"):
        detect_format("file.exe", b"MZ\x90\x00")


def test_rejects_non_utf8_text_file():
    with pytest.raises(DocumentParseError, match="UTF-8"):
        detect_format("file.txt", b"\xff\xfe\x00bad")


def test_rejects_fake_docx_that_is_just_a_zip():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("not_word.txt", "hi")

    with pytest.raises(DocumentParseError, match="doesn't look like a real Word document"):
        detect_format("file.docx", buf.getvalue())


def test_detects_real_xlsx():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")

    assert detect_format("file.xlsx", buf.getvalue()) == "xlsx"


def test_rejects_fake_xlsx_that_is_just_a_zip():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("not_excel.txt", "hi")

    with pytest.raises(DocumentParseError, match="doesn't look like a real Excel file"):
        detect_format("file.xlsx", buf.getvalue())


def test_detects_real_pptx():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ppt/presentation.xml", "<presentation/>")

    assert detect_format("file.pptx", buf.getvalue()) == "pptx"


def test_rejects_fake_pptx_that_is_just_a_zip():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("not_powerpoint.txt", "hi")

    with pytest.raises(DocumentParseError, match="doesn't look like a real PowerPoint file"):
        detect_format("file.pptx", buf.getvalue())


def test_detects_csv():
    assert detect_format("data.csv", b"a,b,c\n1,2,3") == "csv"


def test_rejects_non_utf8_csv():
    with pytest.raises(DocumentParseError, match="UTF-8"):
        detect_format("data.csv", b"\xff\xfe\x00bad")
