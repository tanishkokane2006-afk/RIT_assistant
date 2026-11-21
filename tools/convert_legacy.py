"""
Convert the OLD project folder (rit_data_collection) into rit_assistant_v3 formats.

    python -m tools.convert_legacy --src ../rit_data_collection [--force]

Writes (nothing is invented; every value is copied verbatim from the old files):
  data/raw/legacy_pages.jsonl          pages + PDF pages in the v3 record schema
  data/raw/pdf_registry.legacy.json    every PDF + text/mixed/image classification
  data/manual/*.csv                    fees, cutoffs (summary), hods, contacts, pdf_links
  data/legacy_quarantine/*.json        data we did NOT index because its meaning is unclear
  data/CONVERSION_REPORT.md            counts, warnings, things to verify
  tests/legacy_questions.csv           the old question list (reference)

Never read/copied: .env, usage.db, suggestions.json (personal data), old embeddings, caches.
Existing manual CSVs with content are never overwritten unless --force
(the new file is written as <name>.generated.csv instead).
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

try:
    import config
    ROOT, DATA = config.ROOT, config.DATA
    MIN_CHARS = getattr(config, "PDF_MIN_TEXT_CHARS", 100)
except Exception:                                                     # pragma: no cover
    ROOT = Path(__file__).resolve().parents[1]
    DATA, MIN_CHARS = ROOT / "data", 100
try:
    from scraper.seeds import SEEDS
    SEED_CAT = {s["name"]: s["category"] for s in SEEDS}
except Exception:                                                     # pragma: no cover
    SEED_CAT = {}

RAW, MANUAL, QUAR = DATA / "raw", DATA / "manual", DATA / "legacy_quarantine"
WEBSITE = "https://ritindia.edu"
CAT_OVERRIDE = {"exam_details": "contacts"}   # that page is the exam-coordinator contact list
NUMCELL = re.compile(r"^\(?-?\d[\d.,/]*\)?$")
SKIP_VALUES = {"", "not found", "n/a", "none"}


# ------------------------------------------------------------------ helpers
def norm(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\xa0", " ")).strip()


def sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def load_json(path, repairs):
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repairs.append(f"{Path(path).name}: removed {text.index('{')} stray character(s) before the JSON")
        return json.loads(text[text.index("{"):])


def human(name):
    return name.replace("_", " ").replace("-", " ").strip()


def label(key):
    k = key.replace("_", " ").strip()
    return k[:1].upper() + k[1:]


def fused_count(strings):
    return sum(len(re.findall(r"[a-z][A-Z]", s)) for s in strings)


# ------------------------------------------------------------------ tables
def convert_table(data):
    """old table 'data' (list of rows, may contain None) -> (rows, header_rows, context, prose_lines)"""
    if data and isinstance(data[0], dict):                      # processed-style records
        keys = list(data[0].keys())
        data = [keys] + [[d.get(k) for k in keys] for d in data]
    rows = [[norm(c) for c in r] for r in data]
    rows = [r for r in rows if any(r)]
    if rows and max(sum(1 for c in r if c) for r in rows) <= 1:       # one text cell per row = prose
        return None, 0, "", [c for r in rows for c in r if c]
    context = ""
    while len(rows) > 1 and len({c for c in rows[0] if c}) == 1:      # title-only row -> context
        context = next(c for c in rows[0] if c)
        rows.pop(0)
    if len(rows) < 2:
        return None, 0, context, []
    n = 1
    if len(rows) > 2 and rows[0][0] and not rows[1][0]:               # multi-row header (rowspan)
        while n < 3 and n < len(rows) - 1 and not rows[n][0] and not any(NUMCELL.match(c) for c in rows[n]):
            n += 1
    return rows, n, context, []


def table_record(idx, rows, header_rows, context):
    return {"index": idx, "context": context[:200], "header_rows": header_rows, "rows": rows}


# ------------------------------------------------------------------ HTML pages
def convert_pages(src, repairs):
    recs, by_url, report = [], {}, {"empty": [], "fused": [], "aliases": []}
    order = {n: i for i, n in enumerate(SEED_CAT)}
    files = [f for f in (src / "data" / "raw").glob("*.json") if not f.name.lower().startswith("pdf_")]
    for f in sorted(files, key=lambda f: (order.get(f.stem, 10_000), f.name)):
        try:
            j = load_json(f, repairs)
        except Exception:
            continue
        md = j.get("metadata", {}) if isinstance(j, dict) else {}
        if "page_name" not in md or "tables" not in j:
            continue
        name, url = md["page_name"], md["url"].strip()
        if url in by_url:
            by_url[url]["aliases"].append(name)
            report["aliases"].append((name, by_url[url]["name"]))
            continue
        tables, prose = [], []
        for t in j["tables"]:
            rows, hr, ctx, lines = convert_table(t.get("data", []))
            prose += lines
            if rows:
                tables.append(table_record(len(tables), rows, hr, ctx))
        text = "\n".join(prose)
        notes = ["old scraper kept TABLES ONLY: page text was never captured - re-scrape with scraper.crawl"]
        if not text and not tables:
            report["empty"].append(name)
            notes.append("no table found: page may be an image, a PDF link or JavaScript-loaded")
        cells = prose + [c for t in tables for r in t["rows"] for c in r]
        if fused_count(cells) > 3:
            report["fused"].append(name)
            notes.append("words are fused together (old scraper used get_text(strip=True)) - re-scrape")
        rec = {"id": sha1(url)[:12], "name": name, "aliases": [], "url": url,
               "category": CAT_OVERRIDE.get(name, SEED_CAT.get(name, "general")),
               "type": "html", "title": human(name).title(), "title_source": "derived_from_name",
               "page": 1, "text": text, "tables": tables, "pdf_links": [],
               "content_sha1": sha1(text + json.dumps(tables)), "scraped_at": md.get("scraped_date", ""),
               "origin": "legacy_scrape", "needs_rescrape": True, "notes": notes}
        by_url[url] = rec
        recs.append(rec)
    return recs, report


# ------------------------------------------------------------------ PDFs
def pdf_category(name):
    n = name.lower()
    if "cutoff" in n or "cut-off" in n:
        return "cutoffs"
    if "calender" in n or "calendar" in n or "po-pso" in n:
        return "academics"
    return "admissions"


def garbled(text):
    return bool(text) and text.count("(cid:") * 6 / len(text) > 0.3


def page_has_text(text, tables):
    return bool(tables) or (len(text) >= MIN_CHARS and not garbled(text))


def pdf_context(text, title_ctx):
    if title_ctx:
        return title_ctx
    lines = [norm(l) for l in text.split("\n") if norm(l)]
    for l in lines:
        if re.search(r"cut\s*-?\s*off", l, re.I):
            return l
    return lines[0] if lines else ""


def convert_pdfs(src, repairs):
    reg_path = src / "data" / "raw" / "PDF_REGISTRY.backup.json"      # the 20-PDF version (has the brochure URL)
    if not reg_path.exists():
        reg_path = src / "data" / "raw" / "PDF_REGISTRY.json"
    old_reg = load_json(reg_path, repairs)
    url_of = {}
    for g in ("text_based", "image_based", "mixed"):
        for p in old_reg.get(g, {}).get("pdfs", []):
            url_of.setdefault(p["name"], p["url"])

    recs, registry, skipped = [], [], []
    for f in sorted((src / "data" / "raw").glob("pdf_*.json")):
        if f.name in ("pdf_extraction_summary.json", "pdf_test_debug.json"):
            skipped.append(f.name)
            continue
        j = load_json(f, repairs)
        if j.get("type") != "pdf_document":
            continue
        pname = j["pdf_name"]
        url = url_of.get(pname)
        if not url:
            skipped.append(f"{f.name} (no URL in registry)")
            continue
        cat, title = pdf_category(pname), human(pname)
        pages, flags, img_pages = [], [], []
        for pg in j["pages"]:
            text = (pg.get("text") or "").strip()
            tables, title_ctx = [], ""
            for t in pg.get("tables", []):
                rows, hr, ctx, _ = convert_table(t.get("data", []))
                if rows:
                    title_ctx = title_ctx or ctx
                    tables.append((rows, hr, ctx))
            ok = page_has_text(text, tables)
            flags.append(ok)
            if not ok:
                img_pages.append(pg["page"])
                continue
            tr = [table_record(i, rows, hr, pdf_context(text, ctx)) for i, (rows, hr, ctx) in enumerate(tables)]
            pages.append((pg["page"], text, tr))
        pdf_type = "image" if not any(flags) else ("text" if all(flags) else "mixed")
        if pdf_type != "image":
            for page_no, text, tr in pages:
                recs.append({"id": f"{sha1(url)[:10]}-p{page_no}", "name": f"legacy::pdf::{pname}", "url": url,
                             "parent": "legacy", "category": cat, "type": "pdf", "pdf_type": pdf_type,
                             "title": title, "page": page_no, "text": text, "tables": tr,
                             "content_sha1": sha1(text + json.dumps(tr)), "scraped_at": j.get("scraped_date", ""),
                             "origin": "legacy_scrape"})
        if pdf_type != "text":
            t = f"{title}. PDF document available at this link."
            recs.append({"id": f"{sha1(url)[:10]}-link", "name": f"legacy::pdf::{pname}", "url": url,
                         "parent": "legacy", "category": cat, "type": "pdf_link", "pdf_type": pdf_type,
                         "title": title, "page": 0, "text": t, "tables": [], "content_sha1": sha1(t),
                         "scraped_at": j.get("scraped_date", ""), "origin": "legacy_scrape"})
        registry.append({"url": url, "title": title, "file": pname, "category": cat, "pdf_type": pdf_type,
                         "pages": len(j["pages"]), "text_pages": sum(flags), "image_pages": img_pages,
                         "action": {"text": "parsed", "mixed": "parsed_text_pages+link", "image": "link_only"}[pdf_type],
                         "origin": "legacy_scrape"})
    return recs, registry, skipped, url_of


# ------------------------------------------------------------------ curated + departments
def flatten(obj, prefix=""):
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lines += flatten(v, f"{prefix} - {label(k)}" if prefix else label(k))
    elif isinstance(obj, list):
        for it in obj:
            lines += flatten(it, prefix)
    elif obj is not None:
        s = norm(obj)
        if s.lower() not in SKIP_VALUES:
            lines.append(f"{prefix}: {s}")
    return lines


def doc(name, title, category, url, lines, origin, when=""):
    text = "\n".join(lines)
    return {"id": sha1(name)[:12], "name": name, "aliases": [], "url": url, "category": category,
            "type": "html", "title": title, "page": 1, "text": text, "tables": [], "pdf_links": [],
            "content_sha1": sha1(text), "scraped_at": when, "origin": origin,
            "dedupe_key": name}           # several curated docs share one URL, so URL alone is not unique


def curated_docs_and_csvs(src, out_manual):
    ii = json.loads((src / "data" / "raw" / "institute_info.json").read_text(encoding="utf-8"))
    docs = []
    for sec, cat in (("institution", "institute_info"), ("leadership", "leadership"),
                     ("facilities", "facilities"), ("placements", "placements")):
        if sec in ii:
            docs.append(doc(f"curated::{sec}", f"RIT information - {label(sec)}", cat, WEBSITE,
                            flatten(ii[sec]), "curated:institute_info.json"))
    for key, val in ii.get("admission_details", {}).items():
        docs.append(doc(f"curated::admission::{key}", f"RIT admission details - {label(key)}", "admissions",
                        WEBSITE, flatten(val), "curated:institute_info.json"))

    CUR = "institute_info.json (curated)"
    # fees
    fees = []
    for prog, v in ii.get("fee_structure", {}).items():
        fees.append({"Program": prog.upper() if prog != "btech" else "B.Tech",
                     "Annual Tuition Fee (INR)": str(v.get("annual_tuition_fee", "")),
                     "Fee Details": v.get("details", ""),
                     "context": "Curated summary - academic year not stated in source", "source": CUR})
        for q, txt in v.get("quotawise_fees", {}).items():
            fees.append({"Program": "B.Tech", "Category": label(q), "Fee Details": txt,
                         "context": "Curated summary - academic year not stated in source", "source": CUR})
    # cutoff summary
    cut = [{"Course": c["course"], "Duration": c.get("duration", ""), "Seats": str(c.get("seats", "")),
            "Cutoff Percentile": str(c.get("cutoff_percentile", "")), "Cutoff Rank": str(c.get("cutoff_rank", "")),
            "context": "Curated summary - academic year, CAP round and category NOT stated in source",
            "source": CUR} for c in ii.get("program_cutoffs", [])]
    # contacts
    c = ii.get("institution", {}).get("contact", {})
    contacts = [{"Contact For": "Institute (general, as listed in curated data)", "Telephone": c.get("telephone", ""),
                 "Mobile": c.get("mobile", ""), "Email": c.get("email", ""), "Website": c.get("website", ""),
                 "source": CUR}] if c else []
    return docs, ii, {"fees": fees, "cutoffs": cut, "contacts": contacts}


def departments(src, repairs):
    d = load_json(src / "data" / "raw" / "departments_info.json", repairs)
    docs, hods, quarantine = [], [], []
    for x in d["departments"]:
        name, hod, url = norm(x["department_name"]), norm(x.get("hod_name")), x["url"].strip()
        lines = [f"Department: {name}"]
        if hod.lower() not in SKIP_VALUES:
            lines.append(f"Head of Department (HOD): {hod}")
            hods.append({"Department": name, "HOD Name": hod, "source": url})
        if norm(x.get("hod_message")):
            lines.append(f"HOD message: {norm(x['hod_message'])}")
        docs.append(doc(f"department::{name}", f"Department of {name}", "departments", url, lines,
                        "legacy_scrape:departments_info.json", d["metadata"].get("scraped_date", "")))
        quarantine.append({"department": name, "url": url, "stats": x.get("stats"), "placements": x.get("placements")})
    return docs, hods, quarantine, d["departments"]


# ------------------------------------------------------------------ consistency check
def key(s):
    s = s.lower().replace("&", "and").replace("tele-communication", "telecommunication")
    return re.sub(r"[^a-z0-9]", "", s)


def seat_check(pages, curated_ii):
    scraped = {}
    for p in pages:
        for t in p["tables"]:
            head = " ".join(t["rows"][0]).lower()
            if "sanctioned" in head or "intake" in head:
                for r in t["rows"][1:]:
                    nums = [c for c in r if c.isdigit()]
                    names = [c for c in r if c and not c.isdigit() and c.lower() not in ("total", "ug total")]
                    if nums and names:
                        keys = {key(names[0])} | {key(m) for m in re.findall(r"\(([^)]*)\)", names[0])}
                        for k in keys:
                            scraped.setdefault(k, set()).add(nums[-1])
    ok, bad, miss = [], [], []
    for c in curated_ii.get("program_cutoffs", []):
        k, seats = key(c["course"]), str(c.get("seats"))
        if k in scraped:
            (ok if seats in scraped[k] else bad).append((c["course"], seats, sorted(scraped[k])))
        else:
            miss.append(c["course"])
    return ok, bad, miss


# ------------------------------------------------------------------ writing
def write_csv(name, rows, force, notes):
    if not rows:
        return
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    path = MANUAL / name
    if path.exists() and not force and len([l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]) > 1:
        path = MANUAL / name.replace(".csv", ".generated.csv")
        notes.append(f"{name} already has content -> wrote {path.name} instead (use --force to overwrite)")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="path to the old rit_data_collection folder")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    src = Path(a.src).resolve()
    for d in (RAW, MANUAL, QUAR, ROOT / "tests"):
        d.mkdir(parents=True, exist_ok=True)
    repairs, notes = [], []

    pages, prep = convert_pages(src, repairs)
    pdf_recs, registry, skipped, url_of = convert_pdfs(src, repairs)
    cdocs, ii, csvs = curated_docs_and_csvs(src, MANUAL)
    ddocs, hods, quarantine, _ = departments(src, repairs)
    ok, bad, miss = seat_check(pages, ii)

    all_recs = pages + pdf_recs + cdocs + ddocs
    with open(RAW / "legacy_pages.jsonl", "w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (RAW / "pdf_registry.legacy.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    (QUAR / "department_stats.json").write_text(json.dumps(quarantine, indent=2, ensure_ascii=False), encoding="utf-8")

    # manual CSVs
    csvs["hods"] = hods
    links = [{"title": r["title"], "url": r["url"], "category": r["category"], "description": ""}
             for r in registry if r["pdf_type"] == "image"]
    res = src / "data" / "resources.json"
    link_only_missing = []
    if res.exists():
        for r in json.loads(res.read_text(encoding="utf-8")):
            if r.get("category") == "link_only":
                if r.get("url"):
                    links.append({"title": r["name"], "url": r["url"], "category": "admissions", "description": ""})
                else:
                    link_only_missing.append(r["name"])
    csvs["pdf_links"] = links
    for name, rows in csvs.items():
        write_csv(f"{name}.csv", rows, a.force, notes)
    q = src / "test_questions.csv"
    if q.exists():
        shutil.copy(q, ROOT / "tests" / "legacy_questions.csv")

    # ---- report
    types = Counter(r["pdf_type"] for r in registry)
    L = ["# Legacy data conversion report", "",
         f"Source: `{src.name}`", "",
         "## What was produced", "",
         f"- `data/raw/legacy_pages.jsonl`: {len(all_recs)} records "
         f"({len(pages)} web pages, {sum(r['type']=='pdf' for r in pdf_recs)} PDF pages, "
         f"{sum(r['type']=='pdf_link' for r in pdf_recs)} PDF link stubs, {len(cdocs)} curated info docs, "
         f"{len(ddocs)} department docs)",
         f"- `data/raw/pdf_registry.legacy.json`: {len(registry)} PDFs -> {dict(types)}",
         "- `data/manual/`: " + ", ".join(f"{n}.csv ({len(r)} rows)" for n, r in csvs.items() if r),
         f"- tables kept: {sum(len(p['tables']) for p in pages)} web, {sum(len(p['tables']) for p in pdf_recs)} PDF", "",
         "## Repairs / duplicates", ""]
    L += [f"- {r}" for r in repairs] or ["- none"]
    L += [f"- `{al}` has the same URL as `{orig}` (kept as alias, not duplicated)" for al, orig in prep["aliases"]]
    L += ["", "## Pages that need a re-scrape (python -m scraper.crawl)", "",
          "ALL legacy web pages: the old scraper stored tables only, never the page text.", "",
          f"- no content at all (image / PDF-only / JavaScript?): {', '.join(prep['empty']) or 'none'}",
          f"- words fused together in cells: {', '.join(prep['fused']) or 'none'}", "",
          "## Verify before trusting (curated `institute_info.json`)", "",
          "- fees.csv, cutoffs.csv (percentile/rank with NO year, round or category), contacts.csv and the "
          "`curated::*` docs come from `institute_info.json`, which is not tied to a page URL. Check them against "
          "the official documents; fix by editing the CSVs.",
          f"- seat counts vs the scraped intake tables: {len(ok)} match, {len(bad)} differ, {len(miss)} not comparable"]
    L += [f"  - DIFFERS: {c} curated={s} scraped={sc}" for c, s, sc in bad]
    L += [f"  - not comparable (no matching scraped row): {', '.join(miss)}" if miss else "",
          "- HODs: " + "; ".join(f"{h['Department']} = {h['HOD Name']}" for h in hods
                                 if h["HOD Name"] == "Dr. S. R. Desai") + " -> same name for two departments, confirm.",
          "- the only contact data is one general number and `director@ritindia.edu`; there is NO admission-office "
          "contact in the data (the old test questions Q05/Q06 expect one).",
          "", "## Not indexed (quarantined / excluded)", "",
          "- `legacy_quarantine/department_stats.json`: counters like '15 HIGHEST SALARY PACKAGE' / '190 RECRUITERS' "
          "have no unit or scope and repeat across departments; not used as facts.",
          "- excluded on purpose: `.gitignore/.env` (secrets - rotate any key in it if it was shared), "
          "`usage.db` (usage counters), `suggestions.json` (names + IP addresses), old embeddings "
          "(different pipeline), `__pycache__`, old logs.",
          f"- not converted: {', '.join(skipped) or 'none'}",
          f"- links with no URL in `resources.json` (add them to pdf_links.csv): {', '.join(link_only_missing) or 'none'}"]
    (DATA / "CONVERSION_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    for n in notes:
        print("NOTE:", n)


if __name__ == "__main__":
    main()
