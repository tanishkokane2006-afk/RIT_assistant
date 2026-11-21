"""Table parsing utilities for RIT Assistant.
Handles colspan, rowspan, multi-level combined headers, and markdown table rendering.
"""

import re
from typing import List, Tuple, Optional
from bs4 import BeautifulSoup, Tag

def norm(text: Optional[str]) -> str:
    """Normalize whitespace in text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()

def table_to_rows(table: Tag) -> Tuple[List[List[str]], int]:
    """
    Parse a BeautifulSoup <table> tag into a 2D grid of normalized strings,
    resolving colspan and rowspan correctly.
    Returns: (rows, header_rows_count)
    """
    tr_elements = table.find_all("tr", recursive=False)
    if not tr_elements:
        # Check inside tbody/thead
        tr_elements = table.find_all("tr")

    if not tr_elements:
        return [], 0

    grid: List[List[str]] = []
    # To track rowspan: occupied[r][c] = cell_value
    occupied: dict = {}

    header_rows_count = 0
    thead = table.find("thead", recursive=False)
    if thead:
        header_rows_count = len(thead.find_all("tr"))

    for r_idx, tr in enumerate(tr_elements):
        # If no explicit thead, inspect if tr consists purely of <th>
        if header_rows_count == 0 and r_idx == 0:
            if all(cell.name == "th" for cell in tr.find_all(["td", "th"])):
                header_rows_count = 1

        row: List[str] = []
        c_idx = 0
        cells = tr.find_all(["td", "th"])

        for cell in cells:
            # Advance past any cells already occupied by earlier rowspans
            while (r_idx, c_idx) in occupied:
                row.append(occupied[(r_idx, c_idx)])
                c_idx += 1

            cell_text = norm(cell.get_text(" "))
            rowspan = 1
            colspan = 1

            try:
                rowspan = int(cell.get("rowspan", 1))
            except (ValueError, TypeError):
                rowspan = 1

            try:
                colspan = int(cell.get("colspan", 1))
            except (ValueError, TypeError):
                colspan = 1

            # Populate current row across colspan
            for c in range(colspan):
                row.append(cell_text)
                # Populate future rows across rowspan
                for r in range(1, rowspan):
                    occupied[(r_idx + r, c_idx + c)] = cell_text

            c_idx += colspan

        # Fill any trailing occupied cells
        while (r_idx, c_idx) in occupied:
            row.append(occupied[(r_idx, c_idx)])
            c_idx += 1

        if any(row):  # Don't add entirely blank rows
            grid.append(row)

    if header_rows_count == 0 and grid:
        header_rows_count = 1

    header_rows_count = min(header_rows_count, len(grid))
    return grid, header_rows_count

def combined_header(rows: List[List[str]], header_rows: int = 1) -> List[str]:
    """
    Combine multi-level header rows (e.g., from colspan/rowspan) into single column names.
    Consecutive duplicates in the same column (from rowspan) are not repeated.
    """
    if not rows or header_rows <= 0:
        return []

    num_cols = max(len(r) for r in rows[:header_rows])
    combined: List[str] = []

    for c in range(num_cols):
        parts = []
        for r in range(header_rows):
            if c < len(rows[r]):
                val = norm(rows[r][c])
                if val and (not parts or parts[-1] != val):
                    parts.append(val)
        combined.append(" - ".join(parts) if parts else f"Column_{c+1}")

    return combined

def render_table(rows: List[List[str]], header_rows: int = 1) -> str:
    """Format grid rows into a clean Markdown table string."""
    if not rows:
        return ""

    headers = combined_header(rows, header_rows)
    data_rows = rows[header_rows:]

    if not data_rows:
        data_rows = [[""] * len(headers)]

    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    row_lines = []

    for r in data_rows:
        # Align length to headers
        padded = r + [""] * (len(headers) - len(r))
        row_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")

    return "\n".join([header_line, sep_line] + row_lines)
