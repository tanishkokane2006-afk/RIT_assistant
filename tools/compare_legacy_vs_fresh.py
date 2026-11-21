"""Compare legacy and freshly scraped RIT page data."""

import json
import re
from pathlib import Path
from typing import Iterable, Dict, List, Any

import config


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def table_signature(table: Dict[str, Any]) -> str:
    headers = table.get("headers") or (table.get("rows") or [[]])[0]
    rows = table.get("rows") or []
    return json.dumps({"headers": headers, "rows": rows}, sort_keys=True)


def facts_in_text(text: str) -> set:
    return set(re.findall(r"\b\d[\d,]*(?:\.\d+)?(?:%|/yr| per year)?\b", text, re.I))


def compare(
    legacy_path: Path = config.RAW_DIR / "legacy_pages.jsonl",
    fresh_path: Path = config.PAGES_JSONL,
    report_path: Path = config.DATA_DIR / "RESCRAPE_COMPARISON.md",
) -> Dict[str, Any]:
    legacy = read_jsonl(legacy_path)
    fresh = read_jsonl(fresh_path)

    legacy_by_url: Dict[str, List[Dict[str, Any]]] = {}
    fresh_by_url: Dict[str, List[Dict[str, Any]]] = {}
    for row in legacy:
        legacy_by_url.setdefault(row.get("url", ""), []).append(row)
    for row in fresh:
        fresh_by_url.setdefault(row.get("url", ""), []).append(row)

    report = [
        "# Legacy vs Fresh Scrape Comparison",
        "",
        f"- Legacy file: `{legacy_path}`",
        f"- Fresh file: `{fresh_path}`",
        "",
    ]
    changed_urls = 0
    disappeared = 0
    flagged_facts = []

    for url in sorted(set(legacy_by_url) | set(fresh_by_url)):
        old_pages = legacy_by_url.get(url, [])
        new_pages = fresh_by_url.get(url, [])
        old_tables = [t for p in old_pages for t in p.get("tables", [])]
        new_tables = [t for p in new_pages for t in p.get("tables", [])]

        if not new_pages:
            disappeared += 1
            report.append(f"## URL disappeared: {url}")
            report.append("")
            continue
        if not old_pages:
            continue

        old_signatures = [table_signature(t) for t in old_tables]
        new_signatures = [table_signature(t) for t in new_tables]
        if old_signatures == new_signatures:
            continue

        changed_urls += 1
        report.append(f"## URL: {url}")
        report.append("")
        report.append(f"- Legacy table count: {len(old_tables)}")
        report.append(f"- Fresh table count: {len(new_tables)}")

        max_tables = max(len(old_tables), len(new_tables))
        for index in range(max_tables):
            old = old_tables[index] if index < len(old_tables) else None
            new = new_tables[index] if index < len(new_tables) else None
            if old is None:
                report.append(f"- Table {index + 1}: added in fresh data")
                continue
            if new is None:
                report.append(f"- Table {index + 1}: disappeared from fresh data")
                continue

            old_rows = old.get("rows") or []
            new_rows = new.get("rows") or []
            report.append(
                f"- Table {index + 1}: legacy rows={len(old_rows)}, fresh rows={len(new_rows)}"
            )

            if old_rows != new_rows:
                differences = 0
                for row_index in range(max(len(old_rows), len(new_rows))):
                    old_row = old_rows[row_index] if row_index < len(old_rows) else []
                    new_row = new_rows[row_index] if row_index < len(new_rows) else []
                    for col_index in range(max(len(old_row), len(new_row))):
                        old_cell = old_row[col_index] if col_index < len(old_row) else ""
                        new_cell = new_row[col_index] if col_index < len(new_row) else ""
                        if old_cell != new_cell:
                            differences += 1
                            if differences <= 10:
                                report.append(
                                    f"  - Cell [{row_index},{col_index}]: "
                                    f"{old_cell!r} -> {new_cell!r}"
                                )
                report.append(f"  - Total differing cells: {differences}")

        old_text = json.dumps(old_tables, ensure_ascii=False)
        new_text = json.dumps(new_tables, ensure_ascii=False)
        missing_facts = facts_in_text(old_text) - facts_in_text(new_text)
        if missing_facts:
            flagged = sorted(missing_facts)
            flagged_facts.extend(flagged)
            report.append("- Potential legacy facts absent from fresh tables:")
            report.extend(f"  - `{fact}`" for fact in flagged)
        report.append("")

    report.extend([
        "## Summary",
        "",
        f"- Changed URLs: {changed_urls}",
        f"- URLs disappeared: {disappeared}",
        f"- Potential legacy facts absent: {len(set(flagged_facts))}",
    ])

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return {
        "changed_urls": changed_urls,
        "disappeared_urls": disappeared,
        "missing_facts": sorted(set(flagged_facts)),
        "report_path": str(report_path),
    }


if __name__ == "__main__":
    compare()
