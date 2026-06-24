from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# 현재 UTC 시간을 timezone-aware 값으로 반환한다.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# crawl 결과 정보를 담는 데이터 객체다.
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

    # 크롤 시작과 종료 시각 차이를 초 단위로 계산한다.
    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    # 객체 상태를 JSON 직렬화 가능한 dict로 변환한다.
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


# base 크롤러의 상태와 실행 동작을 관리한다.
class BaseCrawler(ABC):
    name: str

    # 현재 설정을 기준으로 크롤링을 실행하고 결과 객체를 반환한다.
    @abstractmethod
    def crawl(self) -> CrawlResult:
        """Execute crawling and return a normalized result."""

