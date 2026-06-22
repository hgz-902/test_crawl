from __future__ import annotations

from datetime import datetime
from pathlib import Path
import asyncio
import tempfile
import unittest
from unittest.mock import patch

from crawler_app import web
from crawler_app.workflow_records_rollup import KST
from crawler_app.workflow_records_rollup_scheduler import (
    WorkflowRecordsRollupScheduler,
    next_rollup_datetime,
    parse_rollup_time,
)


class WorkflowRecordsRollupSchedulerTests(unittest.TestCase):
    def test_parse_rollup_time_validates_hh_mm(self) -> None:
        self.assertEqual(parse_rollup_time("00:01"), (0, 1))
        self.assertEqual(parse_rollup_time("17:31"), (17, 31))
        with self.assertRaises(ValueError):
            parse_rollup_time("24:00")
        with self.assertRaises(ValueError):
            parse_rollup_time("bad")

    def test_next_rollup_datetime_uses_next_day_after_due_time(self) -> None:
        now = datetime(2026, 5, 29, 18, 0, tzinfo=KST)

        next_run = next_rollup_datetime(now, "17:31")

        self.assertEqual(next_run, datetime(2026, 5, 30, 17, 31, tzinfo=KST))

    def test_run_once_if_due_rolls_once_per_day_and_writes_log(self) -> None:
        calls: list[dict] = []

        def fake_rollup(**kwargs):
            calls.append(kwargs)
            return {"rolled_count": 1, "errors": []}

        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = WorkflowRecordsRollupScheduler(
                project_root=tmp_dir,
                rollup_time="12:13",
                rollup_func=fake_rollup,
            )

            first = scheduler.run_once_if_due(datetime(2026, 5, 29, 12, 13, tzinfo=KST))
            second = scheduler.run_once_if_due(datetime(2026, 5, 29, 12, 14, tzinfo=KST))

            self.assertEqual(first, {"rolled_count": 1, "errors": []})
            self.assertIsNone(second)
            self.assertEqual(len(calls), 1)
            self.assertEqual(Path(calls[0]["outputs_root"]), Path(tmp_dir) / "outputs")
            self.assertTrue(list((Path(tmp_dir) / "runtime" / "scheduled-task").glob("*-workflow-records-rollup-python.log")))

    def test_run_once_if_due_does_not_roll_before_due_time(self) -> None:
        calls: list[dict] = []
        scheduler = WorkflowRecordsRollupScheduler(
            project_root="C:/project",
            rollup_time="12:13",
            rollup_func=lambda **kwargs: calls.append(kwargs) or {"rolled_count": 1},
        )

        result = scheduler.run_once_if_due(datetime(2026, 5, 29, 12, 12, 59, tzinfo=KST))

        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_web_startup_and_shutdown_control_python_rollup_scheduler(self) -> None:
        with patch.object(web.WORKFLOW_RECORDS_ROLLUP_SCHEDULER, "start") as start, patch.object(
            web.WORKFLOW_RECORDS_ROLLUP_SCHEDULER,
            "stop",
        ) as stop:
            asyncio.run(web.start_workflow_records_rollup_scheduler())
            asyncio.run(web.stop_workflow_records_rollup_scheduler())

        start.assert_called_once_with()
        stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
