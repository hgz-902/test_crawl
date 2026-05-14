from __future__ import annotations

from pathlib import Path
import logging

from crawler_app.base import BaseCrawler, CrawlResult, utc_now
from crawler_app.workflow import load_workflow_config, run_workflow_config


class ConfigurableCrawler(BaseCrawler):
    name = "configurable"

    def __init__(
        self,
        config_path: str | Path | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else None
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logger or logging.getLogger("crawler_orchestrator")

    def set_config_path(self, config_path: str | Path | None) -> None:
        self.config_path = Path(config_path) if config_path else None

    def crawl(self) -> CrawlResult:
        started_at = utc_now()
        config_name: str | None = None
        output_dir: Path | None = None

        try:
            if self.config_path is None:
                raise ValueError("ConfigurableCrawler requires --config path.")

            config = load_workflow_config(self.config_path)
            config_name = str(config["name"])
            output_dir = Path(config["output_dir"])
            execution = run_workflow_config(config)
            for record in execution.records:
                for step in record.get("steps", []):
                    if step.get("success"):
                        self.logger.info(
                            "Workflow step succeeded | config=%s | record=%s | search_term=%s | item=%s | step=%s:%s | action=%s | wait_state=%s | matches=%s | duration=%ss | url_before=%s | url_after=%s",
                            config_name,
                            record.get("record_key"),
                            record.get("search_term"),
                            record.get("item_index"),
                            step.get("index"),
                            step.get("name"),
                            step.get("action"),
                            step.get("wait_state"),
                            step.get("matched_count"),
                            step.get("duration_seconds"),
                            step.get("url_before"),
                            step.get("url_after"),
                        )
                    else:
                        self.logger.error(
                            "Workflow step failed | config=%s | record=%s | search_term=%s | item=%s | step=%s:%s | action=%s | wait_state=%s | attr=%s | xpath=%s | wait_timeout_ms=%s | url_before=%s | error=%s",
                            config_name,
                            record.get("record_key"),
                            record.get("search_term"),
                            record.get("item_index"),
                            step.get("index"),
                            step.get("name"),
                            step.get("action"),
                            step.get("wait_state"),
                            step.get("attr"),
                            step.get("xpath"),
                            step.get("wait_timeout_ms"),
                            step.get("url_before"),
                            step.get("error"),
                        )

            return CrawlResult(
                crawler_name=self.name,
                success=execution.success,
                started_at=started_at,
                finished_at=utc_now(),
                items_count=len(execution.records),
                message="Workflow crawl completed." if execution.success else "Workflow crawl completed with errors.",
                data=execution.records,
                metadata={
                    "config_name": config_name,
                    "config_path": str(self.config_path),
                    "output_dir": str(execution.output_dir.resolve()),
                    "parser_name": execution.diagnostics.get("parser_name"),
                    "search_terms": execution.diagnostics.get("search_terms", []),
                    "filter_terms": execution.diagnostics.get("filter_terms", []),
                    "search_term_runs": execution.diagnostics.get("search_term_runs", []),
                    "downloaded_files": execution.downloaded_files,
                    "extracted_files": execution.extracted_files,
                    "matched_record_count": execution.diagnostics.get("matched_record_count"),
                    "nonfilter_record_count": execution.diagnostics.get("nonfilter_record_count"),
                    "matched_output_files": execution.diagnostics.get("matched_output_files", []),
                    "nonfilter_output_files": execution.diagnostics.get("nonfilter_output_files", []),
                    "matched_records_file": execution.diagnostics.get("matched_records_file"),
                    "manifest_file": execution.diagnostics.get("manifest_file"),
                    "nonfilter_records_file": execution.diagnostics.get("nonfilter_records_file"),
                    "diagnostics": execution.diagnostics,
                },
                error=execution.error,
            )
        except Exception as exc:
            return CrawlResult(
                crawler_name=self.name,
                success=False,
                started_at=started_at,
                finished_at=utc_now(),
                items_count=0,
                message="Workflow crawl failed.",
                data=[],
                metadata={
                    "config_name": config_name,
                    "config_path": str(self.config_path) if self.config_path else None,
                    "output_dir": str(output_dir.resolve()) if output_dir else None,
                },
                error=str(exc),
            )
