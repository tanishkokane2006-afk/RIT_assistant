"""
Single entry point for reading scraped pages.

Two files can exist:
  data/raw/pages.jsonl         fresh output of `python -m scraper.crawl`
  data/raw/legacy_pages.jsonl  converted from the old project (tools/convert_legacy.py)

iter_pages() yields every record once. If the same key exists (rec['dedupe_key'] if present, else (url, page, type)) in both,
the FRESH scrape wins and the legacy one is dropped. Normaliser and indexer must read
pages ONLY through this function.
"""
import json
from pathlib import Path

try:
    import config
    RAW_DIR = config.RAW_DIR
    PAGES_JSONL = config.PAGES_JSONL
except Exception:                                   # pragma: no cover
    RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
    PAGES_JSONL = RAW_DIR / "pages.jsonl"
LEGACY_PAGES_JSONL = RAW_DIR / "legacy_pages.jsonl"


def _read(path):
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def iter_pages(paths=None):
    """paths: list of Paths in priority order (default: fresh first, then legacy)."""
    if paths is not None:
        if isinstance(paths, (str, Path)):
            paths = [Path(paths)]
        else:
            paths = [Path(p) for p in paths]
    else:
        paths = [PAGES_JSONL, LEGACY_PAGES_JSONL]
    seen = set()
    for p in paths:
        for rec in _read(p):
            key = rec.get("dedupe_key") or (rec.get("url"), rec.get("page"), rec.get("type"))
            if key in seen:
                continue
            seen.add(key)
            yield rec
