"""
Normaliser: HTML/PDF tables from pages.jsonl -> structured records.jsonl and SQLite table.

Run from project root:
    python -m normaliser.records
"""

import csv
import hashlib
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

import config
from scraper.pages_io import iter_pages
from scraper.tables import norm, combined_header

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("normaliser.records")

def is_sr_no_col(name: str) -> bool:
    """Detect serial number column headers like 'Sr. No.', 'S.No.', 'Sl. No.'."""
    cleaned = re.sub(r"[^a-zA-Z]", "", name).lower()
    return cleaned in {"srno", "sno", "slno", "sr", "serialno", "sn", "sno."}

def classify_table(headers: List[str], page_category: str) -> Optional[str]:
    """
    Classify a table according to config.TABLE_SIGNATURES.
    A record type is eligible ONLY IF the header text contains one of its signature words.
    Page category breaks ties (+2).
    Returns matched record type or None if unclassifiable.
    """
    header_text = " ".join(headers).lower()
    scores: Dict[str, int] = {}

    for r_type in config.RECORD_TYPES:
        signatures = config.TABLE_SIGNATURES.get(r_type, [])
        matches = 0
        for sig in signatures:
            if sig.lower() in header_text:
                matches += 1

        if matches > 0:
            score = matches
            if page_category and page_category.lower() == r_type.lower():
                score += 2
            scores[r_type] = score

    if not scores:
        return None

    # Pick type with the highest score
    best_type = max(scores.items(), key=lambda x: x[1])[0]
    return best_type

def record_to_text(record_type: str, context: str, data: Dict[str, str]) -> str:
    """
    Convert a structured record to a single descriptive sentence.
    Used by the indexer for embedding and by the answer formatter for display.
    """
    kv_pairs = [f"{k}: {v}" for k, v in data.items() if v]
    details = ", ".join(kv_pairs)
    prefix = f"[{record_type.upper()}]"
    if context:
        return f"{prefix} {context} - {details}" if details else f"{prefix} {context}"
    return f"{prefix} {details}" if details else prefix

def get_entity_match_key(r_type: str, context: str, data: Dict[str, str]) -> str:
    """
    Identify an entity within a table context (e.g. branch, category, faculty name).
    Used so manual rows can override matching scraped rows.
    """
    non_numeric_pairs = []
    for k, v in data.items():
        clean_v = re.sub(r"[,\s₹$%-]", "", v)
        if not clean_v.isdigit():
            non_numeric_pairs.append((k.lower(), v.lower()))

    ctx_norm = norm(context).lower()
    if non_numeric_pairs:
        ident = "|".join(f"{k}={v}" for k, v in sorted(non_numeric_pairs))
    else:
        ident = "|".join(f"{k.lower()}={v.lower()}" for k, v in sorted(data.items()))

    return f"{r_type}|{ctx_norm}|{ident}"

def generate_record_id(r_type: str, context: str, data: Dict[str, str]) -> str:
    """Generate a stable unique ID for a record."""
    serialized = json.dumps(data, sort_keys=True)
    raw = f"{r_type}|{norm(context).lower()}|{serialized}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

def is_title_only_row(cells: List[str]) -> Tuple[bool, str]:
    """
    Check if a row is title-only: all non-empty cells have the identical string.
    Returns (is_title, title_text).
    """
    non_empty = [norm(c) for c in cells if norm(c)]
    if not non_empty:
        return False, ""
    first = non_empty[0]
    if all(c == first for c in non_empty):
        return True, first
    return False, ""

