from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path

from crawler_app.base import BaseCrawler, CrawlResult, utc_now
from crawler_app.discovery import discover_crawlers
from crawler_app.logging_utils import configure_logger, log_result


@dataclass(slots=True)
class RunSummary:
    run_id: str
    total: int
    succeeded: int
    failed: int
    results: list[CrawlResult]


class CrawlerOrchestrator:
    def __init__(self, log_dir: str | Path = "logs", config_path: str | Path | None = None) -> None:
        self.log_dir = Path(log_dir)
        self.config_path = Path(config_path) if config_path else None
        self.logger = configure_logger(self.log_dir)

    def load_crawlers(self) -> list[BaseCrawler]:
        crawlers = discover_crawlers()
        if self.config_path is not None:
            for crawler in crawlers:
                set_config_path = getattr(crawler, "set_config_path", None)
                if callable(set_config_path):
                    set_config_path(self.config_path)
        return crawlers

    def run(self, crawler_names: list[str] | None = None) -> RunSummary:
        run_started_at = utc_now()
        run_id = run_started_at.strftime("%Y%m%dT%H%M%SZ")
        crawlers = self.load_crawlers()

        if crawler_names:
            allowed = set(crawler_names)
            crawlers = [crawler for crawler in crawlers if crawler.name in allowed]

        self.logger.info("Run started | run_id=%s | crawlers=%s", run_id, [c.name for c in crawlers])

        results: list[CrawlResult] = []
        for crawler in crawlers:
            result = self._run_single(crawler)
            results.append(result)
            log_result(self.log_dir, result)

        succeeded = sum(1 for result in results if result.success)
        failed = len(results) - succeeded

        self.logger.info(
            "Run finished | run_id=%s | total=%s | succeeded=%s | failed=%s",
            run_id,
            len(results),
            succeeded,
            failed,
        )
        return RunSummary(
            run_id=run_id,
            total=len(results),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    def _run_single(self, crawler: BaseCrawler) -> CrawlResult:
        started_at = utc_now()
        self.logger.info("Crawler started | name=%s", crawler.name)

        try:
            result = crawler.crawl()
            self.logger.info(
                "Crawler finished | name=%s | success=%s | items=%s | duration=%.2fs",
                crawler.name,
                result.success,
                result.items_count,
                result.duration_seconds,
            )
            return result
        except Exception as exc:
            finished_at = utc_now()
            error_message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.logger.exception("Crawler failed | name=%s", crawler.name)
            return CrawlResult(
                crawler_name=crawler.name,
                success=False,
                started_at=started_at,
                finished_at=finished_at,
                message="Crawler execution failed.",
                error=error_message,
                metadata={"traceback": traceback.format_exc()},
            )
