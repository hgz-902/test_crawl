from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile
import unittest

from crawler_app.runtime_maintenance import RuntimeRetentionPolicy, cleanup_runtime_files


class RuntimeMaintenanceTests(unittest.TestCase):
    def test_cleanup_trims_histories_logs_tmp_and_flash_without_touching_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state_dir = root / "orchestration_state"
            history_path = state_dir / "run_history.json"
            job_history = state_dir / "history" / "site.json"
            history_path.parent.mkdir(parents=True)
            job_history.parent.mkdir(parents=True)
            history_path.write_text(json.dumps([{"index": index} for index in range(5)]), encoding="utf-8")
            job_history.write_text(json.dumps([{"index": index} for index in range(5)]), encoding="utf-8")

            logs_dir = root / "logs"
            logs_dir.mkdir()
            (logs_dir / "crawl_results.jsonl").write_text("\n".join(json.dumps({"index": index}) for index in range(5)) + "\n", encoding="utf-8")
            old_log = logs_dir / "orchestrator.log"
            old_log.write_text("old", encoding="utf-8")

            scheduled_dir = root / "runtime" / "scheduled-task"
            scheduled_dir.mkdir(parents=True)
            old_scheduled = scheduled_dir / "20260501_010101-site.log"
            old_scheduled.write_text("old", encoding="utf-8")
            recent_scheduled = scheduled_dir / "20260519_010101-site.log"
            recent_scheduled.write_text("recent", encoding="utf-8")
            old_tmp = scheduled_dir / "20260501_010101-site.stdout.tmp"
            old_tmp.write_text("old tmp", encoding="utf-8")

            flash = state_dir / "flash" / "old.json"
            flash.parent.mkdir()
            flash.write_text("{}", encoding="utf-8")

            output_file = root / "outputs" / "site" / "filter" / "workflow_records.json"
            output_file.parent.mkdir(parents=True)
            output_file.write_text("{}", encoding="utf-8")

            now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
            old_time = (now - timedelta(days=20)).timestamp()
            for path in (old_log, old_scheduled, old_tmp, flash):
                os.utime(path, (old_time, old_time))

            cleanup_runtime_files(
                app_root=root,
                history_path=history_path,
                policy=RuntimeRetentionPolicy(
                    global_history_entries=2,
                    job_history_entries=3,
                    scheduled_log_days=7,
                    scheduled_log_keep_per_job=1,
                    scheduled_tmp_days=1,
                    app_log_days=14,
                    crawl_results_jsonl_lines=2,
                    flash_hours=1,
                ),
                now=now,
            )

            self.assertEqual([entry["index"] for entry in json.loads(history_path.read_text(encoding="utf-8"))], [3, 4])
            self.assertEqual([entry["index"] for entry in json.loads(job_history.read_text(encoding="utf-8"))], [2, 3, 4])
            self.assertEqual(len((logs_dir / "crawl_results.jsonl").read_text(encoding="utf-8").splitlines()), 2)
            self.assertFalse(old_log.exists())
            self.assertFalse(old_scheduled.exists())
            self.assertTrue(recent_scheduled.exists())
            self.assertFalse(old_tmp.exists())
            self.assertFalse(flash.exists())
            self.assertTrue(output_file.exists())


if __name__ == "__main__":
    unittest.main()
