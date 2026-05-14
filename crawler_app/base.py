from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CrawlResult:
    crawler_name: str
    success: bool
    started_at: datetime
    finished_at: datetime
    items_count: int = 0
    message: str = ""
    data: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "crawler_name": self.crawler_name,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "items_count": self.items_count,
            "message": self.message,
            "metadata": self.metadata,
            "error": self.error,
            "data": self.data,
        }


class BaseCrawler(ABC):
    name: str

    @abstractmethod
    def crawl(self) -> CrawlResult:
        """Execute crawling and return a normalized result."""

