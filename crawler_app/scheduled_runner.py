from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from crawler_app.orchestration import OrchestrationStateStore, batch_to_dict, cron_matches_datetime, run_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run saved orchestration jobs from Windows Task Scheduler.")
    parser.add_argument("--job-id", action="append", dest="job_ids")
    parser.add_argument("--allow-email-send", action="store_true")
    parser.add_argument("--cron-gate", action="store_true", help="Skip selected jobs unless their saved cron matches the current minute.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = OrchestrationStateStore()
    settings = store.load_settings()
    enabled_job_ids = [
        job_id
        for job_id, job_settings in (settings.get("jobs") or {}).items()
        if isinstance(job_settings, dict) and job_settings.get("enabled")
    ]
    if args.job_ids:
        enabled_set = set(enabled_job_ids)
        selected = [job_id for job_id in args.job_ids if job_id in enabled_set]
    else:
        selected = enabled_job_ids
    if args.cron_gate:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        selected = [
            job_id
            for job_id in selected
            if cron_matches_datetime((settings.get("jobs") or {}).get(job_id, {}).get("cron") or "", now)
        ]
    print(
        "SCHEDULED_RUN_START "
        + json.dumps(
            {
                "requested_job_ids": args.job_ids or [],
                "selected_job_ids": selected,
                "allow_email_send": bool(settings.get("allow_email_send", False)),
                "cron_gate": bool(args.cron_gate),
            },
            ensure_ascii=False,
        )
    )
    if args.cron_gate and not selected:
        print(
            "SCHEDULED_RUN_SKIPPED "
            + json.dumps({"reason": "cron_gate_not_due", "requested_job_ids": args.job_ids or []}, ensure_ascii=False)
        )
        return 0
    batch = run_batch(
        selected,
        store=store,
        force_due=True,
        allow_email_send=bool(settings.get("allow_email_send", False)),
        parallel=True,
    )
    payload = batch_to_dict(batch)
    print(
        "SCHEDULED_RUN_SUMMARY "
        + json.dumps(
            {
                "batch_id": payload.get("batch_id"),
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
                "status": payload.get("status"),
                "total": payload.get("total"),
                "succeeded": payload.get("succeeded"),
                "failed": payload.get("failed"),
                "duplicate_stopped": payload.get("duplicate_stopped"),
                "skipped_not_due": payload.get("skipped_not_due"),
                "results": [
                    {
                        "job_id": result.get("job_id"),
                        "config_name": result.get("config_name"),
                        "status": result.get("status"),
                        "items_count": result.get("items_count"),
                        "duplicate_stopped": result.get("duplicate_stopped"),
                        "error": result.get("error"),
                    }
                    for result in payload.get("results", [])
                    if isinstance(result, dict)
                ],
            },
            ensure_ascii=False,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if batch.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
