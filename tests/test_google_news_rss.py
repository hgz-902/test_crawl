from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler_app.google_news_rss import save_google_news_rss_items

KST = timezone(timedelta(hours=9))


class GoogleNewsRssSaveTests(unittest.TestCase):
    def test_save_google_news_rss_items_writes_batch_named_item_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "google"
            items = [
                {
                    "post_id": "guid-1",
                    "title": "A",
                    "detail_url": "https://news.google.com/articles/1",
                    "description": "desc",
                },
                {
                    "post_id": "guid-2",
                    "title": "B",
                    "detail_url": "https://news.google.com/articles/2",
                    "description": "desc",
                },
            ]

            manifest = save_google_news_rss_items(
                output_dir,
                search_term="SK",
                rss_url="https://news.google.com/rss/search?q=SK",
                final_url="https://news.google.com/rss/search?q=SK",
                items=items,
            )

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_provider"], "google_news_rss")
            self.assertEqual(len(payload["item_files"]), 2)
            date_label = datetime.now(KST).strftime("%Y%m%d")
            for index, file_path in enumerate(payload["item_files"], start=1):
                self.assertRegex(str(file_path), rf"^items/{date_label}/GOOGLE_{date_label}_\d{{6}}_{index}\.json$")
                item_path = output_dir / file_path
                self.assertTrue(item_path.exists())
                item_payload = json.loads(item_path.read_text(encoding="utf-8"))
                self.assertEqual(item_payload["search_term"], "SK")
                self.assertEqual(item_payload["item_index"], index)
            date_dirs = [path for path in (output_dir / "items").iterdir() if path.is_dir()]
            self.assertEqual([path.name for path in date_dirs], [date_label])


if __name__ == "__main__":
    unittest.main()
