from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from crawler_app import orchestration
from crawler_app.orchestration import (
    DEFAULT_KEYWORDS,
    DEFAULT_RECIPIENTS,
    OrchestrationStateStore,
    RegisteredJob,
    build_duplicate_index,
    duplicate_key_for_record,
    next_cron_run,
    normalize_cron_expression,
    normalize_interval,
    notify_keyword_matches,
    records_matching_keywords,
    registered_config_jobs,
    run_batch,
)


class OrchestrationTests(unittest.TestCase):
    def test_state_store_uses_defaults_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            history_path = Path(tmp_dir) / "history.json"
            store = OrchestrationStateStore(settings_path=settings_path, history_path=history_path)

            settings = store.load_settings()

            self.assertEqual(settings["keywords"], DEFAULT_KEYWORDS)
            self.assertEqual(settings["recipients"], DEFAULT_RECIPIENTS)
            self.assertEqual(settings["jobs"], {})

            saved = store.save_settings(
                {
                    "keywords": [" SK ", ""],
                    "recipients": ["a@example.com"],
                    "jobs": {"Sample Job": {"enabled": True, "interval": {"value": "15", "unit": "minutes"}}},
                }
            )

            self.assertTrue(settings_path.exists())
            self.assertEqual(saved["jobs"]["sample_job"]["interval"], {"value": 15, "unit": "minutes"})
            self.assertTrue(saved["jobs"]["sample_job"]["enabled"])

            store.append_history({"batch_id": "b1"})
            self.assertEqual(store.load_history(), [{"batch_id": "b1"}])

    def test_registered_config_jobs_uses_config_file_stem_job_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "my_site.json").write_text(
                json.dumps(
                    {
                        "name": "My Site",
                        "start_url": "https://example.com",
                        "output_dir": "outputs/my_site",
                        "search_terms": ["SK"],
                        "filter_terms": ["최태원"],
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            jobs = registered_config_jobs(config_dir)

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].job_id, "my_site")
            self.assertEqual(jobs[0].config_name, "My Site")
            self.assertEqual(jobs[0].output_dir, "outputs/my_site")

    def test_duplicate_key_prefers_title_and_url_across_record_shapes(self) -> None:
        parser_record = {
            "extracts": {
                "title": " SK Group News ",
                "originallink": "https://news.example.com/a",
            },
            "final_url": "https://rss.example.com",
        }
        general_record = {
            "extracts": {
                "extract_title": "SK Group News",
            },
            "final_url": "https://news.example.com/a",
        }
        title_only_record = {"steps": [{"action": "parser", "value": "Only Title"}], "extracts": {}}

        self.assertEqual(duplicate_key_for_record(parser_record), duplicate_key_for_record(general_record))
        self.assertEqual(duplicate_key_for_record(title_only_record), "only title")

    def test_build_duplicate_index_reads_workflow_record_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "outputs" / "site" / "filter"
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "workflow_records.json").write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "extracts": {"title": "Existing", "link": "https://example.com/existing"},
                                "final_url": "https://rss.example.com",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            index = build_duplicate_index([Path(tmp_dir) / "outputs"])

            self.assertIn("existing | https://example.com/existing", index)

    def test_duplicate_stop_snapshot_merge_preserves_existing_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "outputs" / "site"
            snapshot_path = output_dir / "filter" / "workflow_records.json"
            snapshot_path.parent.mkdir(parents=True)
            existing_record = {"extracts": {"title": "Existing", "link": "https://example.com/existing"}}
            repeated_existing_record = {
                "extracts": {"title": "Existing", "link": "https://example.com/existing"},
                "search_term": "second-term",
            }
            fresh_record = {"extracts": {"title": "Fresh", "link": "https://example.com/fresh"}}
            snapshot_path.write_text(
                json.dumps({"config_name": "site", "item_count": 2, "records": [existing_record, repeated_existing_record]}),
                encoding="utf-8",
            )

            before = orchestration._read_workflow_snapshots(output_dir)
            snapshot_path.write_text(
                json.dumps({"config_name": "site", "item_count": 1, "records": [fresh_record]}),
                encoding="utf-8",
            )
            orchestration._merge_or_restore_workflow_snapshots(output_dir, before)

            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["item_count"], 3)
            self.assertEqual([record["extracts"]["title"] for record in payload["records"]], ["Existing", "Existing", "Fresh"])

    def test_duplicate_stop_snapshot_restore_keeps_existing_records_when_new_snapshot_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "outputs" / "site"
            snapshot_path = output_dir / "filter" / "workflow_records.json"
            snapshot_path.parent.mkdir(parents=True)
            existing_record = {"extracts": {"title": "Existing", "link": "https://example.com/existing"}}
            snapshot_path.write_text(
                json.dumps({"config_name": "site", "item_count": 1, "records": [existing_record]}),
                encoding="utf-8",
            )

            before = orchestration._read_workflow_snapshots(output_dir)
            snapshot_path.write_text(json.dumps({"config_name": "site", "item_count": 0, "records": []}), encoding="utf-8")
            orchestration._merge_or_restore_workflow_snapshots(output_dir, before)

            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["item_count"], 1)
            self.assertEqual(payload["records"][0]["extracts"]["title"], "Existing")

    def test_run_batch_loads_local_dotenv_for_orchestration_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            (config_dir / "site.json").write_text(
                json.dumps(
                    {
                        "name": "site",
                        "start_url": "https://example.com",
                        "output_dir": str(tmp_path / "outputs" / "site"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    }
                ),
                encoding="utf-8",
            )
            (tmp_path / ".env").write_text("ORCHESTRATION_DOTENV_PROOF=loaded\n", encoding="utf-8")
            os.environ.pop("ORCHESTRATION_DOTENV_PROOF", None)

            def fake_runner(config_path: Path, record_policy):
                self.assertEqual(os.environ.get("ORCHESTRATION_DOTENV_PROOF"), "loaded")
                return {"success": True, "records": [{"extracts": {"title": "Fresh", "link": "https://example.com/fresh"}}]}

            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            with patch.object(orchestration, "APP_ROOT", tmp_path):
                batch = run_batch(["site"], store=store, config_dir=config_dir, runner=fake_runner, send_notifications=False)

            self.assertEqual(batch.results[0].status, "succeeded")

    def test_batch_runner_duplicate_stops_one_job_and_continues_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            for name in ("first", "second"):
                (config_dir / f"{name}.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "start_url": f"https://example.com/{name}",
                            "output_dir": str(tmp_path / "outputs" / name),
                            "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                        }
                    ),
                    encoding="utf-8",
                )

            snapshot_dir = tmp_path / "snapshots" / "filter"
            snapshot_dir.mkdir(parents=True)
            duplicate_record = {"extracts": {"title": "Duplicate", "link": "https://example.com/dup"}}
            (snapshot_dir / "workflow_records.json").write_text(
                json.dumps({"records": [duplicate_record]}),
                encoding="utf-8",
            )

            def fake_runner(config_path: Path, record_policy):
                calls.append(config_path.stem)
                if config_path.stem == "first":
                    records = [
                        {"extracts": {"title": "Fresh", "link": "https://example.com/fresh"}},
                        duplicate_record,
                    ]
                else:
                    records = [{"extracts": {"title": "Second Fresh", "link": "https://example.com/second"}}]

                accepted = []
                for record in records:
                    decision = record_policy(record)
                    if decision.get("include", True):
                        accepted.append(record)
                    if decision.get("stop"):
                        break
                return {"success": True, "records": accepted, "metadata": {"config_path": str(config_path)}}

            calls: list[str] = []
            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            batch = run_batch(
                ["first", "second"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                snapshot_roots=[tmp_path / "snapshots"],
                send_notifications=False,
            )

            self.assertEqual(batch.total, 2)
            self.assertEqual(calls, ["first", "second"])
            self.assertEqual(batch.results[0].status, "duplicate_stopped")
            self.assertEqual(batch.results[0].items_count, 1)
            self.assertEqual(batch.results[0].records[0]["extracts"]["title"], "Fresh")
            self.assertEqual(batch.results[1].status, "succeeded")
            self.assertEqual(batch.results[1].items_count, 1)
            self.assertEqual(store.load_history()[0]["duplicate_stopped"], 1)

    def test_run_batch_preserves_exact_korean_job_id_before_legacy_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            (config_dir / "시그널.json").write_text(
                json.dumps(
                    {
                        "name": "시그널",
                        "start_url": "https://example.com/signal",
                        "output_dir": str(tmp_path / "outputs" / "signal"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            calls: list[str] = []

            def fake_runner(config_path: Path, record_policy):
                calls.append(config_path.name)
                return {"success": True, "records": [{"extracts": {"title": "Fresh", "link": "https://example.com/fresh"}}]}

            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            batch = run_batch(["시그널"], store=store, config_dir=config_dir, runner=fake_runner, send_notifications=False)

            self.assertEqual(batch.total, 1)
            self.assertEqual(calls, ["시그널.json"])

    def test_batch_runner_continues_when_first_record_is_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            for name in ("first", "second"):
                (config_dir / f"{name}.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "start_url": f"https://example.com/{name}",
                            "output_dir": str(tmp_path / "outputs" / name),
                            "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                        }
                    ),
                    encoding="utf-8",
                )

            duplicate_record = {"extracts": {"title": "Duplicate", "link": "https://example.com/dup"}}
            snapshot_dir = tmp_path / "snapshots" / "filter"
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "workflow_records.json").write_text(json.dumps({"records": [duplicate_record]}), encoding="utf-8")
            calls: list[str] = []

            def fake_runner(config_path: Path, record_policy):
                calls.append(config_path.stem)
                records = [duplicate_record] if config_path.stem == "first" else [
                    {"extracts": {"title": "Second", "link": "https://example.com/second"}}
                ]
                accepted = []
                for record in records:
                    decision = record_policy(record)
                    if decision.get("include", True):
                        accepted.append(record)
                    if decision.get("stop"):
                        break
                return {"success": True, "records": accepted}

            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            batch = run_batch(
                ["first", "second"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                snapshot_roots=[tmp_path / "snapshots"],
                send_notifications=False,
            )

            self.assertEqual(calls, ["first", "second"])
            self.assertEqual(batch.results[0].status, "duplicate_stopped")
            self.assertEqual(batch.results[0].items_count, 0)
            self.assertEqual(batch.results[1].status, "succeeded")

    def test_batch_runner_skips_same_job_duplicate_seen_during_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            (config_dir / "site.json").write_text(
                json.dumps(
                    {
                        "name": "site",
                        "start_url": "https://example.com",
                        "output_dir": str(tmp_path / "outputs" / "site"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    }
                ),
                encoding="utf-8",
            )
            repeated = {"extracts": {"title": "Repeated", "link": "https://example.com/repeated"}}

            def fake_runner(config_path: Path, record_policy):
                accepted = []
                for record in [repeated, repeated]:
                    decision = record_policy(record)
                    if decision.get("include", True):
                        accepted.append(record)
                    if decision.get("stop"):
                        break
                return {"success": True, "records": accepted}

            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            batch = run_batch(
                ["site"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                snapshot_roots=[],
                send_notifications=False,
            )

            self.assertEqual(batch.results[0].status, "succeeded")
            self.assertEqual(batch.results[0].items_count, 1)
            self.assertEqual(batch.results[0].metadata["same_run_duplicate_skipped_count"], 1)

    def test_batch_runner_skips_when_another_batch_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            (config_dir / "site.json").write_text(
                json.dumps(
                    {
                        "name": "site",
                        "start_url": "https://example.com",
                        "output_dir": str(tmp_path / "outputs" / "site"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    }
                ),
                encoding="utf-8",
            )
            lock_path = store.job_lock_path("site")
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text(
                json.dumps({"pid": 12345, "created_at": orchestration.utc_timestamp()}),
                encoding="utf-8",
            )
            calls: list[Path] = []

            def fake_runner(config_path: Path, record_policy):
                calls.append(config_path)
                return {"success": True, "records": []}

            batch = run_batch(
                ["site"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                send_notifications=False,
            )

            self.assertEqual(batch.status, "completed")
            self.assertEqual(batch.total, 1)
            self.assertEqual(batch.results[0].status, "skipped_running")
            self.assertEqual(calls, [])
            self.assertEqual(store.load_history()[0]["results"][0]["status"], "skipped_running")

    def test_batch_runner_default_duplicate_scope_is_per_config_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            first_output = tmp_path / "outputs" / "first"
            second_output = tmp_path / "outputs" / "second"
            config_dir.mkdir()
            for name, output_dir in (("first", first_output), ("second", second_output)):
                (config_dir / f"{name}.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "start_url": f"https://example.com/{name}",
                            "output_dir": str(output_dir),
                            "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                        }
                    ),
                    encoding="utf-8",
                )

            duplicate_record = {"extracts": {"title": "Shared", "link": "https://example.com/shared"}}
            first_snapshot = first_output / "filter"
            first_snapshot.mkdir(parents=True)
            (first_snapshot / "workflow_records.json").write_text(
                json.dumps({"records": [duplicate_record]}),
                encoding="utf-8",
            )

            def fake_runner(config_path: Path, record_policy):
                accepted = []
                decision = record_policy(duplicate_record)
                if decision.get("include", True):
                    accepted.append(duplicate_record)
                return {"success": True, "records": accepted}

            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            batch = run_batch(
                ["first", "second"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                send_notifications=False,
            )

            self.assertEqual(batch.results[0].status, "duplicate_stopped")
            self.assertEqual(batch.results[1].status, "succeeded")
            self.assertEqual(batch.results[1].items_count, 1)

    def test_keyword_match_scans_record_text_case_insensitive(self) -> None:
        records = [
            {"extracts": {"title": "sk expands", "body": "plain body"}},
            {"extracts": {"title": "other", "body": "최태원 interview"}},
            {"extracts": {"title": "none", "body": "irrelevant"}},
        ]

        matches = records_matching_keywords(records, ["SK", "최태원"])

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["keywords"], ["sk"])
        self.assertEqual(matches[1]["keywords"], ["최태원"])

    def test_notify_keyword_matches_dry_runs_without_smtp_password(self) -> None:
        job = RegisteredJob(
            job_id="site",
            config_name="Site",
            config_path="configs/site.json",
            output_dir="outputs/site",
        )
        matches = [{"record": {"extracts": {"title": "SK title", "link": "https://example.com"}}, "keywords": ["sk"]}]

        with patch.object(orchestration, "load_orchestration_env", lambda: None), patch.dict(
            os.environ, {"SMTP_HOST": "smtp.example.com"}, clear=True
        ):
            result = notify_keyword_matches(
                matches,
                settings={"recipients": ["to@example.com"], "sender": "from@example.com"},
                job=job,
        )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["reason"], "smtp_credentials_missing")
        self.assertNotIn("password", json.dumps(result).casefold())

    def test_notify_keyword_matches_requires_explicit_send_permission(self) -> None:
        matches = [{"record": {"extracts": {"title": "SK title", "link": "https://example.com"}}, "keywords": ["sk"]}]

        with patch.object(orchestration, "load_orchestration_env", lambda: None), patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "from@example.com",
                "SMTP_PASSWORD": "secret",
            },
            clear=True,
        ):
            result = notify_keyword_matches(
                matches,
                settings={"recipients": ["to@example.com"], "sender": "from@example.com"},
                allow_send=False,
            )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["reason"], "real_send_not_allowed")
        self.assertNotIn("secret", json.dumps(result).casefold())

    def test_notification_body_groups_site_topic_description_and_url(self) -> None:
        job = RegisteredJob(
            job_id="naver_news",
            config_name="네이버뉴스",
            config_path="configs/네이버뉴스.json",
            output_dir="outputs/naver_news",
        )
        matches = [
            {
                "record": {
                    "search_term": "최태원",
                    "extracts": {
                        "description": "SK 관련 기사 설명입니다.",
                        "link": "https://example.com/article",
                    },
                },
                "keywords": ["sk"],
            }
        ]

        body = orchestration._notification_body(matches, job=job)

        self.assertIn("Site: 네이버뉴스", body)
        self.assertIn("네이버뉴스 > 최태원", body)
        self.assertIn("desc: SK 관련 기사 설명입니다.", body)
        self.assertIn("URL: https://example.com/article", body)

    def test_batch_runner_skips_not_due_job_and_force_runs_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_dir = tmp_path / "configs"
            config_dir.mkdir()
            (config_dir / "site.json").write_text(
                json.dumps(
                    {
                        "name": "site",
                        "start_url": "https://example.com",
                        "output_dir": str(tmp_path / "outputs" / "site"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    }
                ),
                encoding="utf-8",
            )
            store = OrchestrationStateStore(
                settings_path=tmp_path / "state" / "settings.json",
                history_path=tmp_path / "state" / "history.json",
            )
            future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
            store.save_settings(
                {
                    "keywords": ["SK"],
                    "recipients": ["to@example.com"],
                    "jobs": {"site": {"enabled": True, "interval": {"value": 1, "unit": "hours"}, "next_run_at": future}},
                }
            )
            calls: list[str] = []

            def fake_runner(config_path: Path, record_policy):
                calls.append(config_path.stem)
                return {"success": True, "records": [{"extracts": {"title": "Fresh", "link": "https://example.com/fresh"}}]}

            skipped = run_batch(
                ["site"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                snapshot_roots=[],
                send_notifications=False,
            )

            self.assertEqual(calls, [])
            self.assertEqual(skipped.results[0].status, "skipped_not_due")
            self.assertEqual(skipped.skipped_not_due, 1)

            forced = run_batch(
                ["site"],
                store=store,
                config_dir=config_dir,
                runner=fake_runner,
                snapshot_roots=[],
                send_notifications=False,
                force_due=True,
            )

            self.assertEqual(calls, ["site"])
            self.assertEqual(forced.results[0].status, "succeeded")
            self.assertTrue(store.load_settings()["jobs"]["site"]["next_run_at"])

    def test_normalize_interval_guards_unit_and_value(self) -> None:
        self.assertEqual(normalize_interval({"value": "0", "unit": "weeks"}), {"value": 1, "unit": "hours"})
        self.assertEqual(normalize_interval({"value": "2", "unit": "days"}), {"value": 2, "unit": "days"})

    def test_normalize_cron_expression_and_next_run(self) -> None:
        self.assertEqual(normalize_cron_expression("*/5 * * * *"), "*/5 * * * *")
        next_run = next_cron_run("0 3 * * *", after=datetime(2026, 5, 18, 2, 59, tzinfo=timezone.utc))
        self.assertEqual(next_run, datetime(2026, 5, 18, 3, 0, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            normalize_cron_expression("* * *")


if __name__ == "__main__":
    unittest.main()
