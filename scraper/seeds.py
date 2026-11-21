"""
ALL LINKS TO SCRAPE LIVE HERE.  To add a page: add one line to SEEDS.

  name      short unique id (becomes the file name of the saved HTML snapshot)
  url       full URL (paste it from the browser address bar)
  category  hint only: general, leadership, academics, programs, policies,
            admissions, fees, intake, cutoffs, hods, faculty, contacts

RIT's pages use long encoded query strings that differ only in a few segments,
so the lines below are built with _rit(page, a, b, c, d). For a NEW page, you can
simply paste the full URL as {"name": ..., "url": "https://...", "category": ...}.

Check this file any time with:   python -m scraper.seeds
"""
from collections import defaultdict

WEB = "https://ritindia.edu/ritwebsite/website/"
ALLOWED_DOMAINS = {"ritindia.edu", "www.ritindia.edu"}   # PDFs/pages on other hosts are skipped

_Q0 = "aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_"
_MID = "_nZzaXNkY2JxdXNhNDZlM2Q3Nz_"

# suffix (last segment) is the same for every page of the same website section
_ACAD, _ADM, _LEAD = "NjMyMTgwNDE0ZDAzYw", "NjMyMTgwNmVjNTRjNg", "NjMyMTY3N2YyNWY3Yw"


def _rit(page, a, b, c, d):
    return f"{WEB}{page}?idsfvsisdcbqusa={_Q0}{a}{_MID}{b}_{c}_{d}"


def _s(name, category, url):
    return {"name": name, "category": category, "url": url.strip()}


SEEDS = [
    # ---------------- Academics ----------------
    _s("exam_schedule",         "academics", _rit("undergraduate.php", "MNjM0OGU5ZDA3NWUzMw", "6348ea525addc", 12, _ACAD)),
    _s("exam_details",          "contacts",  _rit("undergraduate.php", "MNjM0OGU5ZDA3NWUzMw", "6423e52f2a65d", 12, _ACAD)),
    _s("academic_calendar",     "academics", _rit("aboutus.php",       "MNjM0M2IwMDY0M2I0MQ", "",              12, _ACAD)),
    _s("programs_diploma",      "programs",  _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "6347de510181f", 12, _ACAD)),
    _s("programs_undergraduate","programs",  _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "6347ded53315c", 12, _ACAD)),
    _s("programs_postgraduate", "programs",  _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "6347df1dab97f", 12, _ACAD)),
    _s("programs_phd",          "programs",  _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "6364e67f1513a", 12, _ACAD)),
    _s("programs_management",   "programs",  _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "6666e8bbded61", 12, _ACAD)),
    _s("programs_working_prof", "programs",  _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "",              12, _ACAD)),
    _s("programs_computer_app",  "programs", _rit("undergraduate.php", "MNjM0M2FmN2JlNGVhYg", "675c1eb4a3f0f", 12, _ACAD)),
    _s("rules_regulations",     "policies",  _rit("aboutus.php",       "MNjQ5MmEzOWNkZmQ3OA", "",              12, _ACAD)),
    _s("curriculum",            "academics", _rit("aboutus.php",       "MNjUwZDFiOWZmMWEzNg", "",              12, _ACAD)),
    _s("courses_po_pso_co",     "academics", _rit("aboutus.php",       "MNjM0M2IwNGZkOWYyZg", "",              12, _ACAD)),

    # ---------------- Admissions ----------------
    # CHECK: this URL is called "fee_structure" in one script and "general_info" in the other.
    _s("fee_structure",         "fees",      _rit("aboutus.php",       "MNjNjNTE3YTFkYjI3Nw", "",              12, _ADM)),
    _s("admission_enquiry",     "admissions",_rit("admission.php",     "MNjMyNDAwMWYwNWFhZg", "",              12, _ADM)),
    _s("admission_faqs",        "admissions",_rit("aboutus.php",       "MNjMyNDQ4YjAwMTk0Zg", "",              12, _ADM)),
    _s("admission_ug_fy",       "admissions",_rit("undergraduate.php", "MNjMyNDE2MGQ4MTJmMA", "632452dadab82",  1,  _ADM)),
    _s("admission_ug_dsy",      "admissions",_rit("undergraduate.php", "MNjMyNDE2MGQ4MTJmMA", "6324530e2c85b",  2,  _ADM)),
    _s("admission_pg_fy",       "admissions",_rit("undergraduate.php", "MNjMyNDE2MTQ2MWQ0NQ", "",               12, _ADM)),
    _s("admission_pg_rules",    "admissions",_rit("undergraduate.php", "MNjMyNDE2MTQ2MWQ0NQ", "63c514cc18353",  12, _ADM)),
    _s("admission_diploma_fy",  "admissions",_rit("undergraduate.php", "MNjMyNDE2MjI0NjEwZQ", "6329b6a239675",  3,  _ADM)),
    _s("admission_diploma_dsy", "admissions",_rit("undergraduate.php", "MNjMyNDE2MjI0NjEwZQ", "6329b6b716a6a",  4,  _ADM)),
    _s("admission_mba",         "admissions",_rit("undergraduate.php", "MNjMyNDQxODBjNWQwYw", "69e3166b0a473",  12, _ADM)),
    _s("admission_bba",         "admissions",_rit("undergraduate.php", "MNjMyNDQxODBjNWQwYw", "69e31673152a8",  7,  _ADM)),

    # ---------------- From your institutional-info script ----------------
    _s("leadership_1",          "leadership",_rit("aboutus.php",       "MNjMyMmIxMGY3OTVmZg", "",              12, _LEAD)),
    _s("leadership_2",          "leadership",_rit("aboutus.php",       "MNjMyMTkwYzkyMGU2MQ", "",              12, _LEAD)),
    _s("fees_page",             "fees",      _rit("feestructure.php",  "MNjkzNjViNzJhOTIwYw", "",              12, _ADM)),
]

