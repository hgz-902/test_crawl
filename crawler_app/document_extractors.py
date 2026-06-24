from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
import importlib
import xml.etree.ElementTree as ET
import zipfile


SupportedFileType = Literal["pdf", "hwpx"]


# document extract 결과 정보를 담는 데이터 객체다.
@dataclass(slots=True)
class DocumentExtractResult:
    source_path: str | None
    source_url: str | None
    file_name: str | None
    file_type: SupportedFileType | str
    success: bool
    text: str = ""
    text_length: int = 0
    page_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    # 객체 상태를 JSON 직렬화 가능한 dict로 변환한다.
    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_url": self.source_url,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "success": self.success,
            "text": self.text,
            "text_length": self.text_length,
            "page_count": self.page_count,
            "metadata": self.metadata,
            "error": self.error,
        }


# 텍스트 파일을 추출한다.
def extract_text_from_file(path: str | Path) -> DocumentExtractResult:
    file_path = Path(path)
    file_type = _detect_file_type(file_path.suffix, file_path.name)

    if file_type is None:
        return _failure_result(
            file_type=file_path.suffix.lower().lstrip(".") or "unknown",
            file_name=file_path.name,
            source_path=str(file_path),
            error=f"Unsupported file type: {file_path.suffix or 'no extension'}",
        )

    try:
        file_bytes = file_path.read_bytes()
    except OSError as exc:
        return _failure_result(
            file_type=file_type,
            file_name=file_path.name,
            source_path=str(file_path),
            error=f"Failed to read file: {exc}",
        )

    return extract_text_from_bytes(
        file_bytes=file_bytes,
        file_type=file_type,
        file_name=file_path.name,
        source_path=str(file_path),
    )


# 텍스트 bytes를 추출한다.
def extract_text_from_bytes(
    file_bytes: bytes,
    file_type: str,
    file_name: str | None = None,
    source_url: str | None = None,
    source_path: str | None = None,
) -> DocumentExtractResult:
    normalized = file_type.lower().lstrip(".")

    if normalized == "pdf":
        return _extract_pdf_text(
            file_bytes=file_bytes,
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
        )
    if normalized == "hwpx":
        return _extract_hwpx_text(
            file_bytes=file_bytes,
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
        )

    return _failure_result(
        file_type=normalized or "unknown",
        file_name=file_name,
        source_url=source_url,
        source_path=source_path,
        error=f"Unsupported file type: {file_type}",
    )


# pdf 텍스트를 추출한다.
def _extract_pdf_text(
    file_bytes: bytes,
    file_name: str | None,
    source_url: str | None,
    source_path: str | None,
) -> DocumentExtractResult:
    try:
        pypdf = importlib.import_module("pypdf")
    except ModuleNotFoundError:
        return _failure_result(
            file_type="pdf",
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
            error="pypdf is not installed. Install dependencies from requirements.txt.",
        )

    try:
        reader = pypdf.PdfReader(BytesIO(file_bytes))
        page_texts: list[str] = []
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                page_texts.append(text)

        if not page_texts:
            return _failure_result(
                file_type="pdf",
                file_name=file_name,
                source_url=source_url,
                source_path=source_path,
                error="No extractable text found in PDF.",
                metadata={"page_count": len(reader.pages)},
            )

        merged_text = "\n\n".join(page_texts).strip()
        return DocumentExtractResult(
            source_path=source_path,
            source_url=source_url,
            file_name=file_name,
            file_type="pdf",
            success=True,
            text=merged_text,
            text_length=len(merged_text),
            page_count=len(reader.pages),
            metadata={"extractor": "pypdf"},
        )
    except Exception as exc:
        return _failure_result(
            file_type="pdf",
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
            error=f"Failed to extract PDF text: {exc}",
        )


# hwpx 텍스트를 추출한다.
def _extract_hwpx_text(
    file_bytes: bytes,
    file_name: str | None,
    source_url: str | None,
    source_path: str | None,
) -> DocumentExtractResult:
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            xml_members = [
                name for name in zf.namelist()
                if name.lower().endswith(".xml") and "contents" in name.lower()
            ]
            if not xml_members:
                xml_members = [
                    name for name in zf.namelist()
                    if name.lower().endswith(".xml") and "section" in name.lower()
                ]
            if not xml_members:
                return _failure_result(
                    file_type="hwpx",
                    file_name=file_name,
                    source_url=source_url,
                    source_path=source_path,
                    error="No HWPX content XML found.",
                )

            xml_members.sort()
            paragraphs: list[str] = []
            for member in xml_members:
                xml_bytes = zf.read(member)
                paragraphs.extend(_extract_hwpx_paragraphs(xml_bytes))

            cleaned = "\n".join(part for part in paragraphs if part).strip()
            if not cleaned:
                return _failure_result(
                    file_type="hwpx",
                    file_name=file_name,
                    source_url=source_url,
                    source_path=source_path,
                    error="No extractable text found in HWPX.",
                    metadata={"content_files": xml_members},
                )

            return DocumentExtractResult(
                source_path=source_path,
                source_url=source_url,
                file_name=file_name,
                file_type="hwpx",
                success=True,
                text=cleaned,
                text_length=len(cleaned),
                page_count=None,
                metadata={"content_files": xml_members},
            )
    except zipfile.BadZipFile:
        return _failure_result(
            file_type="hwpx",
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
            error="Invalid HWPX file: not a valid ZIP archive.",
        )
    except ET.ParseError as exc:
        return _failure_result(
            file_type="hwpx",
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
            error=f"Failed to parse HWPX XML: {exc}",
        )
    except Exception as exc:
        return _failure_result(
            file_type="hwpx",
            file_name=file_name,
            source_url=source_url,
            source_path=source_path,
            error=f"Failed to extract HWPX text: {exc}",
        )


# hwpx paragraphs를 추출한다.
def _extract_hwpx_paragraphs(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []

    for element in root.iter():
        if _local_name(element.tag) != "p":
            continue

        chunks: list[str] = []
        for node in element.iter():
            if node.text:
                text = node.text.strip()
                if text:
                    chunks.append(text)

        paragraph = " ".join(chunks).strip()
        if paragraph:
            paragraphs.append(paragraph)

    return paragraphs


# XML/HTML tag의 local name을 반환한다.
def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


# detect 파일 type 값을 계산해 반환한다.
def _detect_file_type(suffix: str, file_name: str | None) -> SupportedFileType | None:
    normalized = suffix.lower().lstrip(".")
    if normalized in {"pdf", "hwpx"}:
        return normalized

    if file_name:
        lower_name = file_name.lower()
        if lower_name.endswith(".pdf"):
            return "pdf"
        if lower_name.endswith(".hwpx"):
            return "hwpx"

    return None


# failure 결과 값을 계산해 반환한다.
def _failure_result(
    file_type: str,
    error: str,
    file_name: str | None = None,
    source_url: str | None = None,
    source_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DocumentExtractResult:
    return DocumentExtractResult(
        source_path=source_path,
        source_url=source_url,
        file_name=file_name,
        file_type=file_type,
        success=False,
        text="",
        text_length=0,
        page_count=None,
        metadata=metadata or {},
        error=error,
    )
