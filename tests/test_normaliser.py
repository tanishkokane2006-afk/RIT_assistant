"""Unit tests for Task A Normaliser.
Tests:
- Merged-header fee table
- Intake table
- Faculty table
- Unclassified table is reported to unclassified_tables.jsonl, not guessed
- Manual CSV overrides scraped value
- record_to_text output format
"""

import csv
import json
import sqlite3
import tempfile
from pathlib import Path

import config
from scraper.tables import table_to_rows
from normaliser.records import (
    process_table,
    classify_table,
    record_to_text,
    run_normaliser,
    load_manual_csvs
)
from bs4 import BeautifulSoup

def test_classify_and_process_tables():
    # 1. Merged-header fee table
    html_fee = """
    <table>
      <thead>
        <tr>
          <th rowspan="2">Category</th>
          <th colspan="2">Fees (INR)</th>
        </tr>
        <tr>
          <th>Tuition Fee</th>
          <th>Development Fee</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Open</td><td>105000</td><td>15000</td></tr>
        <tr><td>OBC</td><td>52500</td><td>15000</td></tr>
      </tbody>
    </table>
    """
    soup_fee = BeautifulSoup(html_fee, "html.parser")
    rows, header_rows = table_to_rows(soup_fee.find("table"))
    tbl_fee = {"rows": rows, "header_rows": header_rows, "context": "Fee Structure 2026-27"}
    recs, unclass = process_table(tbl_fee, "https://ritindia.edu/fees", 1, "Fees Page", "fees")

    assert unclass is None
    assert len(recs) == 2
    assert recs[0]["type"] == "fees"
    assert recs[0]["data"]["Fees (INR) - Tuition Fee"] == "105000"
    assert recs[0]["data"]["Fees (INR) - Development Fee"] == "15000"
    assert recs[0]["data"]["Category"] == "Open"

    # Test record_to_text
    txt = record_to_text(recs[0]["type"], recs[0]["context"], recs[0]["data"])
    assert "[FEES]" in txt
    assert "105000" in txt

    # 2. Intake table with title-only section divider and serial-no
    html_intake = """
    <table>
      <thead>
        <tr>
          <th>Sr. No.</th>
          <th>Branch Name</th>
          <th>Sanctioned Intake</th>
        </tr>
      </thead>
      <tbody>
        <tr><td colspan="3">Undergraduate Programs</td></tr>
        <tr><td>1</td><td>Computer Science and Engineering</td><td>180</td></tr>
        <tr><td>2</td><td>Mechanical Engineering</td><td>120</td></tr>
      </tbody>
    </table>
    """
    soup_intake = BeautifulSoup(html_intake, "html.parser")
    rows, header_rows = table_to_rows(soup_intake.find("table"))
    tbl_intake = {"rows": rows, "header_rows": header_rows, "context": "Sanctioned Seats"}
    recs_intake, unclass = process_table(tbl_intake, "https://ritindia.edu/intake", 1, "Intake Page", "intake")

    assert unclass is None
    assert len(recs_intake) == 2
    assert recs_intake[0]["type"] == "intake"
    # Sr. No. column dropped!
    assert "Sr. No." not in recs_intake[0]["data"]
    assert recs_intake[0]["data"]["Branch Name"] == "Computer Science and Engineering"
    assert recs_intake[0]["data"]["Sanctioned Intake"] == "180"
    # Context updated with title-only row
    assert "Undergraduate Programs" in recs_intake[0]["context"]

    # 3. Faculty table
    html_faculty = """
    <table>
      <thead>
        <tr>
          <th>Name of Faculty</th>
          <th>Designation</th>
          <th>Qualification</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Dr. A. B. Patil</td><td>Professor</td><td>Ph.D. Computer Engg</td></tr>
      </tbody>
    </table>
    """
    soup_fac = BeautifulSoup(html_faculty, "html.parser")
    rows, header_rows = table_to_rows(soup_fac.find("table"))
    tbl_fac = {"rows": rows, "header_rows": header_rows, "context": "CSE Faculty"}
    recs_fac, unclass = process_table(tbl_fac, "https://ritindia.edu/faculty", 1, "Faculty Page", "academics")

    assert unclass is None
    assert len(recs_fac) == 1
    assert recs_fac[0]["type"] == "faculty"
    assert recs_fac[0]["data"]["Designation"] == "Professor"
    assert recs_fac[0]["data"]["Qualification"] == "Ph.D. Computer Engg"

    # 4. Unclassifiable table (no matching signatures in header)
    html_unclass = """
    <table>
      <thead>
        <tr><th>Inventory Item</th><th>Quantity</th><th>Condition</th></tr>
      </thead>
      <tbody>
        <tr><td>Basketball</td><td>10</td><td>Good</td></tr>
      </tbody>
    </table>
    """
    soup_unclass = BeautifulSoup(html_unclass, "html.parser")
    rows, header_rows = table_to_rows(soup_unclass.find("table"))
    tbl_unclass = {"rows": rows, "header_rows": header_rows, "context": "Sports Equipment"}
    recs_unclass, unclass = process_table(tbl_unclass, "https://ritindia.edu/sports", 1, "Sports Page", "general")

    assert len(recs_unclass) == 0
    assert unclass is not None
    assert unclass["headers"] == ["Inventory Item", "Quantity", "Condition"]

