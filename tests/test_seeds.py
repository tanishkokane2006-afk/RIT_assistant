"""
Test seed uniqueness and handling of empty-URL seeds.
"""

from collections import defaultdict
import config
from scraper.seeds import SEEDS, duplicates
import scraper.crawl as crawl

def test_no_duplicate_urls():
    dups = duplicates()
    assert len(dups) == 0, f"Found duplicate URLs in seeds: {dups}"
    assert len(SEEDS) == len(set(s["name"] for s in SEEDS)), "Duplicate seed names"

def test_empty_url_skipped(monkeypatch=None):
    # Test that crawl.run skips a seed with an empty URL without raising an error
    dummy_seed = {"name": "test_empty_seed", "url": "", "category": "general"}
    original_seeds = crawl.SEEDS
    try:
        crawl.SEEDS = [dummy_seed]
        # Run dry run with --check logic
        crawl.run(only={"test_empty_seed"}, with_pdfs=False, dry=True)
    finally:
        crawl.SEEDS = original_seeds

if __name__ == "__main__":
    print("Testing seeds uniqueness...")
    test_no_duplicate_urls()
    print("Testing empty URL seed skipping...")
    test_empty_url_skipped()
    print("ALL SEED TESTS PASSED!")