def process_table(
    table: Dict[str, Any],
    source_url: str,
    page_no: int,
    page_title: str,
    page_category: str,
    page_name: str = ""
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Process a single table object.
    Returns: (list_of_records, unclassified_table_entry_or_None)
    """
    raw_rows = table.get("rows", [])
    header_rows_count = table.get("header_rows", 1)

    if not raw_rows:
        return [], None

    # Adjust if header_rows wrongly absorbed the data row
    if header_rows_count >= len(raw_rows) and len(raw_rows) > 1 and raw_rows[-1][0].strip().isdigit():
        header_rows_count = 1

    headers = combined_header(raw_rows, header_rows_count)
    if not headers:
        return [], None

    # Drop serial number columns
    keep_indices = [i for i, h in enumerate(headers) if not is_sr_no_col(h)]
    if not keep_indices:
        return [], None

    filtered_headers = [headers[i] for i in keep_indices]
    r_type = classify_table(filtered_headers, page_category)

    base_context = norm(table.get("context", "") or page_title)

    if not r_type:
        unclassified = {
            "source_url": source_url,
            "page": page_no,
            "context": base_context,
            "headers": filtered_headers,
            "rows": raw_rows,
            "header_rows": header_rows_count,
            "rows_count": len(raw_rows) - header_rows_count,
            "title": page_title,
            "category": page_category,
        }
        return [], unclassified

    records: List[Dict[str, Any]] = []
    running_context = base_context
    data_rows = raw_rows[header_rows_count:]

    for row_cells in data_rows:
        title_only, title_text = is_title_only_row(row_cells)
        if title_only:
            running_context = f"{base_context} - {title_text}" if base_context else title_text
            continue

        # Extract data for filtered columns
        row_data: Dict[str, str] = {}
        for idx in keep_indices:
            header_name = headers[idx]
            val = norm(row_cells[idx]) if idx < len(row_cells) else ""
            row_data[header_name] = val

        if not any(row_data.values()):
            continue

        # Detect total rows for intake tables
        is_total = False
        if r_type == "intake":
            is_total = (
                any("total" in norm(c).lower() for c in row_cells) or
                any("total" in norm(k).lower() or "total" in norm(v).lower() for k, v in row_data.items())
            )

        rid = generate_record_id(r_type, running_context, row_data)

        if is_total:
            # Total intake rows answer "total intake" questions, never program names
            key_tokens = ["total", "intake", norm(running_context)]
            for k, v in row_data.items():
                if "total" in k.lower() or "total" in v.lower() or v.isdigit():
                    key_tokens.append(k)
                    key_tokens.append(v)
        else:
            # Hidden extra tokens: include page title and page name words for disambiguation
            key_tokens = [norm(running_context)]
            if page_title:
                key_tokens.append(norm(page_title))
            if page_name:
                key_tokens.append(norm(page_name.replace("_", " ")))
            for k, v in row_data.items():
                key_tokens.append(k)
                key_tokens.append(v)

        key_text = norm(" ".join(key_tokens))

        rec = {
            "id": rid,
            "type": r_type,
            "source_url": source_url,
            "page": page_no,
            "context": running_context,
            "data": row_data,
            "key_text": key_text,
            "source": "scraped",
            "is_total": is_total,
        }
        records.append(rec)

    return records, None

def load_manual_csvs(manual_dir: Path = config.MANUAL_DIR) -> List[Dict[str, Any]]:
    """Load manual records from data/manual/<type>.csv, ignoring *.generated.csv."""
    manual_records: List[Dict[str, Any]] = []

    for r_type in config.RECORD_TYPES:
        csv_path = manual_dir / f"{r_type}.csv"
        if not csv_path.exists() or csv_path.name.endswith(".generated.csv"):
            continue

        try:
            with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for r_idx, row in enumerate(reader, 1):
                    # Strip header whitespace and drop blank cells
                    row_clean = {
                        k.strip(): norm(v)
                        for k, v in row.items()
                        if k is not None and k.strip() and norm(v) != ""
                    }
                    context = row_clean.pop("context", "")
                    src = row_clean.pop("source", f"manual/{r_type}.csv")

                    if not row_clean:
                        continue

                    is_total = False
                    if r_type == "intake":
                        is_total = any(
                            "total" in norm(k).lower() or "total" in norm(v).lower()
                            for k, v in row_clean.items()
                        )
                    rid = generate_record_id(r_type, context, row_clean)

                    if is_total:
                        key_tokens = ["total", "intake", norm(context)]
                        for k, v in row_clean.items():
                            key_tokens.append(k)
                            key_tokens.append(v)
                    else:
                        key_tokens = [norm(context)]
                        for k, v in row_clean.items():
                            key_tokens.append(k)
                            key_tokens.append(v)

                    key_text = norm(" ".join(key_tokens))

                    rec = {
                        "id": rid,
                        "type": r_type,
                        "source_url": src,
                        "page": 1,
                        "context": context,
                        "data": row_clean,
                        "key_text": key_text,
                        "source": "manual",
                        "is_total": is_total,
                    }
                    manual_records.append(rec)
        except Exception as e:
            logger.error("Failed loading manual CSV %s: %s", csv_path, e)

    return manual_records

def save_to_sqlite(records: List[Dict[str, Any]], db_path: Path = config.DB_PATH):
    """Write records to SQLite database with index on type and is_total."""
    config.ensure_directories()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            source_url TEXT,
            page INTEGER,
            context TEXT,
            data_json TEXT NOT NULL,
            key_text TEXT,
            source TEXT,
            is_total INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_type ON records(type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_is_total ON records(is_total)")
    cursor.execute("DELETE FROM records")  # Clean rebuild

    for r in records:
        cursor.execute(
            """
            INSERT OR REPLACE INTO records (id, type, source_url, page, context, data_json, key_text, source, is_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["id"],
                r["type"],
                r.get("source_url", ""),
                r.get("page", 1),
                r.get("context", ""),
                json.dumps(r.get("data", {}), ensure_ascii=False),
                r.get("key_text", ""),
                r.get("source", "scraped"),
                1 if r.get("is_total") else 0,
            )
        )

    conn.commit()
    conn.close()

