"""Unit tests for scraper HTML table parsing and combined header extraction."""

from bs4 import BeautifulSoup
from scraper.tables import norm, table_to_rows, combined_header, render_table

def test_norm():
    assert norm("  hello \n\t world  ") == "hello world"
    assert norm(None) == ""

def test_simple_table():
    html = """
    <table>
      <thead>
        <tr><th>Branch</th><th>Intake</th></tr>
      </thead>
      <tbody>
        <tr><td>Computer Science</td><td>180</td></tr>
        <tr><td>Mechanical</td><td>120</td></tr>
      </tbody>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    rows, header_rows = table_to_rows(soup.find("table"))
    assert header_rows == 1
    assert len(rows) == 3
    headers = combined_header(rows, header_rows)
    assert headers == ["Branch", "Intake"]
    assert rows[1] == ["Computer Science", "180"]
    assert rows[2] == ["Mechanical", "120"]

def test_colspan_rowspan_table():
    html = """
    <table>
      <thead>
        <tr>
          <th rowspan="2">Department</th>
          <th colspan="2">Fees (INR)</th>
        </tr>
        <tr>
          <th>Tuition Fee</th>
          <th>Development Fee</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>B.Tech CSE</td>
          <td>120000</td>
          <td>15000</td>
        </tr>
      </tbody>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    rows, header_rows = table_to_rows(soup.find("table"))
    assert header_rows == 2
    headers = combined_header(rows, header_rows)
    assert headers == ["Department", "Fees (INR) - Tuition Fee", "Fees (INR) - Development Fee"]
    assert rows[2] == ["B.Tech CSE", "120000", "15000"]

    md = render_table(rows, header_rows)
    assert "| Department | Fees (INR) - Tuition Fee | Fees (INR) - Development Fee |" in md
    assert "| B.Tech CSE | 120000 | 15000 |" in md

if __name__ == "__main__":
    test_norm()
    test_simple_table()
    test_colspan_rowspan_table()
    print("test_scraper_parse: ALL PASSED")
