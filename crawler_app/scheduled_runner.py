from __future__ import annotations

import argparse
import json

from crawler_app.orchestration import OrchestrationStateStore, batch_to_dict, run_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run saved orchestration jobs from Windows Task Scheduler.")
    parser.add_argument("--job-id", action="append", dest="job_ids")
    parser.add_argument("--allow-email-send", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = OrchestrationStateStore()
    settings = store.load_settings()
    selected = args.job_ids or [
        job_id
        for job_id, job_settings in (settings.get("jobs") or {}).items()
        if isinstance(job_settings, dict) and job_settings.get("enabled")
    ]
    batch = run_batch(
        selected,
        store=store,
        force_due=True,
        allow_email_send=args.allow_email_send,
        parallel=True,
    )
    print(json.dumps(batch_to_dict(batch), ensure_ascii=False, indent=2))
    return 1 if batch.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
