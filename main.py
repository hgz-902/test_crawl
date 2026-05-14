from __future__ import annotations

import argparse
import json

from crawler_app.orchestrator import CrawlerOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run registered crawlers and log their results.",
    )
    parser.add_argument(
        "--crawler",
        action="append",
        dest="crawlers",
        help="Crawler name to run. Repeat this option to run multiple crawlers.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory where orchestrator logs and JSONL result logs are stored.",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        help="JSON config path for the configurable crawler.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    orchestrator = CrawlerOrchestrator(log_dir=args.log_dir, config_path=args.config_path)
    summary = orchestrator.run(crawler_names=args.crawlers)
    print(json.dumps(_summary_for_cli(summary), ensure_ascii=False, indent=2, default=str))


def _summary_for_cli(summary) -> dict:
    return {
        "run_id": summary.run_id,
        "total": summary.total,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
        "results": [
            {
                "crawler_name": result.crawler_name,
                "success": result.success,
                "started_at": result.started_at.isoformat(),
                "finished_at": result.finished_at.isoformat(),
                "duration_seconds": result.duration_seconds,
                "items_count": result.items_count,
                "message": result.message,
                "error": result.error,
                "metadata": result.metadata,
            }
            for result in summary.results
        ],
    }


if __name__ == "__main__":
    main()
