from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from crawler_app.news_grouping import build_article_clusters
from crawler_app.news_ingestion import sync_news_ui_database
from crawler_app.news_ui_api import router


class NewsUiApiTests(unittest.TestCase):
    def test_grouping_guard_does_not_merge_different_templated_titles(self) -> None:
        rows = [
            {
                "article_id": "bill-1",
                "title": "2218848 환경기술 및 환경산업 지원법 일부개정법률안 대안",
                "source_site": "국회",
                "published_at": "2026-06-18 10:00:00",
                "first_seen_at": "2026-06-18 10:00:00",
            },
            {
                "article_id": "bill-2",
                "title": "2218851 야생생물 보호 및 관리에 관한 법률 일부개정법률안 대안",
                "source_site": "국회",
                "published_at": "2026-06-18 10:01:00",
                "first_seen_at": "2026-06-18 10:01:00",
            },
            {
                "article_id": "stock-1",
                "title": "현대모비스 주가 6월 4일 12% 급등 마감",
                "source_site": "증권",
                "published_at": "2026-06-18 10:02:00",
                "first_seen_at": "2026-06-18 10:02:00",
            },
            {
                "article_id": "stock-2",
                "title": "한화오션 주가 6월 4일 12% 급등 마감",
                "source_site": "증권",
                "published_at": "2026-06-18 10:03:00",
                "first_seen_at": "2026-06-18 10:03:00",
            },
            {
                "article_id": "sk-1",
                "title": "SK온 차세대 ESS 신제품 공개",
                "source_site": "조선일보",
                "published_at": "2026-06-18 10:04:00",
                "first_seen_at": "2026-06-18 10:04:00",
            },
            {
                "article_id": "sk-2",
                "title": "SK 온, 차세대 ESS 제품 공개",
                "source_site": "연합뉴스",
                "published_at": "2026-06-18 10:05:00",
                "first_seen_at": "2026-06-18 10:05:00",
            },
            {
                "article_id": "dart-1",
                "title": "SK이노베이션/기업지배구조보고서공시/2026.05.22",
                "source_site": "DART",
                "published_at": "2026-06-18 10:06:00",
                "first_seen_at": "2026-06-18 10:06:00",
            },
            {
                "article_id": "dart-2",
                "title": "SK이노베이션/타법인주식및출자증권처분결정/2026.05.28",
                "source_site": "DART",
                "published_at": "2026-06-18 10:07:00",
                "first_seen_at": "2026-06-18 10:07:00",
            },
        ]
        with patch.dict(
            os.environ,
            {
                "NEWS_GROUPING_PROVIDER": "lexical",
                "NEWS_GROUPING_THRESHOLD": "0.45",
            },
        ):
            assignments = build_article_clusters(rows)

        by_article = {assignment.article_id: assignment.cluster_id for assignment in assignments}
        self.assertNotEqual(by_article["bill-1"], by_article["bill-2"])
        self.assertNotEqual(by_article["stock-1"], by_article["stock-2"])
        self.assertNotEqual(by_article["dart-1"], by_article["dart-2"])
        self.assertEqual(by_article["sk-1"], by_article["sk-2"])

    def test_ingestion_grouping_and_user_state_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            db_path = root / "runtime" / "news_ui.sqlite3"
            records_path = root / "outputs" / "naver_news" / "filter" / "workflow_records.json"
            records_path.parent.mkdir(parents=True)
            records_path.write_text(
                json.dumps(
                    {
                        "config_name": "naver_news",
                        "records": [
                            {
                                "record_key": "NAVER-1",
                                "source_name": "조선일보",
                                "search_term": "SK",
                                "extract_title": "SK온 배터리 투자 확대",
                                "pub_date": "Fri, 29 May 2026 09:00:00 +0900",
                                "final_url": "https://www.chosun.com/economy/1",
                            },
                            {
                                "record_key": "NAVER-2",
                                "source_name": "연합뉴스",
                                "search_term": "SK",
                                "extract_title": "SK온 배터리 투자 확대 발표",
                                "pub_date": "Fri, 29 May 2026 09:05:00 +0900",
                                "final_url": "https://www.yna.co.kr/view/AKR1",
                            },
                            {
                                "record_key": "NAVER-3",
                                "source_name": "매일경제",
                                "search_term": "반도체",
                                "extract_title": "반도체 장비 수출 증가",
                                "pub_date": "Sat, 30 May 2026 09:00:00 +0900",
                                "final_url": "https://www.mk.co.kr/news/1",
                            },
                            {
                                "record_key": "NAVER-4",
                                "source_name": "조선일보",
                                "search_term": "반도체",
                                "extract_title": "SK온 배터리 투자 확대 전망",
                                "pub_date": "Fri, 29 May 2026 09:10:00 +0900",
                                "final_url": "https://www.chosun.com/economy/2",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "NEWS_UI_DB_PATH": str(db_path),
                    "NEWS_GROUPING_PROVIDER": "lexical",
                    "NEWS_GROUPING_THRESHOLD": "0.45",
                },
            ):
                summary = sync_news_ui_database(project_root=root, rebuild=True)
                self.assertEqual(summary.articles_upserted, 4)
                self.assertEqual(summary.sentiments_written, 4)
                self.assertGreaterEqual(summary.clusters_written, 4)

                app = FastAPI()
                app.include_router(router)
                client = TestClient(app)

                options = client.get("/api/filter-options")
                self.assertEqual(options.status_code, 200)
                self.assertIn("연합뉴스", options.json()["sources"])
                self.assertIn("SK", options.json()["search_terms"])

                news = client.get("/api/news", params={"user_id": "tester", "page_size": 10})
                self.assertEqual(news.status_code, 200)
                self.assertEqual(news.json()["totalCount"], 4)

                grouped = client.get("/api/news/grouped", params={"user_id": "tester", "search_term": "SK"})
                self.assertEqual(grouped.status_code, 200)
                grouped_items = grouped.json()["items"]
                self.assertEqual(grouped.json()["totalCount"], 1)
                self.assertEqual(grouped_items[0]["source_name"], "연합뉴스")
                self.assertEqual(grouped_items[0]["similar_count"], 1)
                self.assertEqual(len(grouped_items[0]["similar_articles"]), 1)

                grouped_all = client.get("/api/news/grouped", params={"user_id": "tester", "page_size": 10})
                self.assertEqual(grouped_all.status_code, 200)
                largest_similar_count = max(item["similar_count"] for item in grouped_all.json()["items"])
                self.assertEqual(largest_similar_count, 2)

                article_id = grouped_items[0]["article_id"]
                read = client.patch(f"/api/news/{article_id}/read", json={"user_id": "tester", "value": True})
                self.assertEqual(read.status_code, 200)
                self.assertTrue(read.json()["is_read"])

                favorite = client.patch(f"/api/news/{article_id}/favorite", json={"user_id": "tester", "value": True})
                self.assertEqual(favorite.status_code, 200)
                self.assertTrue(favorite.json()["is_favorite"])

                stats = client.get("/api/stats", params={"user_id": "tester"})
                self.assertEqual(stats.status_code, 200)
                self.assertEqual(stats.json()["read"], 1)
                self.assertEqual(stats.json()["favorite"], 1)

                analysis = client.post(
                    f"/api/news/{article_id}/analysis/save",
                    json={
                        "user_id": "tester",
                        "prompt_used": "요약",
                        "sentiment_label": "negative",
                        "sentiment_display": "부정",
                        "action_plan": "1단계 대응",
                        "impact": "시장 반응 확인",
                        "action_source": "user_modified",
                        "sentiment_source": "user_modified",
                    },
                )
                self.assertEqual(analysis.status_code, 200)
                self.assertEqual(analysis.json()["confirmed_by"], "tester")

                saved = client.get(f"/api/news/{article_id}/analysis", params={"user_id": "tester"})
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()["sentiment_label"], "negative")
                self.assertEqual(saved.json()["action_plan"], "1단계 대응")
                refreshed = client.get("/api/news", params={"user_id": "tester", "title": grouped_items[0]["title"]})
                self.assertEqual(refreshed.status_code, 200)
                self.assertIsNone(refreshed.json()["items"][0]["sentiment_confidence"])

                analyzed = client.post(
                    f"/api/news/{article_id}/analyze",
                    json={"user_id": "tester", "prompt": "분석"},
                )
                self.assertEqual(analyzed.status_code, 404)


if __name__ == "__main__":
    unittest.main()