def test_manual_csv_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pages_file = tmp_path / "pages.jsonl"
        records_file = tmp_path / "records.jsonl"
        unclass_file = tmp_path / "unclassified.jsonl"
        db_file = tmp_path / "test.db"

        # 1. Write pages.jsonl with a scraped fee record: Open = 100000
        page_data = {
            "url": "https://ritindia.edu/fees",
            "page": 1,
            "title": "Fees",
            "category": "fees",
            "tables": [
                {
                    "rows": [
                        ["Category", "Tuition Fee"],
                        ["Open", "100000"]
                    ],
                    "header_rows": 1,
                    "context": "B.Tech Tuition"
                }
            ]
        }
        with open(pages_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(page_data) + "\n")

        # 2. Write manual/fees.csv with an override: Open = 105000 (same context and keys)
        old_manual = config.MANUAL_DIR
        config.MANUAL_DIR = tmp_path / "manual"
        config.MANUAL_DIR.mkdir()

        manual_fee_csv = config.MANUAL_DIR / "fees.csv"
        with open(manual_fee_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["context", "Category", "Tuition Fee", "source"])
            writer.writerow(["B.Tech Tuition", "Open", "105000", "manual/override"])

        try:
            total_recs, unclass_count = run_normaliser(
                pages_jsonl_path=pages_file,
                records_jsonl_path=records_file,
                unclassified_jsonl_path=unclass_file,
                db_path=db_file
            )

            # Check that total records is 1 (deduped) and the value is the manual 105000
            with open(records_file, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]

            assert len(lines) == 1
            assert lines[0]["data"]["Tuition Fee"] == "105000"
            assert lines[0]["source"] == "manual"

            # Check SQLite table
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT data_json, source FROM records WHERE type = 'fees'")
            row = cursor.fetchone()
            assert row is not None
            data = json.loads(row[0])
            assert data["Tuition Fee"] == "105000"
            assert row[1] == "manual"
            conn.close()
        finally:
            config.MANUAL_DIR = old_manual

def test_task2_real_data_normalisation():
    # Run normaliser on real data
    total_recs, unclass_count = run_normaliser()
    assert total_recs > 0
    assert unclass_count == 2

    # Verify SQLite
    conn = sqlite3.connect(str(config.DB_PATH))
    cursor = conn.cursor()

    # 1. Computer Engineering 180 exists
    cursor.execute("SELECT data_json, source_url FROM records WHERE type = 'intake' AND data_json LIKE '%Computer Engineering%' AND data_json LIKE '%180%'")
    row = cursor.fetchone()
    assert row is not None, "Computer Engineering 180 intake record not found"
    data = json.loads(row[0])
    assert data.get("Program") == "Computer Engineering"
    assert data.get("Intake Capacity") == "180"
    assert "admission.php" in row[1] or "undergraduate.php" in row[1]

    # 2. Civil Engineering 60 collapsed across sources
    cursor.execute("SELECT count(*), source_url FROM records WHERE type = 'intake' AND data_json LIKE '%Civil Engineering%' AND data_json LIKE '%60%'")
    rows = cursor.fetchall()
    assert len(rows) == 1, f"Expected 1 collapsed Civil Engineering 60 row, got {len(rows)}"
    # Verify multiple sources listed
    src_urls = rows[0][1]
    assert "," in src_urls, f"Expected multiple URLs in source_url, got: {src_urls}"

    # 3. UG Total 840 is marked is_total: true
    cursor.execute("SELECT is_total, data_json, key_text FROM records WHERE type = 'intake' AND data_json LIKE '%UG Total%'")
    row_total = cursor.fetchone()
    assert row_total is not None, "UG Total row not found"
    assert row_total[0] == 1, f"Expected is_total=1, got {row_total[0]}"
    assert "computer engineering" not in row_total[2].lower()

    # 4. Exam coordinator table classified as contacts
    cursor.execute("SELECT count(*) FROM records WHERE type = 'contacts' AND key_text LIKE '%examination co-ordinators%'")
    assert cursor.fetchone()[0] >= 1, "Exam coordinators not classified under contacts"

    conn.close()

if __name__ == "__main__":
    test_classify_and_process_tables()
    test_manual_csv_override()
    test_task2_real_data_normalisation()
    print("test_normaliser: ALL PASSED")
