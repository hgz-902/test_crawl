from __future__ import annotations

from unittest.mock import patch
from io import StringIO
import unittest

from crawler_app import scheduled_runner


class ScheduledRunnerTests(unittest.TestCase):
    def test_runner_filters_explicit_job_ids_to_saved_enabled_jobs(self) -> None:
        class FakeStore:
            def load_settings(self) -> dict:
                return {
                    "allow_email_send": False,
                    "jobs": {
                        "enabled": {"enabled": True},
                        "disabled": {"enabled": False},
                    },
                }

        calls: list[dict[str, object]] = []

        def fake_run_batch(selected, **kwargs):
            calls.append({"selected": list(selected), **kwargs})
            return type("Batch", (), {"failed": 0})()

        stdout = StringIO()
        with patch.object(scheduled_runner, "OrchestrationStateStore", return_value=FakeStore()), patch.object(
            scheduled_runner, "run_batch", side_effect=fake_run_batch
        ), patch.object(
            scheduled_runner, "batch_to_dict", return_value={"status": "completed"}
        ), patch("sys.argv", ["scheduled_runner", "--job-id", "disabled", "--allow-email-send"]), patch("sys.stdout", stdout):
            exit_code = scheduled_runner.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["selected"], [])
        self.assertFalse(calls[0]["allow_email_send"])
        self.assertIn("SCHEDULED_RUN_START", stdout.getvalue())
        self.assertIn("SCHEDULED_RUN_SUMMARY", stdout.getvalue())

    def test_runner_uses_saved_email_permission_for_scheduled_runs(self) -> None:
        class FakeStore:
            def load_settings(self) -> dict:
                return {"allow_email_send": True, "jobs": {"enabled": {"enabled": True}}}

        calls: list[dict[str, object]] = []

        def fake_run_batch(selected, **kwargs):
            calls.append({"selected": list(selected), **kwargs})
            return type("Batch", (), {"failed": 0})()

        stdout = StringIO()
        with patch.object(scheduled_runner, "OrchestrationStateStore", return_value=FakeStore()), patch.object(
            scheduled_runner, "run_batch", side_effect=fake_run_batch
        ), patch.object(
            scheduled_runner, "batch_to_dict", return_value={"status": "completed"}
        ), patch("sys.argv", ["scheduled_runner", "--job-id", "enabled"]), patch("sys.stdout", stdout):
            exit_code = scheduled_runner.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["selected"], ["enabled"])
        self.assertTrue(calls[0]["allow_email_send"])


if __name__ == "__main__":
    unittest.main()
