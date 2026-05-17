from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crawler_app.orchestration import RegisteredJob
from crawler_app.windows_scheduler import (
    SchedulerCommandResult,
    build_task_action,
    list_managed_tasks,
    managed_task_name,
    sync_windows_scheduled_tasks,
    write_task_launcher,
)


class WindowsSchedulerTests(unittest.TestCase):
    def test_list_managed_tasks_filters_to_orchestration_prefix(self) -> None:
        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            return SchedulerCommandResult(
                0,
                '"TaskName","Next Run Time","Status"\n'
                '"\\CrawlerOrchestration\\crawler_abc","2026-05-18 01:00:00","Ready"\n'
                '"\\Other\\crawler_abc","2026-05-18 01:00:00","Ready"\n',
                "",
            )

        self.assertEqual(list_managed_tasks(command_runner=fake_runner), ["\\CrawlerOrchestration\\crawler_abc"])

    def test_sync_deletes_existing_tasks_and_creates_enabled_jobs(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            calls.append(args)
            if args[:3] == ["schtasks.exe", "/Query", "/FO"]:
                return SchedulerCommandResult(
                    0,
                    '"TaskName","Next Run Time","Status"\n'
                    '"\\CrawlerOrchestration\\crawler_old","2026-05-18 01:00:00","Ready"\n',
                    "",
                )
            return SchedulerCommandResult(0, "", "")

        job = RegisteredJob(
            job_id="sample",
            config_name="Sample",
            config_path="configs/sample.json",
            output_dir="outputs/sample",
        )
        settings = {"jobs": {"sample": {"enabled": True, "interval": {"value": 15, "unit": "minutes"}}}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = sync_windows_scheduled_tasks(
                settings,
                [job],
                command_runner=fake_runner,
                is_windows=True,
                launcher_dir=Path(tmp_dir),
            )

        self.assertEqual(result.status, "synced")
        self.assertEqual(result.deleted, ["\\CrawlerOrchestration\\crawler_old"])
        self.assertEqual(result.created, [managed_task_name("sample")])
        self.assertTrue(any(call[:3] == ["schtasks.exe", "/Delete", "/TN"] for call in calls))
        create_call = next(call for call in calls if call[:3] == ["schtasks.exe", "/Create", "/F"])
        self.assertIn("/SC", create_call)
        self.assertIn("MINUTE", create_call)
        self.assertIn("/MO", create_call)
        self.assertIn("15", create_call)

    def test_build_task_action_points_to_launcher_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            launcher_dir = Path(tmp_dir)
            launcher = write_task_launcher(Path("C:/project"), "sample", launcher_dir=launcher_dir)
            action = build_task_action(launcher)

            self.assertIn("crawler_", action)
            self.assertIn("powershell.exe", action)
            self.assertNotIn("SMTP_PASSWORD", action)
            self.assertNotIn("NAVER_CLIENT_SECRET", action)
            launcher_text = launcher.read_text(encoding="utf-8-sig")
            self.assertIn("Run-OrchestrationJob.ps1", launcher_text)
            self.assertIn("-JobId 'sample'", launcher_text)
            self.assertNotIn("SMTP_PASSWORD", launcher_text)
            self.assertNotIn("NAVER_CLIENT_SECRET", launcher_text)


if __name__ == "__main__":
    unittest.main()
