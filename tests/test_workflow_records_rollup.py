from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler_app.workflow_records_rollup import rollup_workflow_records

KST = timezone(timedelta(hours=9))


class WorkflowRecordsRollupTests(unittest.TestCase):
    def test_rollup_moves_workflow_records_under_crawler_rollup_dir_and_removes_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            source = outputs / "motir_news" / "filter" / "workflow_records.json"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({"records": [{"final_url": "https://example.com/a"}]}), encoding="utf-8")

            summary = rollup_workflow_records(
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 0, 1, 0, tzinfo=KST),
            )

            archive = outputs / "motir_news" / "filter" / "rollup" / "workflow_records_20260529_000100.json"
            self.assertEqual(summary["rolled_count"], 1)
            self.assertFalse(source.exists())
            self.assertTrue(archive.exists())
            self.assertEqual(json.loads(archive.read_text(encoding="utf-8"))["records"][0]["final_url"], "https://example.com/a")

    def test_rollup_archive_sorts_workflow_records_by_pub_date_latest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            source = outputs / "daum" / "filter" / "workflow_records.json"
            source.parent.mkdir(parents=True)
            source.write_text(
                json.dumps(
                    {
                        "records": [
                            {"extract_title": "old", "pub_date": "2026-04-26T22:00:02.000+09:00", "final_url": "https://v.daum.net/v/old"},
                            {"extract_title": "new", "pub_date": "2026-05-29T10:11:11.000+09:00", "final_url": "https://v.daum.net/v/new"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rollup_workflow_records(
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 0, 1, 0, tzinfo=KST),
            )

            archive = outputs / "daum" / "filter" / "rollup" / "workflow_records_20260529_000100.json"
            payload = json.loads(archive.read_text(encoding="utf-8"))
            self.assertEqual([record["extract_title"] for record in payload["records"]], ["new", "old"])
            self.assertEqual(payload["item_count"], 2)

    def test_rollup_keeps_latest_twenty_archives_per_original_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            rollup_dir = outputs / "site" / "filter" / "rollup"
            rollup_dir.mkdir(parents=True)
            for index in range(20):
                archive = rollup_dir / f"workflow_records_202605{index + 1:02d}_000100.json"
                archive.write_text(json.dumps({"index": index}), encoding="utf-8")
            source = outputs / "site" / "filter" / "workflow_records.json"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps({"index": "new"}), encoding="utf-8")

            summary = rollup_workflow_records(
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 0, 1, 0, tzinfo=KST),
                keep_count=20,
            )

            archives = sorted(path.name for path in rollup_dir.glob("workflow_records_*.json"))
            self.assertEqual(len(archives), 20)
            self.assertNotIn("workflow_records_20260501_000100.json", archives)
            self.assertIn("workflow_records_20260529_000100.json", archives)
            self.assertEqual(summary["deleted_old_count"], 1)

    def test_rollup_skips_locked_workflow_records_without_blocking_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            locked_source = outputs / "locked" / "filter" / "workflow_records.json"
            open_source = outputs / "open" / "filter" / "workflow_records.json"
            locked_source.parent.mkdir(parents=True)
            open_source.parent.mkdir(parents=True)
            locked_source.write_text(json.dumps({"records": [{"final_url": "https://example.com/locked"}]}), encoding="utf-8")
            open_source.write_text(json.dumps({"records": [{"final_url": "https://example.com/open"}]}), encoding="utf-8")
            lock_path = locked_source.with_name(".workflow_records.json.lock")
            lock_path.write_text("active lock", encoding="utf-8")

            summary = rollup_workflow_records(
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 0, 1, 0, tzinfo=KST),
                lock_timeout_seconds=0.01,
                stale_lock_seconds=300,
            )

            self.assertTrue(locked_source.exists())
            self.assertFalse(open_source.exists())
            self.assertEqual(summary["rolled_count"], 1)
            self.assertEqual(summary["skipped"][0]["reason"], "lock_timeout")
            self.assertTrue((outputs / "open" / "filter" / "rollup" / "workflow_records_20260529_000100.json").exists())


if __name__ == "__main__":
    unittest.main()
