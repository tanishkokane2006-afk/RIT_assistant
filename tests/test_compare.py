import json
import tempfile
from pathlib import Path

from tools.compare_legacy_vs_fresh import compare


def test_compare_synthetic_fixture():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        legacy = tmp / "legacy.jsonl"
        fresh = tmp / "fresh.jsonl"
        report = tmp / "comparison.md"

        legacy.write_text(json.dumps({
            "url": "https://example.test/fee",
            "tables": [{"rows": [["Category", "Fee"], ["Open", "136522"]]}],
        }) + "\n", encoding="utf-8")
        fresh.write_text(json.dumps({
            "url": "https://example.test/fee",
            "tables": [{"rows": [["Category", "Fee"], ["Open", "140000"]]}],
        }) + "\n", encoding="utf-8")

        result = compare(legacy, fresh, report)
        text = report.read_text(encoding="utf-8")
        assert result["changed_urls"] == 1
        assert "136522" in text or "Cell" in text
        assert "Legacy vs Fresh Scrape Comparison" in text

if __name__ == "__main__":
    test_compare_synthetic_fixture()
    print("ALL COMPARE TESTS PASSED!")
