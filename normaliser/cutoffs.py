"""
Cut-off tables parser and normaliser for RIT Assistant v3.
Parses wide tables from the 10 cut-off PDFs into long-format cutoff_cells in SQLite
and generates branch/PDF descriptors for indexing and retrieval routing.

Run from project root:
    python -m normaliser.cutoffs
"""

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import config
from scraper.pages_io import iter_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("normaliser.cutoffs")

VALID_METRICS = {"SML NO", "Merit No", "Marks"}

def parse_cutoff_context(ctx: str, pdf_name: str = "") -> Tuple[str, str, str]:
    """Parse program_level, year, and round from table context and PDF name."""
    text = (ctx + " " + pdf_name).lower()

    # 1. Program level
    level = ""
    if "dsy" in text and "diploma" in text:
        level = "DSY Diploma"
    elif "dsy" in text or "direct second year" in text:
        level = "DSY B.Tech"
    elif "m. tech" in text or "m.tech" in text or "mtech" in text:
        level = "M.Tech"
    elif "mba" in text:
        level = "MBA"
    elif "diploma" in text:
        level = "FY Diploma"
    elif "b. tech" in text or "b.tech" in text or "btech" in text:
        level = "FY B.Tech"

    # 2. Year (normalized to YYYY-YY)
    m_yr = re.search(r"(20\d\d[-–/]\d{2,4})", ctx)
    raw_yr = m_yr.group(1) if m_yr else ""
    if not raw_yr:
        m_yr_pdf = re.search(r"(20\d\d[-–/]\d{2,4})", pdf_name)
        raw_yr = m_yr_pdf.group(1) if m_yr_pdf else ""

    year = raw_yr
    if len(raw_yr) == 9 and raw_yr[4] in ("-", "/", "–"):
        year = f"{raw_yr[:4]}-{raw_yr[7:]}"

    # 3. Round
    rnd = ""
    m_rnd = re.search(r"cap\s+([a-zA-Z0-9]+)", ctx, re.I)
    if m_rnd:
        raw_r = m_rnd.group(1).lower()
        if raw_r in ("i", "ist", "first", "1"):
            rnd = "CAP I"
        elif raw_r in ("ii", "iind", "second", "2"):
            rnd = "CAP II"
        elif raw_r in ("iii", "iiird", "third", "3"):
            rnd = "CAP III"
        elif raw_r in ("iv", "ivth", "fourth", "4"):
            rnd = "CAP IV"
        else:
            rnd = f"CAP {m_rnd.group(1).upper()}"

    return level, year, rnd

def parse_header_columns(row0: List[str], row1: List[str]) -> List[Tuple[int, str, str]]:
    """
    Forward-fill row 0 group label (Gents/Ladies/General) rightwards until next label.
    Category is from row 1.
    Returns: list of (col_idx, group, category)
    """
    current_group = ""
    cols: List[Tuple[int, str, str]] = []
    max_cols = max(len(row0), len(row1))

    for c in range(2, max_cols):
        g = row0[c].strip() if c < len(row0) else ""
        cat = row1[c].strip() if c < len(row1) else ""

        if g in ("Gents", "Ladies", "General") or (g and not current_group):
            current_group = g
        elif g:
            current_group = g

        if not cat:
            final_group = "General"
            final_cat = g or current_group or f"Col_{c+1}"
        else:
            final_group = current_group if current_group else "General"
            final_cat = cat

        cols.append((c, final_group, final_cat))

    return cols

