from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import ModuleType
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from crawler_app.document_extractors import extract_text_from_bytes, extract_text_from_file


class DocumentExtractorTests(unittest.TestCase):
    def test_extract_hwpx_text_from_bytes(self) -> None:
        hwpx_bytes = build_hwpx_bytes(
            [
                "첫 번째 문단입니다.",
                "두 번째 문단입니다.",
            ]
        )

        result = extract_text_from_bytes(hwpx_bytes, "hwpx", file_name="sample.hwpx")

        self.assertTrue(result.success)
        self.assertIn("첫 번째 문단입니다.", result.text)
        self.assertIn("두 번째 문단입니다.", result.text)
        self.assertEqual(result.file_type, "hwpx")
        self.assertGreater(result.text_length, 0)

    def test_extract_hwpx_text_from_file(self) -> None:
        hwpx_bytes = build_hwpx_bytes(["파일 기반 추출 테스트"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.hwpx"
            file_path.write_bytes(hwpx_bytes)

            result = extract_text_from_file(file_path)

        self.assertTrue(result.success)
        self.assertEqual(result.source_path, str(file_path))
        self.assertIn("파일 기반 추출 테스트", result.text)

    def test_extract_pdf_returns_dependency_error_when_pypdf_missing(self) -> None:
        with patch("crawler_app.document_extractors.importlib.import_module", side_effect=ModuleNotFoundError("pypdf")):
            result = extract_text_from_bytes(b"%PDF-1.4", "pdf", file_name="sample.pdf")

        self.assertFalse(result.success)
        self.assertIn("pypdf is not installed", result.error or "")

    def test_extract_pdf_text_with_stub_pypdf(self) -> None:
        fake_module = ModuleType("pypdf")

        class FakePage:
            def __init__(self, text: str) -> None:
                self._text = text

            def extract_text(self) -> str:
                return self._text

        class FakeReader:
            def __init__(self, _: BytesIO) -> None:
                self.pages = [FakePage("page 1"), FakePage("page 2")]

        fake_module.PdfReader = FakeReader
        original = sys.modules.get("pypdf")
        sys.modules["pypdf"] = fake_module
        try:
            result = extract_text_from_bytes(b"fake pdf bytes", "pdf", file_name="sample.pdf")
        finally:
            if original is not None:
                sys.modules["pypdf"] = original
            else:
                sys.modules.pop("pypdf", None)

        self.assertTrue(result.success)
        self.assertEqual(result.page_count, 2)
        self.assertEqual(result.text, "page 1\n\npage 2")

    def test_unsupported_extension(self) -> None:
        result = extract_text_from_bytes(b"hello", "txt", file_name="sample.txt")

        self.assertFalse(result.success)
        self.assertIn("Unsupported file type", result.error or "")


def build_hwpx_bytes(paragraphs: list[str]) -> bytes:
    paragraph_xml = "".join(
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
        for text in paragraphs
    )
    contents = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<hp:section xmlns:hp=\"http://www.hancom.co.kr/hwpml/2011/paragraph\">"
        f"{paragraph_xml}"
        "</hp:section>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", contents)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
