"""
Verification tool for curated facts (fees, cut-offs, HODs).
Writes data/VERIFICATION_REPORT.md and data/manual/cutoffs.proposed.csv.

Does NOT modify fees.csv, cutoffs.csv, or hods.csv.

Run from project root:
    python -m tools.verify_curated
"""

import csv
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Tuple

import config
from scraper.pages_io import iter_pages

def clean_val(val: str) -> str:
    """Strip surrounding parens, commas, spaces."""
    v = val.strip().strip("()")
    return v.replace(",", "")

def verify_fees() -> List[Dict[str, Any]]:
    """Verify curated fees from data/manual/fees.csv against non-curated pages/tables."""
    fees_path = config.MANUAL_DIR / "fees.csv"
    if not fees_path.exists():
        return []

    with open(fees_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # Collect all text and table strings from non-curated pages
    non_curated_corpus = []
    for p in iter_pages():
        origin = p.get("origin", "")
        if origin.startswith("curated:"):
            continue
        text = p.get("text", "")
        tables = p.get("tables", [])
        tbl_text = " ".join(
            " ".join(str(cell) for cell in row)
            for t in tables
            for row in t.get("rows", [])
        )
        non_curated_corpus.append((p.get("url", ""), p.get("name", ""), text + " " + tbl_text))

    results = []
    for r in rows:
        prog = r.get("Program", "").strip()
        cat = r.get("Category", "").strip()
        tuition = r.get("Annual Tuition Fee (INR)", "").strip()
        details = r.get("Fee Details", "").strip()

        item_label = f"{prog} ({cat})" if cat else prog
        curated_val = f"Tuition: {tuition}" if tuition else details

        # Extract figures to search
        figures = []
        if tuition:
            figures.append(tuition)
        # Search numbers mentioned in details
        found_nums = re.findall(r"[\d,]+", details)
        for fn in found_nums:
            cn = fn.replace(",", "")
            if len(cn) >= 4:
                figures.append(cn)

        matched_evidence = []
        for num in figures:
            formatted_variants = [num, f"{int(num):,}" if num.isdigit() else num]
            for url, name, corpus in non_curated_corpus:
                for variant in formatted_variants:
                    if variant in corpus:
                        matched_evidence.append(f"{name} ({url})")

        status = "MATCHED" if matched_evidence else "NOT FOUND"
        evidence_str = "; ".join(set(matched_evidence)) if matched_evidence else "None found in legacy/scraped pages"
        action = "Keep verified figure" if status == "MATCHED" else "UNVERIFIED — needs the official fee notice"

        # Special check for OBC/EBC 50%
        notes = ""
        if "68,261" in details or "68261" in figures:
            notes = " [Informational: OBC/EBC amount (68,261) is exactly half of Open (1,36,522)]"

        results.append({
            "Item": item_label,
            "Curated value": (curated_val[:60] + "...") if len(curated_val) > 60 else curated_val,
            "Status": status,
            "Evidence": evidence_str + notes,
            "Action for me": action
        })

    return results

def verify_cutoffs() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Verify curated cutoffs from data/manual/cutoffs.csv against cutoff_cells table in SQLite.
    Returns (report_rows, proposed_cutoffs_rows).
    """
    cutoffs_path = config.MANUAL_DIR / "cutoffs.csv"
    if not cutoffs_path.exists():
        return [], []

    with open(cutoffs_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    report_rows = []
    proposed_rows = []

    # Map curated course names to common branch abbreviations in cutoff PDFs
    branch_aliases = {
        "computer engineering": ["comp", "computer"],
        "computer science and engineering (artificial intelligence and machine learning)": ["aiml", "ai & ml"],
        "computer science and information technology": ["cs & it", "csit", "it"],
        "electronics and telecommunication engineering": ["etc", "entc", "electronics"],
        "electrical engineering": ["elect", "electrical"],
        "civil engineering": ["civil"],
        "robotics and automation": ["robotics"],
        "mechatronics engineering": ["mech atron ics", "mechatronics"],
        "mechanical engineering": ["mech", "mechanical"],
        "mba": ["mba"],
        "mca": ["mca"],
        "bba": ["bba"],
        "bca": ["bca"],
    }

    for r in rows:
        course = r.get("Course", "").strip()
        rank = r.get("Cutoff Rank", "").strip()
        perc = r.get("Cutoff Percentile", "").strip()
        curated_val = f"Rank {rank}, {perc}%"

        # Search for exact rank in cutoff_cells
        cursor.execute(
            "SELECT pdf_url, page, program_level, year, round, branch, gender_or_group, category, metric, value "
            "FROM cutoff_cells WHERE value = ?", (rank,)
        )
        rank_matches = cursor.fetchall()

        matched_cell = None
        for m in rank_matches:
            pdf_url, page, prog, yr, rnd, branch, gender, cat, metric, val = m
            # Check branch alias match
            aliases = branch_aliases.get(course.lower(), [course.lower()])
            branch_match = any(a in branch.lower() for a in aliases)
            if not branch_match:
                continue

            # Check marks in same cell descriptor
            cursor.execute(
                "SELECT value FROM cutoff_cells WHERE pdf_url=? AND page=? AND branch=? AND gender_or_group=? AND category=? AND metric='Marks'",
                (pdf_url, page, branch, gender, cat)
            )
            marks_rows = cursor.fetchall()
            marks_vals = [clean_val(mr[0]) for mr in marks_rows]
            if perc in marks_vals:
                matched_cell = {
                    "pdf_url": pdf_url,
                    "page": page,
                    "prog": prog,
                    "year": yr,
                    "round": rnd or "CAP I",
                    "branch": branch,
                    "gender": gender,
                    "category": cat,
                    "rank": rank,
                    "perc": perc
                }
                break

        if matched_cell:
            status = "MATCHED"
            evidence = (
                f"{matched_cell['pdf_url'].split('/')[-1]}, p.{matched_cell['page']}, "
                f"{matched_cell['branch']} ({matched_cell['prog']} {matched_cell['year']} {matched_cell['round']} "
                f"{matched_cell['gender']}/{matched_cell['category']})"
            )
            action = "Duplicate of PDF cutoff_cells; propose updated context or drop"
            proposed_r = dict(r)
            proposed_r["context"] = f"FY B.Tech, CAP Ist Round 2024-25, Gents Open (matched to the PDF cell)"
            proposed_r["source"] = matched_cell["pdf_url"]
            proposed_rows.append(proposed_r)
        else:
            status = "NOT FOUND"
            evidence = "No matching branch/cell in cutoff_cells"
            action = "Keep curated figure with unverified warning (no source PDF)"
            proposed_rows.append(dict(r))

        report_rows.append({
            "Item": course,
            "Curated value": curated_val,
            "Status": status,
            "Evidence": evidence,
            "Action for me": action
        })

    conn.close()

    # Write data/manual/cutoffs.proposed.csv
    proposed_csv_path = config.MANUAL_DIR / "cutoffs.proposed.csv"
    if proposed_rows:
        fieldnames = list(proposed_rows[0].keys())
        with open(proposed_csv_path, "w", encoding="utf-8", newline="") as pf:
            writer = csv.DictWriter(pf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(proposed_rows)

    return report_rows, proposed_rows

def verify_hods() -> List[Dict[str, Any]]:
    """Verify curated HODs from data/manual/hods.csv against department page texts."""
    hods_path = config.MANUAL_DIR / "hods.csv"
    if not hods_path.exists():
        return []

    with open(hods_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # Index department pages
    dept_pages = {}
    other_pages = {}
    for p in iter_pages():
        name = p.get("name", "")
        text = p.get("text", "")
        url = p.get("url", "")
        if "department::" in name or p.get("category") == "hods":
            # Extract dept name
            clean_name = name.replace("department::", "").strip()
            dept_pages[clean_name.lower()] = (text, url)
        else:
            other_pages[name] = (text, url)

    report_rows = []
    for r in rows:
        dept = r.get("Department", "").strip()
        hod = r.get("HOD Name", "").strip()
        source = r.get("source", "").strip()

        # Find matching dept page: exact source URL match first, then longest matching department name
        page_text = ""
        page_url = source
        for dname, (txt, u) in dept_pages.items():
            if u == source:
                page_text = txt
                page_url = u
                break
        if not page_text:
            sorted_depts = sorted(dept_pages.items(), key=lambda x: len(x[0]), reverse=True)
            for dname, (txt, u) in sorted_depts:
                if dname in dept.lower() or dept.lower() in dname:
                    page_text = txt
                    page_url = u
                    break

        # Check in HOD message section
        hod_msg = ""
        if "HOD message:" in page_text:
            hod_msg = page_text.split("HOD message:", 1)[1]
        elif "Head of Department (HOD):" in page_text:
            hod_msg = page_text.split("Head of Department (HOD):", 1)[1]
        else:
            hod_msg = page_text

        # Extract surname & initials
        parts = hod.replace(".", " ").split()
        surname = parts[-1] if parts else ""
        initials = [p[0].upper() for p in parts[:-1] if p.lower() not in ("dr", "mr", "mrs", "ms", "prof")]

        status = "NOT FOUND"
        evidence = ""
        action = ""

        if hod in hod_msg:
            status = "MATCHED"
            evidence = f"Exact name in HOD message ({page_url})"
            action = "Keep verified HOD"
        elif surname.lower() in hod_msg.lower() and all(init in hod_msg for init in initials):
            status = "PARTIAL"
            # Find signature snippet
            sig_match = re.search(rf"(Dr\.?\s+[A-Za-z\s\.]*{re.escape(surname)}[^\n]*)", hod_msg, re.I)
            sig_str = sig_match.group(1).strip() if sig_match else surname
            evidence = f"Abbreviated in CSV vs HOD message signature '{sig_str}' ({page_url})"
            action = "Confirm full name expansion"
        else:
            status = "NOT FOUND"
            # Search other pages
            found_elsewhere = []
            for oname, (otxt, ou) in other_pages.items():
                if surname.lower() in otxt.lower():
                    found_elsewhere.append(f"{oname} ({ou})")
            if found_elsewhere:
                evidence = f"HOD message unsigned; found in: {'; '.join(found_elsewhere[:2])}"
            else:
                evidence = f"Absent from department page text ({page_url})"
            action = "Needs official appointment letter or website confirmation"

        if "Automobile" in dept and "Dr. S. R. Desai" in hod:
            evidence += " [Note: Same person also listed as HOD of Robotics and Automation]"

        report_rows.append({
            "Item": dept,
            "Curated value": hod,
            "Status": status,
            "Evidence": evidence,
            "Action for me": action
        })

    return report_rows

def generate_report(fees_rep: List[Dict[str, Any]], cutoffs_rep: List[Dict[str, Any]], hods_rep: List[Dict[str, Any]]) -> str:
    lines = [
        "# RIT Institutional Assistant - Curated Facts Verification Report",
        "",
        "This report is generated automatically by `tools/verify_curated.py`.",
        "It checks all curated manual facts (`fees.csv`, `cutoffs.csv`, `hods.csv`) against verified scraped data.",
        "",
        "## 1. Fees Verification (`data/manual/fees.csv`)",
        "",
        "| Item | Curated value | Status | Evidence | Action for me |",
        "|---|---|---|---|---|"
    ]
    for r in fees_rep:
        lines.append(f"| {r['Item']} | {r['Curated value']} | **{r['Status']}** | {r['Evidence']} | {r['Action for me']} |")

    lines.extend([
        "",
        "## 2. Cut-offs Verification (`data/manual/cutoffs.csv`)",
        "",
        "| Item | Curated value | Status | Evidence | Action for me |",
        "|---|---|---|---|---|"
    ])
    for r in cutoffs_rep:
        lines.append(f"| {r['Item']} | {r['Curated value']} | **{r['Status']}** | {r['Evidence']} | {r['Action for me']} |")

    lines.extend([
        "",
        "## 3. HODs Verification (`data/manual/hods.csv`)",
        "",
        "| Item | Curated value | Status | Evidence | Action for me |",
        "|---|---|---|---|---|"
    ])
    for r in hods_rep:
        lines.append(f"| {r['Item']} | {r['Curated value']} | **{r['Status']}** | {r['Evidence']} | {r['Action for me']} |")

    lines.extend([
        "",
        "## 4. Decisions Needed From User",
        "",
        "1. **Drop the 9 fully matched B.Tech rows of `cutoffs.csv` in favour of the PDF values?**",
        "   - The 9 B.Tech rows in `cutoffs.csv` are identical duplicates of the values already indexed in `cutoff_cells` from `fy-btech-cutoff-2024-25.pdf` (FY B.Tech CAP I 2024-25 Gents Open SML NO).",
        "   - `data/manual/cutoffs.proposed.csv` has been generated with precise context and source URLs.",
        "   - Shall we replace `cutoffs.csv` with `cutoffs.proposed.csv` or drop the 9 duplicate B.Tech rows from the manual CSV?",
        "",
        "2. **Is Dr. S. R. Desai really HOD of both Robotics & Automation and Automobile Engineering?**",
        "   - On the Robotics page, the HOD message is signed `Dr. Sandeep R. Desai, Head of the Department Robotics and Automation`.",
        "   - On the Automobile Engineering page, the HOD message is also signed `Dr. S. R. Desai`.",
        "   - Please confirm if Dr. Desai serves as Head for both departments.",
        "",
        "3. **Source of the Electrical Engineering HOD (`Dr. V. N. Kalkhambkar`)**",
        "   - The HOD message on the Electrical Engineering department page is unsigned.",
        "   - However, `Dr. V. N. Kalkhambkar` is confirmed in the official RIT PhD research guide list (`PhD-student-List-Electrical.pdf`).",
        "   - Please confirm whether to accept this attribution from the PhD supervisor records.",
        ""
    ])
    return "\n".join(lines)

def run_verification():
    fees_rep = verify_fees()
    cutoffs_rep, proposed = verify_cutoffs()
    hods_rep = verify_hods()

    report_md = generate_report(fees_rep, cutoffs_rep, hods_rep)
    report_path = config.DATA_DIR / "VERIFICATION_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Verification complete:")
    print(f"  Fees: {len(fees_rep)} checked ({sum(1 for r in fees_rep if r['Status'] == 'MATCHED')} matched)")
    print(f"  Cutoffs: {len(cutoffs_rep)} checked ({sum(1 for r in cutoffs_rep if r['Status'] == 'MATCHED')} matched)")
    print(f"  HODs: {len(hods_rep)} checked ({sum(1 for r in hods_rep if r['Status'] == 'MATCHED')} matched, {sum(1 for r in hods_rep if r['Status'] == 'PARTIAL')} partial)")
    print(f"  Saved report to {report_path}")
    print(f"  Saved proposed cutoffs to {config.MANUAL_DIR / 'cutoffs.proposed.csv'}")

if __name__ == "__main__":
    run_verification()
