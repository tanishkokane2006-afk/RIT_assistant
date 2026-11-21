"""Tests for scraper.pages_io single loader.
Tests:
- Priority order: fresh record wins over legacy record on shared key
- Records sharing the same URL but having distinct dedupe_keys are all kept
"""

import json
import tempfile
from pathlib import Path

from scraper.pages_io import iter_pages


def test_shared_key_priority():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        fresh_file = tmp_path / "fresh_pages.jsonl"
        legacy_file = tmp_path / "legacy_pages.jsonl"

        rec_fresh = {
            "id": "fresh1",
            "url": "https://ritindia.edu/page1",
            "page": 1,
            "type": "html",
            "title": "Fresh Title",
            "text": "Fresh Content",
            "tables": [],
        }
        rec_legacy = {
            "id": "legacy1",
            "url": "https://ritindia.edu/page1",
            "page": 1,
            "type": "html",
            "title": "Legacy Title",
            "text": "Legacy Content",
            "tables": [],
        }

        fresh_file.write_text(json.dumps(rec_fresh) + "\n", encoding="utf-8")
        legacy_file.write_text(json.dumps(rec_legacy) + "\n", encoding="utf-8")

        results = list(iter_pages(paths=[fresh_file, legacy_file]))
        assert len(results) == 1, f"Expected 1 record, got {len(results)}"
        assert results[0]["title"] == "Fresh Title"
        assert results[0]["id"] == "fresh1"


def test_shared_url_distinct_dedupe_keys():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pages_file = tmp_path / "pages.jsonl"

        # Curated records sharing root URL https://ritindia.edu
        rec_inst = {
            "id": "c1",
            "url": "https://ritindia.edu",
            "page": 1,
            "type": "html",
            "title": "Institution",
            "dedupe_key": "curated::institution",
            "text": "Institute info",
            "tables": [],
        }
        rec_lead = {
            "id": "c2",
            "url": "https://ritindia.edu",
            "page": 1,
            "type": "html",
            "title": "Leadership",
            "dedupe_key": "curated::leadership",
            "text": "Leadership info",
            "tables": [],
        }

        pages_file.write_text(
            json.dumps(rec_inst) + "\n" + json.dumps(rec_lead) + "\n",
            encoding="utf-8",
        )

        results = list(iter_pages(paths=[pages_file]))
        assert len(results) == 2, f"Expected 2 records, got {len(results)}"
        keys = {r["dedupe_key"] for r in results}
        assert keys == {"curated::institution", "curated::leadership"}


if __name__ == "__main__":
    test_shared_key_priority()
    test_shared_url_distinct_dedupe_keys()
    print("test_pages_io: ALL PASSED")