# ---------------- Department seeds from data/manual/hods.csv ----------------
import csv
from pathlib import Path
import re

HODS_CSV = Path(__file__).resolve().parent.parent / "data" / "manual" / "hods.csv"
if HODS_CSV.exists():
    with open(HODS_CSV, "r", encoding="utf-8-sig") as _f:
        for _row in csv.DictReader(_f):
            _dept = _row.get("Department", "").strip()
            _src = _row.get("source", "").strip()
            if _dept and _src:
                _slug = re.sub(r"[^a-zA-Z0-9]+", "_", _dept).strip("_").lower()
                _name = f"dept_{_slug}"
                if not any(s["name"] == _name for s in SEEDS):
                    SEEDS.append(_s(_name, "hods", _src))

# Additional department seeds (MBA, BBA, Automobile Engineering)
_EXTRA_DEPTS = [
    ("dept_mba", "hods", "https://www.ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2YTQyOWYwZg_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw"),
    ("dept_bba", "hods", "https://www.ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjY3YTkwZjhlMTI1Ng_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw"),
    ("dept_automobile_engineering", "hods", "https://www.ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjMyYWJlOGJkZDlkMQ_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw"),
]
for _n, _c, _u in _EXTRA_DEPTS:
    if not any(s["name"] == _n for s in SEEDS):
        SEEDS.append(_s(_n, _c, _u))


def duplicates():
    by_url = defaultdict(list)
    for s in SEEDS:
        by_url[s["url"]].append(s["name"])
    return {u: n for u, n in by_url.items() if len(n) > 1}


if __name__ == "__main__":
    names = [s["name"] for s in SEEDS]
    assert len(names) == len(set(names)), "duplicate seed names"
    print(f"{len(SEEDS)} seeds, {len(set(s['url'] for s in SEEDS))} unique URLs")
    for u, n in duplicates().items():
        print(f"  DUPLICATE URL shared by: {', '.join(n)}")
    from urllib.parse import urlparse
    bad = [s["name"] for s in SEEDS if urlparse(s["url"]).netloc not in ALLOWED_DOMAINS]
    print("  Seeds outside ALLOWED_DOMAINS:", bad or "none")