def get_intake_collapse_key(data: Dict[str, str]) -> Optional[str]:
    """Extract program name key and numbers to collapse identical intake across sources."""
    prog_parts = []
    nums = []
    for k, v in data.items():
        clean_v = re.sub(r"[,\s₹$%-]", "", v)
        if clean_v.isdigit():
            nums.append(clean_v)
        else:
            prog_parts.append(v)
    if not prog_parts or not nums:
        return None
    clean_prog = re.sub(r"[^a-zA-Z0-9]", "", " ".join(prog_parts)).lower()
    nums_str = ",".join(sorted(nums))
    return f"{clean_prog}|{nums_str}"

def run_normaliser(
    pages_jsonl_path: Optional[Path] = None,
    records_jsonl_path: Path = config.RECORDS_JSONL,
    unclassified_jsonl_path: Path = config.UNCLASSIFIED_JSONL,
    db_path: Path = config.DB_PATH,
    manual_dir: Optional[Path] = None
) -> Tuple[int, int]:
    """
    Run normalisation pipeline on iter_pages() and manual CSVs.
    Returns: (total_records_count, unclassified_tables_count)
    """
    config.ensure_directories()
    manual_dir = manual_dir or config.MANUAL_DIR
    scraped_records: List[Dict[str, Any]] = []
    unclassified_tables: List[Dict[str, Any]] = []

    pages_input = [pages_jsonl_path] if pages_jsonl_path else None
    for page in iter_pages(paths=pages_input):
        p_type = page.get("type", "")
        # HTML tables only for structured records (PDF tables are cut-off / syllabus)
        if p_type != "html":
            continue

        url = page.get("url", "")
        page_no = page.get("page", 1)
        title = page.get("title", "")
        cat = page.get("category", "")
        name = page.get("name", "")
        tables = page.get("tables", [])

        for table in tables:
            tbl_recs, unclass = process_table(table, url, page_no, title, cat, page_name=name)
            if unclass:
                unclassified_tables.append(unclass)
            scraped_records.extend(tbl_recs)

    # Collapse intake records: identical (program-name key, numbers) across sources
    collapsed_scraped: List[Dict[str, Any]] = []
    intake_seen: Dict[str, Dict[str, Any]] = {}

    for rec in scraped_records:
        if rec["type"] == "intake" and not rec.get("is_total", False):
            ckey = get_intake_collapse_key(rec["data"])
            if ckey:
                if ckey in intake_seen:
                    existing = intake_seen[ckey]
                    existing_urls = [u.strip() for u in existing["source_url"].split(",") if u.strip()]
                    new_url = rec["source_url"].strip()
                    if new_url and new_url not in existing_urls:
                        existing_urls.append(new_url)
                        existing["source_url"] = ", ".join(existing_urls)
                    existing["key_text"] = norm(existing["key_text"] + " " + rec["key_text"])
                    continue
                else:
                    intake_seen[ckey] = rec
                    collapsed_scraped.append(rec)
                    continue
        collapsed_scraped.append(rec)

    # Entity map for scraped records
    final_records_by_entity: Dict[str, Dict[str, Any]] = {}
    for rec in collapsed_scraped:
        ekey = get_entity_match_key(rec["type"], rec["context"], rec["data"])
        final_records_by_entity[ekey] = rec

    # Load manual CSVs (manual rows win over scraped duplicates)
    manual_records = load_manual_csvs(manual_dir=manual_dir)
    for m_rec in manual_records:
        ekey = get_entity_match_key(m_rec["type"], m_rec["context"], m_rec["data"])
        final_records_by_entity[ekey] = m_rec  # Manual wins

    all_records = list(final_records_by_entity.values())

    # Save to records.jsonl
    with open(records_jsonl_path, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save to unclassified_tables.jsonl
    with open(unclassified_jsonl_path, "w", encoding="utf-8") as f:
        for u in unclassified_tables:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    # Save to SQLite
    save_to_sqlite(all_records, db_path)

    # Print summary counts
    counts_by_type: Dict[str, int] = {t: 0 for t in config.RECORD_TYPES}
    for r in all_records:
        counts_by_type[r["type"]] = counts_by_type.get(r["type"], 0) + 1

    print("\n" + "=" * 50)
    print("Normalisation Complete:")
    for r_type in config.RECORD_TYPES:
        print(f"  {r_type:10s}: {counts_by_type.get(r_type, 0)} records")
    print(f"  Total records: {len(all_records)}")
    print(f"  Unclassified tables: {len(unclassified_tables)}")
    print("=" * 50)

    return len(all_records), len(unclassified_tables)

if __name__ == "__main__":
    run_normaliser()
