from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler_app.google_news_rss import save_google_news_rss_items

KST = timezone(timedelta(hours=9))


class GoogleNewsRssSaveTests(unittest.TestCase):
    def test_save_google_news_rss_items_writes_stable_item_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "google"
            item = {
                "post_id": "guid-1",
                "title": "A",
                "detail_url": "https://news.google.com/articles/1",
                "description": "desc",
            }

            first = save_google_news_rss_items(
                output_dir,
                search_term="SK",
                rss_url="https://news.google.com/rss/search?q=SK",
                final_url="https://news.google.com/rss/search?q=SK",
                items=[item],
            )
            second = save_google_news_rss_items(
                output_dir,
                search_term="SK",
                rss_url="https://news.google.com/rss/search?q=SK",
                final_url="https://news.google.com/rss/search?q=SK",
                items=[item],
            )

            self.assertEqual(first, second)
            payload = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_provider"], "google_news_rss")
            self.assertEqual(len(payload["item_files"]), 1)
            self.assertTrue(payload["item_files"][0].startswith(f"items/{datetime.now(KST).strftime('%Y%m%d')}/item_"))
            item_path = output_dir / payload["item_files"][0]
            self.assertTrue(item_path.exists())
            item_payload = json.loads(item_path.read_text(encoding="utf-8"))
            self.assertEqual(item_payload["search_term"], "SK")
            self.assertEqual(item_payload["item_index"], 1)
            date_dirs = [path for path in (output_dir / "items").iterdir() if path.is_dir()]
            self.assertEqual([path.name for path in date_dirs], [datetime.now(KST).strftime("%Y%m%d")])


if __name__ == "__main__":
    unittest.main()