def extract_cutoff_cells_from_pages(
    pages_input: Optional[List[Path]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract long-format cells, descriptors, and review logs from cut-off PDFs.
    Returns: (cells, descriptors, needs_review_list)
    """
    recs = [
        r for r in iter_pages(paths=pages_input)
        if r.get("type") == "pdf" and "cutoff" in r.get("name", "").lower()
    ]

    by_pdf: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        # Prefer legacy records (which contain all 10 PDFs completely)
        by_pdf.setdefault(r["name"], []).append(r)

    cells: List[Dict[str, Any]] = []
    descriptors: List[Dict[str, Any]] = []
    needs_review: List[Dict[str, Any]] = []

    for pdf_name, pages in sorted(by_pdf.items()):
        prev_cols: Optional[List[Tuple[int, str, str]]] = None
        prev_meta: Optional[Tuple[str, str, str, str]] = None
        last_branch = ""
        branches_in_pdf: Dict[str, Dict[str, Any]] = {}

        for p in sorted(pages, key=lambda x: x["page"]):
            pdf_url = p.get("url", "")
            page_no = p.get("page", 1)
            tables = p.get("tables", [])

            for t_idx, t in enumerate(tables):
                rows = t.get("rows", [])
                if len(rows) < 2:
                    needs_review.append({
                        "pdf": pdf_name, "page": page_no, "table_idx": t_idx,
                        "reason": "Table has fewer than 2 rows"
                    })
                    continue

                base_ctx = t.get("context", "")
                level, year, rnd = parse_cutoff_context(base_ctx, pdf_name)
                cur_ctx = base_ctx

                # Check if row 0 is a leading title row
                start_offset = 0
                first_non_empty = [c for c in rows[0] if c.strip()]
                if len(first_non_empty) == 1 and any(w in first_non_empty[0].lower() for w in ("cut off", "date", "district", "round")):
                    cur_ctx = first_non_empty[0]
                    sub_lvl, sub_yr, sub_rnd = parse_cutoff_context(cur_ctx, pdf_name)
                    if sub_lvl: level = sub_lvl
                    if sub_yr: year = sub_yr
                    if sub_rnd: rnd = sub_rnd
                    start_offset = 1

                is_hdr_table = False
                if start_offset < len(rows) and rows[start_offset][0].strip().lower().startswith("branch"):
                    is_hdr_table = True

                if not is_hdr_table:
                    first_metric = rows[start_offset][1].strip() if len(rows[start_offset]) > 1 else ""
                    if first_metric not in VALID_METRICS:
                        needs_review.append({
                            "pdf": pdf_name, "page": page_no, "table_idx": t_idx,
                            "reason": f"Non-header table row does not start with valid metric: {rows[start_offset][:3]}"
                        })
                        continue
                    if not prev_cols:
                        needs_review.append({
                            "pdf": pdf_name, "page": page_no, "table_idx": t_idx,
                            "reason": "Continuation table has no preceding header to inherit"
                        })
                        continue

                r_idx = start_offset
                cols = prev_cols

                while r_idx < len(rows):
                    row = rows[r_idx]
                    non_empty = [c for c in row if c.strip()]
                    if not non_empty:
                        r_idx += 1
                        continue

                    # Section title row
                    if len(non_empty) == 1 and ("cut off" in non_empty[0].lower() or "district" in non_empty[0].lower()):
                        cur_ctx = non_empty[0]
                        sub_lvl, sub_yr, sub_rnd = parse_cutoff_context(cur_ctx, pdf_name)
                        if sub_lvl: level = sub_lvl
                        if sub_yr: year = sub_yr
                        if sub_rnd: rnd = sub_rnd
                        r_idx += 1
                        continue

                    # Header start
                    if row[0].strip().lower().startswith("branch"):
                        row0 = row
                        row1 = rows[r_idx + 1] if r_idx + 1 < len(rows) else []
                        parsed_cols = parse_header_columns(row0, row1)
                        pairs = [(g, cat) for c, g, cat in parsed_cols]
                        if len(pairs) != len(set(pairs)):
                            needs_review.append({
                                "pdf": pdf_name, "page": page_no, "table_idx": t_idx,
                                "reason": f"Duplicate (group, category) in header: {pairs}"
                            })
                            break
                        cols = parsed_cols
                        prev_cols = cols
                        prev_meta = (level, year, rnd, cur_ctx)
                        r_idx += 2
                        continue

                    # Data row validation
                    if not cols or len(row) < len(cols) + 2:
                        needs_review.append({
                            "pdf": pdf_name, "page": page_no, "table_idx": t_idx,
                            "reason": f"Row length mismatch: got {len(row)}, expected {len(cols)+2 if cols else 'unknown'}"
                        })
                        break

                    b_raw = row[0].strip() if len(row) > 0 else ""
                    if b_raw:
                        current_branch = b_raw
                        last_branch = b_raw
                    else:
                        current_branch = last_branch

                    metric = row[1].strip() if len(row) > 1 else ""
                    if metric in VALID_METRICS:
                        for c_idx, group, cat in cols:
                            val = row[c_idx] if c_idx < len(row) else ""
                            val_str = str(val).strip()
                            avail = val_str not in ("", "-", "--")

                            cell_rec = {
                                "pdf_url": pdf_url,
                                "pdf_name": pdf_name,
                                "page": page_no,
                                "program_level": level,
                                "year": year,
                                "round": rnd,
                                "branch": current_branch,
                                "gender_or_group": group,
                                "category": cat,
                                "metric": metric,
                                "value": val_str,
                                "available": avail,
                                "context": cur_ctx
                            }
                            cells.append(cell_rec)

                            # Record descriptor information
                            desc_key = (pdf_name, level, year, rnd, current_branch)
                            if desc_key not in branches_in_pdf:
                                branches_in_pdf[desc_key] = {
                                    "pdf_url": pdf_url,
                                    "pdf_name": pdf_name,
                                    "program_level": level,
                                    "year": year,
                                    "round": rnd,
                                    "branch": current_branch,
                                    "categories": set()
                                }
                            if avail:
                                branches_in_pdf[desc_key]["categories"].add(f"{group} {cat}".strip())

                    r_idx += 1

        # Build descriptors for this PDF
        for desc_key, dinfo in branches_in_pdf.items():
            cats_str = ", ".join(sorted(dinfo["categories"]))
            desc_text = (
                f"{dinfo['program_level']} · {dinfo['round']} · {dinfo['year']} · "
                f"{dinfo['branch']} cut-off. Available categories: {cats_str}"
            )
            descriptors.append({
                "kind": "record",
                "type": "cutoffs",
                "pdf_url": dinfo["pdf_url"],
                "pdf_name": dinfo["pdf_name"],
                "program_level": dinfo["program_level"],
                "year": dinfo["year"],
                "round": dinfo["round"],
                "branch": dinfo["branch"],
                "text": desc_text,
                "categories": list(dinfo["categories"])
            })

    return cells, descriptors, needs_review

def save_cutoff_cells_to_sqlite(
    cells: List[Dict[str, Any]],
    db_path: Path = config.DB_PATH
):
    """Save cutoff_cells to SQLite database table."""
    config.ensure_directories()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cutoff_cells (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_url TEXT,
            page INTEGER,
            program_level TEXT,
            year TEXT,
            round TEXT,
            branch TEXT,
            gender_or_group TEXT,
            category TEXT,
            metric TEXT,
            value TEXT,
            available INTEGER,
            context TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cutoff_lookup ON cutoff_cells(branch, program_level, year, round)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cutoff_cat ON cutoff_cells(category, gender_or_group)")
    cursor.execute("DELETE FROM cutoff_cells")

    for c in cells:
        cursor.execute(
            """
            INSERT INTO cutoff_cells (
                pdf_url, page, program_level, year, round, branch,
                gender_or_group, category, metric, value, available, context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c["pdf_url"],
                c["page"],
                c["program_level"],
                c["year"],
                c["round"],
                c["branch"],
                c["gender_or_group"],
                c["category"],
                c["metric"],
                c["value"],
                1 if c["available"] else 0,
                c["context"]
            )
        )

    conn.commit()
    conn.close()

def run_cutoff_normaliser() -> Tuple[int, int]:
    """Run full cutoff pipeline -> cutoff_cells in SQLite & jsonl."""
    cells, descriptors, needs_review = extract_cutoff_cells_from_pages()

    # Save to SQLite
    save_cutoff_cells_to_sqlite(cells)

    # Save to cutoff_cells.jsonl
    cutoff_jsonl_path = config.NORMALISED_DIR / "cutoff_cells.jsonl"
    with open(cutoff_jsonl_path, "w", encoding="utf-8") as f:
        for c in cells:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Save descriptors to cutoff_descriptors.jsonl
    desc_jsonl_path = config.NORMALISED_DIR / "cutoff_descriptors.jsonl"
    with open(desc_jsonl_path, "w", encoding="utf-8") as f:
        for d in descriptors:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print("\n" + "=" * 50)
    print("Cut-off Normalisation Complete:")
    print(f"  Total cells: {len(cells)}")
    print(f"  Total branch descriptors: {len(descriptors)}")
    print(f"  Needs review tables count: {len(needs_review)}")
    for nr in needs_review:
        print(f"    ! {nr['pdf']} (p.{nr['page']} tbl {nr['table_idx']}): {nr['reason']}")
    print("=" * 50)

    return len(cells), len(needs_review)

if __name__ == "__main__":
    run_cutoff_normaliser()
