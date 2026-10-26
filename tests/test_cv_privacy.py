import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from io import BytesIO
from unittest.mock import patch

from pypdf import PdfWriter
import pytest

from job_scout.cv_privacy import (
    CVProcessingError,
    MAX_CV_PAGES,
    MAX_CV_TEXT_CHARS,
    MAX_CV_UPLOAD_BYTES,
    extract_pdf_text,
)


class FakePage:
    def __init__(self, value):
        self.value = value

    def extract_text(self):
        return self.value


class FakeReader:
    def __init__(self, pages, encrypted=False):
        self.pages = pages
        self.is_encrypted = encrypted


def test_oversized_pdf_is_rejected_before_parsing():
    payload = b"%PDF-" + b"x" * MAX_CV_UPLOAD_BYTES
    with patch("job_scout.cv_privacy.PdfReader") as parser:
        with pytest.raises(CVProcessingError, match="5 MB"):
            extract_pdf_text(payload)
        parser.assert_not_called()


def test_encrypted_pdf_is_rejected_without_attempting_extraction():
    with patch(
        "job_scout.cv_privacy.PdfReader",
        return_value=FakeReader([FakePage("private CV")], encrypted=True),
    ):
        with pytest.raises(CVProcessingError, match="contraseña"):
            extract_pdf_text(b"%PDF-synthetic")


def test_pdf_with_too_many_pages_is_rejected():
    pages = [FakePage("page") for _ in range(MAX_CV_PAGES + 1)]
    with patch("job_scout.cv_privacy.PdfReader", return_value=FakeReader(pages)):
        with pytest.raises(CVProcessingError, match="páginas"):
            extract_pdf_text(b"%PDF-synthetic")


def test_text_extraction_is_capped():
    with patch(
        "job_scout.cv_privacy.PdfReader",
        return_value=FakeReader([FakePage("A" * (MAX_CV_TEXT_CHARS + 1))]),
    ):
        result = extract_pdf_text(b"%PDF-synthetic")
    assert len(result.text) == MAX_CV_TEXT_CHARS
    assert result.truncated is True


def test_empty_text_pdf_fails_with_safe_message():
    with patch(
        "job_scout.cv_privacy.PdfReader",
        return_value=FakeReader([FakePage("   ")]),
    ):
        with pytest.raises(CVProcessingError, match="extraer texto"):
            extract_pdf_text(b"%PDF-synthetic")


def test_malformed_pdf_does_not_echo_parser_exception():
    with patch("job_scout.cv_privacy.PdfReader", side_effect=RuntimeError("private payload")):
        with pytest.raises(CVProcessingError) as exc:
            extract_pdf_text(b"%PDF-synthetic")
    assert "private payload" not in str(exc.value)


def test_real_encrypted_pdf_is_rejected():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    writer.write(output)
    with pytest.raises(CVProcessingError, match="contraseña"):
        extract_pdf_text(output.getvalue())


def test_real_too_many_page_pdf_is_rejected():
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(MAX_CV_PAGES + 1):
        writer.add_blank_page(width=100, height=100)
    writer.write(output)
    with pytest.raises(CVProcessingError, match="páginas"):
        extract_pdf_text(output.getvalue())
