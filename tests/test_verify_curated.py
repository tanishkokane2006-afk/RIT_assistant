"""
Tests for Task 3b: Curated facts verification.
Tests real data:
- Rank 20264 is found at COMP. ENGG / Gents / Open / SML NO in FY B.Tech 2024-25 PDF
- Rank 31116 is NOT FOUND in cutoff_cells
- Robotics HOD is PARTIAL
- Civil HOD is MATCHED
"""

import sqlite3
import config
from tools.verify_curated import verify_cutoffs, verify_hods

def test_rank_20264_found():
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT pdf_url, page, program_level, year, branch, gender_or_group, category, metric, value "
        "FROM cutoff_cells WHERE value = '20264'"
    )
    matches = c.fetchall()
    conn.close()

    assert len(matches) > 0, "Rank 20264 must be present in cutoff_cells"
    # Verify at least one match is COMP. ENGG / Gents / Open / SML NO / 2024-25
    found = any(
        "COMP" in m[4] and m[5] == "Gents" and m[6] == "Open" and m[7] == "SML NO" and "2024-25" in m[3]
        for m in matches
    )
    assert found, f"Rank 20264 not found in expected cell: {matches}"

def test_rank_31116_not_found():
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM cutoff_cells WHERE value = '31116'")
    matches = c.fetchall()
    conn.close()
    assert len(matches) == 0, f"Rank 31116 expected NOT FOUND, but found: {matches}"

def test_hods_status():
    report_rows = verify_hods()
    hod_dict = {r["Item"]: r for r in report_rows}

    # Robotics and Automation should be PARTIAL
    robotics = hod_dict.get("Robotics and Automation")
    assert robotics is not None, "Robotics and Automation missing from HOD report"
    assert robotics["Status"] == "PARTIAL", f"Robotics expected PARTIAL, got {robotics['Status']}"

    # Civil Engineering should be MATCHED
    civil = hod_dict.get("Civil Engineering")
    assert civil is not None, "Civil Engineering missing from HOD report"
    assert civil["Status"] == "MATCHED", f"Civil expected MATCHED, got {civil['Status']}"

if __name__ == "__main__":
    print("Testing rank 20264 found...")
    test_rank_20264_found()
    print("Testing rank 31116 not found...")
    test_rank_31116_not_found()
    print("Testing HODs status (Robotics PARTIAL, Civil MATCHED)...")
    test_hods_status()
    print("ALL VERIFY_CURATED TESTS PASSED!")
