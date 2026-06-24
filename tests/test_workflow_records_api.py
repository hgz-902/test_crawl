from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crawler_app import web
from crawler_app.workflow_records_api import build_workflow_records_response


class WorkflowRecordsApiTests(unittest.TestCase):
    def test_today_query_reads_live_workflow_records_not_today_rollup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            filter_dir = outputs / "naver_news" / "filter"
            rollup_dir = filter_dir / "rollup"
            rollup_dir.mkdir(parents=True)
            self._write_records(
                filter_dir / "workflow_records.json",
                [
                    {
                        "record_key": "NAVER-LIVE",
                        "search_term": "SK",
                        "filter_term": "SK",
                        "extract_title": "live",
                        "description": "",
                        "pub_date": "Fri, 29 May 2026 10:00:00 +0900",
                        "final_url": "https://example.com/live",
                    }
                ],
            )
            self._write_records(
                rollup_dir / "workflow_records_20260529_000100.json",
                [{"record_key": "NAVER-TODAY-ROLLUP", "pub_date": "Fri, 29 May 2026 00:00:00 +0900"}],
            )

            response = build_workflow_records_response(
                {"date": "2026-05-29", "source_name": "naver_news"},
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(response["totalCount"], 1)
            self.assertEqual(response["items"][0]["record_key"], "NAVER-LIVE")

    def test_prior_date_query_reads_rollup_by_rollup_file_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            rollup_dir = outputs / "daum" / "filter" / "rollup"
            rollup_dir.mkdir(parents=True)
            self._write_records(
                rollup_dir / "workflow_records_20260528_000100.json",
                [{"record_key": "DAUM-OLD", "pub_date": "Fri, 29 May 2026 10:00:00 +0900"}],
            )

            response = build_workflow_records_response(
                {"date": "2026-05-28", "source_name": "daum"},
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(response["items"], [{"record_key": "DAUM-OLD", "pub_date": "Fri, 29 May 2026 10:00:00 +0900"}])

    def test_range_query_all_sources_sorts_by_published_at_alias_and_paginates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            self._write_records(
                outputs / "naver_news" / "filter" / "workflow_records.json",
                [{"record_key": "NAVER-NEW", "pub_date": "Fri, 29 May 2026 12:00:00 +0900"}],
            )
            self._write_records(
                outputs / "google" / "filter" / "rollup" / "workflow_records_20260528_000100.json",
                [{"record_key": "GOOGLE-OLD", "pub_date": "Thu, 28 May 2026 09:00:00 +0900"}],
            )

            response = build_workflow_records_response(
                {
                    "from_date": "2026-05-28",
                    "to_date": "2026-05-29",
                    "sort_by": "published_at",
                    "sort_order": "desc",
                    "page": 1,
                    "page_size": 1,
                },
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(response["totalCount"], 2)
            self.assertEqual(response["page"], 1)
            self.assertEqual(response["pageSize"], 1)
            self.assertEqual([record["record_key"] for record in response["items"]], ["NAVER-NEW"])

    def test_page_size_is_capped_at_one_hundred(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = Path(tmp_dir) / "outputs"
            self._write_records(
                outputs / "naver_news" / "filter" / "workflow_records.json",
                [{"record_key": f"NAVER-{index}", "pub_date": "Fri, 29 May 2026 12:00:00 +0900"} for index in range(101)],
            )

            response = build_workflow_records_response(
                {"date": "2026-05-29", "page_size": 500},
                outputs_root=outputs,
                now=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(response["pageSize"], 100)
            self.assertEqual(len(response["items"]), 100)

    def test_web_route_accepts_post_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            outputs = tmp_path / "outputs"
            today = datetime.now(timezone.utc).date().isoformat()
            self._write_records(
                outputs / "naver_news" / "filter" / "workflow_records.json",
                [{"record_key": "NAVER-LIVE", "pub_date": f"{today}T12:00:00+09:00"}],
            )
            with patch.object(web, "BASE_DIR", tmp_path), TestClient(web.app) as client:
                response = client.post("/api/workflow-records", json={"date": today, "source_name": "naver_news"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["items"][0]["record_key"], "NAVER-LIVE")

    def test_web_route_accepts_post_form_and_rejects_invalid_source_name(self) -> None:
        with TestClient(web.app) as client:
            response = client.post("/api/workflow-records/search", data={"source_name": "../outputs"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("source_name", response.json()["detail"])

    @staticmethod
    def _write_records(path: Path, records: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
