# Legacy data conversion report

Source: `rit_data_collection`

## What was produced

- `data/raw/legacy_pages.jsonl`: 580 records (22 web pages, 533 PDF pages, 7 PDF link stubs, 7 curated info docs, 11 department docs)
- `data/raw/pdf_registry.legacy.json`: 17 PDFs -> {'text': 10, 'mixed': 2, 'image': 5}
- `data/manual/`: fees.csv (10 rows), cutoffs.csv (13 rows), contacts.csv (1 rows), hods.csv (11 rows), pdf_links.csv (6 rows)
- tables kept: 18 web, 553 PDF

## Repairs / duplicates

- pdf_MBA-CutOff-List-2025-26.json: removed 1 stray character(s) before the JSON
- `programs_working_prof` has the same URL as `programs_management` (kept as alias, not duplicated)
- `admission_pg_fy` has the same URL as `admission_ug_dsy` (kept as alias, not duplicated)

## Pages that need a re-scrape (python -m scraper.crawl)

ALL legacy web pages: the old scraper stored tables only, never the page text.

- no content at all (image / PDF-only / JavaScript?): exam_schedule, academic_calendar, programs_phd, rules_regulations, curriculum, courses_po_pso_co, fee_structure, admission_ug_dsy, admission_mba, admission_bba
- words fused together in cells: admission_ug_fy, admission_diploma_fy, admission_diploma_dsy

## Verify before trusting (curated `institute_info.json`)

- fees.csv, cutoffs.csv (percentile/rank with NO year, round or category), contacts.csv and the `curated::*` docs come from `institute_info.json`, which is not tied to a page URL. Check them against the official documents; fix by editing the CSVs.
- seat counts vs the scraped intake tables: 12 match, 0 differ, 1 not comparable
  - not comparable (no matching scraped row): BBA
- HODs: Robotics and Automation = Dr. S. R. Desai; Automobile Engineering (Presently Automotive Technology) = Dr. S. R. Desai -> same name for two departments, confirm.
- the only contact data is one general number and `director@ritindia.edu`; there is NO admission-office contact in the data (the old test questions Q05/Q06 expect one).

## Not indexed (quarantined / excluded)

- `legacy_quarantine/department_stats.json`: counters like '15 HIGHEST SALARY PACKAGE' / '190 RECRUITERS' have no unit or scope and repeat across departments; not used as facts.
- excluded on purpose: `.gitignore/.env` (secrets - rotate any key in it if it was shared), `usage.db` (usage counters), `suggestions.json` (names + IP addresses), old embeddings (different pipeline), `__pycache__`, old logs.
- not converted: pdf_extraction_summary.json, pdf_test_debug.json
- links with no URL in `resources.json` (add them to pdf_links.csv): academic_calendar
