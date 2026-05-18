from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crawler_app.orchestration import RegisteredJob
from crawler_app.windows_scheduler import (
    SchedulerCommandResult,
    TASK_FOLDER,
    build_task_action,
    cron_to_schtasks_args,
    delete_managed_task,
    list_managed_task_details,
    list_managed_tasks,
    managed_task_name,
    sync_windows_scheduled_tasks,
    write_task_launcher,
    RUNNER_SCRIPT,
)


class WindowsSchedulerTests(unittest.TestCase):
    def test_list_managed_tasks_filters_to_orchestration_prefix(self) -> None:
        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            return SchedulerCommandResult(
                0,
                '"TaskName","Next Run Time","Status"\n'
                    f'"{TASK_FOLDER}\\crawler_abc","2026-05-18 01:00:00","Ready"\n'
                '"\\Other\\crawler_abc","2026-05-18 01:00:00","Ready"\n',
                "",
            )

        self.assertEqual(list_managed_tasks(command_runner=fake_runner), [f"{TASK_FOLDER}\\crawler_abc"])

    def test_list_managed_task_details_includes_scheduler_runtime_fields(self) -> None:
        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            return SchedulerCommandResult(
                0,
                '"HostName","TaskName","Next Run Time","Status","Last Run Time","Last Result","Task To Run","Schedule Type","Repeat: Every"\n'
                f'"HOST","{TASK_FOLDER}\\crawler_abc","2026-05-18 15:04:00","Ready","2026-05-18 14:49:00","0","powershell.exe -File launcher.ps1","Minute","0 Hour(s), 15 Minute(s)"\n'
                '"HOST","\\Other\\crawler_abc","2026-05-18 15:04:00","Ready","N/A","0","cmd","Minute","15"\n',
                "",
            )

        details = list_managed_task_details(command_runner=fake_runner)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].task_name, f"{TASK_FOLDER}\\crawler_abc")
        self.assertEqual(details[0].status, "Ready")
        self.assertEqual(details[0].last_result, "0")
        self.assertEqual(details[0].repeat_every, "0 Hour(s), 15 Minute(s)")

    def test_list_managed_task_details_falls_back_to_basic_query_when_verbose_parse_is_empty(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            calls.append(args)
            if "/V" in args:
                return SchedulerCommandResult(0, '"WrongHeader","Status"\n"value","Ready"\n', "")
            return SchedulerCommandResult(
                0,
                '"TaskName","Next Run Time","Status"\n'
                    f'"{TASK_FOLDER}\\crawler_abc","2026-05-18 15:04:00","Ready"\n',
                "",
            )

        details = list_managed_task_details(command_runner=fake_runner)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].task_name, f"{TASK_FOLDER}\\crawler_abc")
        self.assertEqual(details[0].next_run_time, "2026-05-18 15:04:00")
        self.assertEqual(calls[0], ["schtasks.exe", "/Query", "/FO", "CSV", "/V"])
        self.assertEqual(calls[1], ["schtasks.exe", "/Query", "/FO", "CSV"])

    def test_list_managed_task_details_falls_back_to_powershell_when_csv_parse_is_empty(self) -> None:
        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            if args[:2] == ["powershell.exe", "-NoProfile"]:
                return SchedulerCommandResult(
                    0,
                    f'[{{"TaskName":"{TASK_FOLDER.replace(chr(92), chr(92) + chr(92))}\\\\crawler_abc","NextRunTime":"2026-05-18 15:04:00","Status":"Ready","LastRunTime":"2026-05-18 14:49:00","LastResult":"0"}}]',
                    "",
                )
            return SchedulerCommandResult(0, '"WrongHeader","Status"\n"value","Ready"\n', "")

        details = list_managed_task_details(command_runner=fake_runner)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].task_name, f"{TASK_FOLDER}\\crawler_abc")
        self.assertEqual(details[0].last_result, "0")

    def test_delete_managed_task_deletes_only_managed_task_and_launcher(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            calls.append(args)
            return SchedulerCommandResult(0, "", "")

        with tempfile.TemporaryDirectory() as tmp_dir:
            launcher_dir = Path(tmp_dir)
            launcher = launcher_dir / "crawler_abc.ps1"
            launcher.write_text("launcher", encoding="utf-8")

            result = delete_managed_task(
                f"{TASK_FOLDER}\\crawler_abc",
                command_runner=fake_runner,
                launcher_dir=launcher_dir,
                registry_path=launcher_dir / "registry.json",
            )

            self.assertEqual(result.status, "deleted")
            self.assertFalse(launcher.exists())

        self.assertEqual(calls[0][:3], ["schtasks.exe", "/End", "/TN"])
        self.assertEqual(calls[1][:3], ["schtasks.exe", "/Delete", "/TN"])

    def test_delete_managed_task_rejects_unmanaged_task(self) -> None:
        with self.assertRaises(ValueError):
            delete_managed_task("\\Other\\crawler_abc", command_runner=lambda args: SchedulerCommandResult(0, "", ""))

    def test_sync_deletes_existing_tasks_and_creates_one_task_per_enabled_job(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            calls.append(args)
            if args[:3] == ["schtasks.exe", "/Query", "/FO"]:
                return SchedulerCommandResult(
                    0,
                    '"TaskName","Next Run Time","Status"\n'
                f'"{TASK_FOLDER}\\crawler_old","2026-05-18 01:00:00","Ready"\n',
                    "",
                )
            return SchedulerCommandResult(0, "", "")

        job = RegisteredJob(
            job_id="sample",
            config_name="Sample",
            config_path="configs/sample.json",
            output_dir="outputs/sample",
        )
        settings = {"jobs": {"sample": {"enabled": True, "cron": "*/15 * * * *", "interval": {"value": 15, "unit": "minutes"}}}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = sync_windows_scheduled_tasks(
                settings,
                [job],
                command_runner=fake_runner,
                is_windows=True,
                launcher_dir=Path(tmp_dir),
                registry_path=Path(tmp_dir) / "registry.json",
            )

        self.assertEqual(result.status, "synced")
        self.assertEqual(result.deleted, [f"{TASK_FOLDER}\\crawler_old"])
        expected_task = managed_task_name("sample")
        self.assertEqual(result.created, [expected_task])
        self.assertTrue(any(call[:3] == ["schtasks.exe", "/Delete", "/TN"] for call in calls))
        create_call = next(call for call in calls if call[:3] == ["schtasks.exe", "/Create", "/F"])
        self.assertIn(expected_task, create_call)
        self.assertIn("/SC", create_call)
        self.assertIn("MINUTE", create_call)
        self.assertIn("/MO", create_call)
        self.assertIn("15", create_call)

    def test_cron_to_schtasks_args_supports_common_forms(self) -> None:
        self.assertEqual(cron_to_schtasks_args("*/5 * * * *")[:4], ["/SC", "MINUTE", "/MO", "5"])
        self.assertEqual(cron_to_schtasks_args("0 */2 * * *")[:4], ["/SC", "HOURLY", "/MO", "2"])
        self.assertEqual(cron_to_schtasks_args("0 3 * * *"), ["/SC", "DAILY", "/MO", "1", "/ST", "03:00"])
        self.assertEqual(cron_to_schtasks_args("0 0 */2 * *"), ["/SC", "DAILY", "/MO", "2", "/ST", "00:00"])

    def test_cron_to_schtasks_args_rejects_invalid_expression(self) -> None:
        with self.assertRaises(ValueError):
            cron_to_schtasks_args("not cron")

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
            self.assertNotIn("-AllowEmailSend", launcher_text)
            self.assertNotIn("SMTP_PASSWORD", launcher_text)
            self.assertNotIn("NAVER_CLIENT_SECRET", launcher_text)

    def test_task_launcher_includes_job_id_and_email_send_only_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            launcher = write_task_launcher(
                Path("C:/project"),
                "sample",
                launcher_dir=Path(tmp_dir),
                allow_email_send=True,
            )

            launcher_text = launcher.read_text(encoding="utf-8-sig")

            self.assertIn("-JobId 'sample'", launcher_text)
            self.assertIn("-AllowEmailSend", launcher_text)

    def test_sync_uses_saved_email_send_setting_for_launcher(self) -> None:
        def fake_runner(args: list[str]) -> SchedulerCommandResult:
            if args[:3] == ["schtasks.exe", "/Query", "/FO"]:
                return SchedulerCommandResult(0, '"TaskName","Next Run Time","Status"\n', "")
            return SchedulerCommandResult(0, "", "")

        job = RegisteredJob(
            job_id="sample",
            config_name="Sample",
            config_path="configs/sample.json",
            output_dir="outputs/sample",
        )
        settings = {
            "allow_email_send": True,
            "jobs": {"sample": {"enabled": True, "interval": {"value": 15, "unit": "minutes"}}},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            sync_windows_scheduled_tasks(
                settings,
                [job],
                command_runner=fake_runner,
                is_windows=True,
                launcher_dir=Path(tmp_dir),
                registry_path=Path(tmp_dir) / "registry.json",
            )
            launcher_text = next(Path(tmp_dir).glob("crawler_*.ps1")).read_text(encoding="utf-8-sig")

        self.assertIn("-AllowEmailSend", launcher_text)
        self.assertIn("-JobId 'sample'", launcher_text)

    def test_runner_script_prefers_project_virtualenv_python(self) -> None:
        script_text = RUNNER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('.venv\\Scripts\\python.exe', script_text)
        self.assertIn('& $pythonPath @args', script_text)


if __name__ == "__main__":
    unittest.main()
