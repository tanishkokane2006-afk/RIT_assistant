"""Checks the converted legacy data. Run: python -m tests.test_legacy_import
(needs data/raw/legacy_pages.jsonl produced by tools.convert_legacy)"""
import csv
import json

import config
from scraper.pages_io import iter_pages, LEGACY_PAGES_JSONL

recs = list(iter_pages([LEGACY_PAGES_JSONL]))
by_name = {}
for r in recs:
    by_name.setdefault(r["name"], []).append(r)
REQUIRED = {"id", "name", "url", "category", "type", "title", "page", "text", "tables", "content_sha1"}

# 0) nothing lost by the loader (curated docs share one URL)
assert len(recs) == sum(1 for _ in open(LEGACY_PAGES_JSONL, encoding="utf-8")), "iter_pages dropped records"

# 1) schema
for r in recs:
    assert REQUIRED <= set(r), (r["name"], REQUIRED - set(r))
    assert r["type"] in ("html", "pdf", "pdf_link")
    json.dumps(r)                                       # valid JSON, no NaN
    for t in r["tables"]:
        assert t["rows"] and t["header_rows"] >= 1 and all(isinstance(c, str) for row in t["rows"] for c in row)

# 2) values copied untouched
intake = next(t for t in by_name["programs_undergraduate"][0]["tables"] if t["rows"][0][-1] == "Intake Capacity")
assert ["2", "Computer Engineering", "180"] in intake["rows"]
fees = {r["Program"] + "|" + r.get("Category", ""): r for r in csv.DictReader(open(config.MANUAL_DIR / "fees.csv", encoding="utf-8-sig"))}
assert fees["B.Tech|"]["Annual Tuition Fee (INR)"] == "136522"

# 3) cut-off PDF: multi-row header kept, title in context, '(85.57)'-style cells untouched
fy = [r for r in recs if r["name"].endswith("FY-BTech-CutOff-2025-26") and r["type"] == "pdf"]
t = fy[0]["tables"][0]
assert t["header_rows"] == 2 and "Cut off" in t["context"], (t["header_rows"], t["context"])
assert any("(85.57)" in row for row in t["rows"])
assert t["rows"][0][0] == "Branch" and t["rows"][1][0] == ""

# 4) image PDFs: link only, nothing parsed
cal = by_name["legacy::pdf::academic-calender-Sem-I-2026-27"]
assert [r["type"] for r in cal] == ["pdf_link"] and cal[0]["pdf_type"] == "image"
assert not any(r["type"] == "pdf" for r in by_name["legacy::pdf::RIT-Information-Brochure-2025"])

# 5) mixed PDF: text pages + a link record
mba = by_name["legacy::pdf::MBA-CutOff-List-2025-26"]
assert {r["type"] for r in mba} == {"pdf", "pdf_link"} and mba[0]["pdf_type"] == "mixed"

# 6) duplicates aliased, secrets/PII never copied
assert by_name["programs_management"][0]["aliases"] == ["programs_working_prof"]
blob = LEGACY_PAGES_JSONL.read_text(encoding="utf-8")
assert "127.0.0.1" not in blob and "Tanish" not in blob

# 7) exam-coordinator page routed to contacts
assert by_name["exam_details"][0]["category"] == "contacts"
print(f"legacy import OK: {len(recs)} records")
