from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from crawler_app.workflow import _export_filter_outputs_to_tran_parquet


class TranParquetExportTests(unittest.TestCase):
    def test_exports_filter_files_flat_with_kind_timestamp_names_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            filter_root = root / "outputs" / "sample" / "filter"
            download_dir = filter_root / "001_default" / "downloads" / "20260619"
            text_dir = filter_root / "001_default" / "texts" / "20260619"
            rollup_dir = filter_root / "rollup"
            download_dir.mkdir(parents=True)
            text_dir.mkdir(parents=True)
            rollup_dir.mkdir(parents=True)

            workflow_records = filter_root / "workflow_records.json"
            latest = filter_root / "latest.json"
            rollup = rollup_dir / "workflow_records_20260619_000100.json"
            download_a = download_dir / "a.pdf"
            download_b = download_dir / "b.pdf"
            text_file = text_dir / "a.txt"

            workflow_records.write_text(json.dumps({"config_name": "sample", "records": []}), encoding="utf-8")
            latest.write_text("{}", encoding="utf-8")
            rollup.write_text(json.dumps({"records": [{"skip": True}]}), encoding="utf-8")
            download_a.write_bytes(b"pdf-a")
            download_b.write_bytes(b"pdf-b")
            text_file.write_text("hello", encoding="utf-8")

            same_download_time = self._mtime_ns("2026-06-19T12:34:56.123456+09:00")
            self._set_mtime_ns(workflow_records, self._mtime_ns("2026-06-19T12:34:55.000001+09:00"))
            self._set_mtime_ns(download_a, same_download_time)
            self._set_mtime_ns(download_b, same_download_time)
            self._set_mtime_ns(text_file, self._mtime_ns("2026-06-19T12:34:57.654321+09:00"))

            stats = _export_filter_outputs_to_tran_parquet(filter_root)

            tran_root = filter_root.parent / "tran"
            self.assertEqual(Path(stats["tran_output_dir"]), tran_root)
            self.assertEqual(stats["exported_file_count"], 4)
            self.assertTrue(tran_root.is_dir())
            self.assertFalse(any(path.is_dir() for path in tran_root.iterdir()))

            names = sorted(path.name for path in tran_root.glob("*.parquet"))
            self.assertIn("metadata_20260619_123455000001.parquet", names)
            self.assertIn("download_20260619_123456123456.parquet", names)
            self.assertIn("download_20260619_123456123456_001.parquet", names)
            self.assertIn("text_20260619_123457654321.parquet", names)
            self.assertFalse(any("latest" in name for name in names))
            self.assertFalse(any("rollup" in name for name in names))

            metadata_path = tran_root / "metadata_20260619_123455000001.parquet"
            metadata_table = pq.read_table(metadata_path)
            metadata = metadata_table.to_pylist()[0]
            self.assertEqual(metadata["source_relative_path"], "workflow_records.json")
            self.assertEqual(metadata["source_file_name"], "workflow_records.json")
            self.assertEqual(metadata["tran_kind"], "metadata")
            self.assertNotIn("source_sha256", metadata_table.schema.names)
            self.assertIn("source_file_name", metadata_table.schema.names)

            manifest = json.loads(metadata["tran_manifest_json"])
            manifest_by_source = {entry["source_relative_path"]: entry for entry in manifest}
            self.assertEqual(set(manifest_by_source), {
                "workflow_records.json",
                "001_default/downloads/20260619/a.pdf",
                "001_default/downloads/20260619/b.pdf",
                "001_default/texts/20260619/a.txt",
            })
            self.assertEqual(manifest_by_source["001_default/downloads/20260619/a.pdf"]["tran_kind"], "download")
            self.assertTrue(manifest_by_source["001_default/downloads/20260619/a.pdf"]["tran_file_name"].startswith("download_"))

            download_table = pq.read_table(tran_root / "download_20260619_123456123456.parquet")
            self.assertNotIn("source_sha256", download_table.schema.names)
            self.assertIn("source_file_name", download_table.schema.names)
            self.assertIn("content_bytes", download_table.schema.names)

    def _mtime_ns(self, iso_text: str) -> int:
        parsed = datetime.fromisoformat(iso_text)
        utc_value = parsed.astimezone(timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = utc_value - epoch
        return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + utc_value.microsecond * 1000

    def _set_mtime_ns(self, path: Path, mtime_ns: int) -> None:
        os.utime(path, ns=(mtime_ns, mtime_ns))


if __name__ == "__main__":
    unittest.main()
