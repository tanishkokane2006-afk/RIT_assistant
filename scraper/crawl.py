"""
Scrape every seed in scraper/seeds.py  ->  data/raw/pages.jsonl

For each page it keeps: full page TEXT, every TABLE (as exact strings), and it
downloads + parses any PDF linked from the page. Raw HTML is saved untouched in
data/raw/html/ so you can re-parse later without hitting the website again.

Run from the project root:
    python -m scraper.crawl                    # everything
    python -m scraper.crawl --check            # dry run: fetch + report, save nothing
    python -m scraper.crawl --only fee_structure,fees_page
    python -m scraper.crawl --no-pdfs
"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import pdfplumber
import requests
import urllib3
from bs4 import BeautifulSoup

import config
from scraper.seeds import SEEDS, ALLOWED_DOMAINS
from scraper.tables import norm, table_to_rows, render_table

if not config.VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

session = requests.Session()
session.headers.update({
    "User-Agent": config.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
})
_robots = {}


# --------------------------------------------------------------------------
# networking
# --------------------------------------------------------------------------
def robots_ok(url):
    if not config.RESPECT_ROBOTS:
        return True
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
            _robots[base] = rp
        except Exception:
            _robots[base] = None          # robots.txt unreachable -> allow
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(config.USER_AGENT, url)


def get(url):
    last = None
    for attempt in range(config.RETRIES):
        try:
            r = session.get(url, timeout=config.REQUEST_TIMEOUT, verify=config.VERIFY_SSL)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            code = getattr(e.response, "status_code", None)
            if code is not None and code < 500:      # 404/403 etc: retrying won't help
                break
            time.sleep(2 ** attempt)
    raise last


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def parse_html(url, content):
    soup = BeautifulSoup(content, "html.parser")
    title = norm(soup.title.get_text()) if soup.title else ""

    pdf_links = {}
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(url, a["href"].strip()))[0]
        pu = urlparse(href)
        if pu.path.lower().endswith(".pdf") and pu.netloc in ALLOWED_DOMAINS:
            pdf_links.setdefault(href, norm(a.get_text(" ")))

    tables = []
    for t in soup.find_all("table"):
        if t.find("table"):                 # outer layout table: handle its inner tables instead
            continue
        rows, header_rows = table_to_rows(t)
        if len(rows) < 2 or max(len(r) for r in rows) < 2:
            continue
        cap = t.find("caption")
        prev = t.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"])
        ctx = norm(cap.get_text(" ")) if cap else (norm(prev.get_text(" ")) if prev else "")
        tables.append({"index": len(tables), "context": ctx[:200],
                       "header_rows": header_rows, "rows": rows})
        t.replace_with(soup.new_string("\n" + render_table(rows, header_rows) + "\n"))

    for tag in soup(["script", "style", "noscript", "nav", "footer", "form", "iframe", "svg"]):
        tag.decompose()

    lines, last = [], None
    for ln in soup.get_text("\n").splitlines():
        ln = norm(ln)
        if ln and ln != last:
            lines.append(ln)
        last = ln
    return title, "\n".join(lines), tables, pdf_links


def parse_pdf(path):
    """Yield (page_no, text, tables) per page. Scanned pages come back empty."""
    out = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = (page.extract_text() or "").strip()
            first = norm(text.split("\n")[0])[:200] if text else ""
            tables = []
            for tb in page.extract_tables():
                rows = [[norm(c or "") for c in r] for r in tb if r and any(r)]
                if len(rows) >= 2:
                    tables.append({"index": len(tables), "context": first,
                                   "header_rows": 1, "rows": rows})
            out.append((i, text, tables))
    return out


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def sha1(s):
    return hashlib.sha1(s if isinstance(s, bytes) else s.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80]


def handle_pdf(url, label, parent, category, dry):
    """Download + parse one PDF -> list of page records."""
    r = get(url)
    if len(r.content) > config.MAX_PDF_MB * 1024 * 1024:
        print(f"      ! skipped (over {config.MAX_PDF_MB} MB): {url}")
        return []
    path = config.PDF_DIR / (sha1(url)[:16] + ".pdf")
    if not dry:
        path.write_bytes(r.content)
    else:
        path = config.PDF_DIR / "_check_tmp.pdf"
        path.write_bytes(r.content)
    base = label or urlparse(url).path.rsplit("/", 1)[-1]
    recs, empty = [], 0
    for page_no, text, tables in parse_pdf(path):
        if not text and not tables:
            empty += 1
            continue
        recs.append({"id": f"{sha1(url)[:10]}-p{page_no}", "name": f"{parent}::pdf::{safe_name(base)}",
                     "url": url, "parent": parent, "category": category, "type": "pdf",
                     "title": base, "page": page_no, "text": text, "tables": tables,
                     "content_sha1": sha1(text + json.dumps(tables)), "scraped_at": now()})
    if empty:
        print(f"      ! {empty} page(s) had no extractable text (scanned image?) - needs OCR: {url}")
    if dry and path.name == "_check_tmp.pdf":
        path.unlink(missing_ok=True)
    return recs


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def run(only=None, with_pdfs=True, dry=False):
    seeds = [s for s in SEEDS if not only or s["name"] in only]
    if not seeds:
        raise SystemExit("No matching seeds.")
    records, log = [], []
    by_url, seen_pdfs, text_hashes = {}, set(), {}
    t0 = time.time()
    print(f"Scraping {len(seeds)} seeds {'(dry run)' if dry else ''}\n")

    for i, s in enumerate(seeds, 1):
        name, url, cat = s["name"], s["url"], s["category"]
        print(f"[{i}/{len(seeds)}] {name}")
        entry = {"name": name, "url": url, "status": "pending"}

        if not url or not url.strip():
            print(f"   ! seed {name} has no URL (skipped)")
            entry.update(status="blocked", error="seed has no URL")
            log.append(entry)
            continue

        if url in by_url:
            by_url[url]["aliases"].append(name)
            entry.update(status="duplicate", duplicate_of=by_url[url]["name"])
            print(f"   = same URL as '{by_url[url]['name']}', skipped (kept as alias)")
            log.append(entry)
            continue
        if not robots_ok(url):
            entry.update(status="blocked_by_robots")
            print("   x blocked by robots.txt")
            log.append(entry)
            continue

        try:
            resp = get(url)
            ctype = resp.headers.get("content-type", "").lower()
            if urlparse(url).path.lower().endswith(".pdf") or "application/pdf" in ctype:
                recs = handle_pdf(url, name, name, cat, dry)
                records.extend(recs)
                entry.update(status="ok", type="pdf", pages=len(recs))
                print(f"   ok  PDF, {len(recs)} page(s) with content")
                log.append(entry)
                time.sleep(config.CRAWL_DELAY)
                continue

            if not dry:
                (config.RAW_HTML_DIR / f"{safe_name(name)}.html").write_bytes(resp.content)
            title, text, tables, pdf_links = parse_html(url, resp.content)
            rec = {"id": sha1(url)[:12], "name": name, "aliases": [], "url": url,
                   "category": cat, "type": "html", "title": title or name, "page": 1,
                   "text": text, "tables": tables, "pdf_links": list(pdf_links),
                   "content_sha1": sha1(text + json.dumps(tables)), "scraped_at": now()}
            by_url[url] = rec
            if rec["content_sha1"] in text_hashes:
                print(f"   ~ identical content to '{text_hashes[rec['content_sha1']]}' (different URL)")
            text_hashes.setdefault(rec["content_sha1"], name)
            records.append(rec)
            entry.update(status="ok", type="html", chars=len(text),
                         tables=len(tables), pdf_links=len(pdf_links))
            print(f"   ok  {len(text)} chars, {len(tables)} table(s), {len(pdf_links)} PDF link(s)")
            if len(text) < 200 and not tables:
                print("   ! almost no content - page may be loaded by JavaScript or the link expired")

            if with_pdfs and config.FOLLOW_PDF_LINKS:
                for purl, label in list(pdf_links.items())[:config.MAX_PDFS_PER_PAGE]:
                    if purl in seen_pdfs or not robots_ok(purl):
                        continue
                    seen_pdfs.add(purl)
                    time.sleep(config.CRAWL_DELAY)
                    try:
                        recs = handle_pdf(purl, label, name, cat, dry)
                        records.extend(recs)
                        print(f"      pdf '{label or purl[-40:]}': {len(recs)} page(s)")
                    except Exception as e:
                        print(f"      ! pdf failed {purl[-60:]}: {e}")
        except Exception as e:
            entry.update(status="failed", error=str(e))
            print(f"   FAILED: {e}")
        log.append(entry)
        time.sleep(config.CRAWL_DELAY)

    ok = sum(1 for e in log if e["status"] == "ok")
    fail = [e["name"] for e in log if e["status"] == "failed"]
    print("\n" + "=" * 60)
    print(f"Done in {time.time() - t0:.0f}s | ok {ok} | failed {len(fail)} | "
          f"duplicates {sum(1 for e in log if e['status'] == 'duplicate')}")
    print(f"Records: {len(records)} "
          f"({sum(1 for r in records if r['type'] == 'html')} pages, "
          f"{sum(1 for r in records if r['type'] == 'pdf')} PDF pages) | "
          f"tables: {sum(len(r['tables']) for r in records)}")
    if fail:
        print("Failed:", ", ".join(fail))

    if dry:
        print("(dry run: nothing saved)")
        return
    with open(config.PAGES_JSONL, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(config.SCRAPE_LOG, "w", encoding="utf-8") as f:
        json.dump({"finished": now(), "seeds": log}, f, indent=2, ensure_ascii=False)
    print(f"Saved {config.PAGES_JSONL}\nLog   {config.SCRAPE_LOG}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated seed names")
    ap.add_argument("--no-pdfs", action="store_true")
    ap.add_argument("--check", action="store_true", help="dry run, save nothing")
    a = ap.parse_args()
    run(only=set(a.only.split(",")) if a.only else None, with_pdfs=not a.no_pdfs, dry=a.check)