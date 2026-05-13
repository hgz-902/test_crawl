"""Crawler application package."""

from dotenv import load_dotenv

load_dotenv()

from crawler_app.document_extractors import DocumentExtractResult, extract_text_from_bytes, extract_text_from_file

__all__ = [
    "DocumentExtractResult",
    "extract_text_from_bytes",
    "extract_text_from_file",
]
