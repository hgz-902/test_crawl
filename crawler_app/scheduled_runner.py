from __future__ import annotations

import argparse
import json

from crawler_app.orchestration import OrchestrationStateStore, batch_to_dict, run_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one orchestration job from Windows Task Scheduler.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--allow-email-send", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    batch = run_batch(
        [args.job_id],
        store=OrchestrationStateStore(),
        force_due=True,
        allow_email_send=args.allow_email_send,
    )
    print(json.dumps(batch_to_dict(batch), ensure_ascii=False, indent=2))
    return 1 if batch.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
