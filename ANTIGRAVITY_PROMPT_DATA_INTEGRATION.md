# PROMPT — paste into Antigravity (workspace = the `rit_assistant_v3/` project, after unzipping `rit_v3_legacy_import.zip` into its root)

You are continuing work on **rit_assistant_v3** (RIT institutional information assistant). The pipeline already exists and passes its tests on fixture data: `scraper/`, `normaliser/records.py`, `indexer/build_index.py`, `backend/{rag,access,app}.py`. **This stage plugs in the first real data**: an older project's collected data has been converted into v3 formats. Your job is to integrate it, make the tools handle its real shapes, and prove it with tests built from the real data.

Inspect the existing code before editing it; follow its conventions. Work task by task; after each one run its tests and `python -m py_compile` on changed files and summarise in a few lines.

## 0. Non-negotiables (unchanged)
1. Answers come **only** from the indexed data; never invent, compute, round, merge or "fix" a value. No data → `config.NO_ANSWER`.
2. One embedding model: `all-MiniLM-L6-v2`, 384-d, normalised.
3. phi/Ollama may only rephrase *document-text* answers, with the `grounded()` check. Structured rows, cut-off values and links are returned verbatim, never through the LLM.
4. Guests: 5 queries; institute users unlimited (signed token). Offline after scraping.
5. **Never hand-edit the converted data** (`legacy_pages.jsonl`, the CSVs). If something is wrong, fix the code, or tell me what to correct in the source.

## 1. What was delivered (read these first)
- `data/CONVERSION_REPORT.md` — counts, warnings, things to verify. **Read it fully.**
- `tools/convert_legacy.py` — the converter (the old folder is NOT in this workspace; don't re-run it).
- `scraper/pages_io.py` — `iter_pages()`: reads `pages.jsonl` (fresh crawl) then `legacy_pages.jsonl`; same key → fresh wins. Key = `dedupe_key` if present else `(url, page, type)`.
- `data/raw/legacy_pages.jsonl` (580 records) in the v3 record schema, plus extra fields: `origin` (`legacy_scrape` | `curated:institute_info.json` | `legacy_scrape:departments_info.json`), `needs_rescrape`, `notes`, `title_source`, `dedupe_key`.
  - `type:"html"`: 22 old web pages. **Tables only, `text` is empty** (the old scraper discarded page text) → need re-scrape. 3 pages have words fused in cells (`theAllotment Letterat…`).
  - `type:"pdf"`: 533 pages from 12 text/mixed PDFs, `pdf_type` = `text` | `mixed`. `type:"pdf_link"`: 7 link stubs (5 image-only PDFs + the 2 mixed PDFs).
  - docs from curated data: `curated::*` (institution, leadership, facilities, placements, admission details) with url `https://ritindia.edu`, and `department::*` (11 departments: HOD name + HOD message).
- `data/raw/pdf_registry.legacy.json` — every PDF with its classification (image PDFs = calendars ×4 + brochure: link only, never parsed).
- `data/manual/{fees,cutoffs,hods,contacts,pdf_links}.csv` — UTF-8 **with BOM**, CRLF, extra columns `context`/`source`, blank cells. `fees/cutoffs/contacts` are *curated summaries* (no year/round/category) and must be verified by me.
- `data/legacy_quarantine/department_stats.json` — **not to be indexed** (unitless counters like "15 HIGHEST SALARY PACKAGE").
- `tests/legacy_questions.csv` — 20 old questions (reference only); `tests/test_legacy_import.py` (passes).

**Table shape in `legacy_pages.jsonl`**: `tables:[{index, context, header_rows, rows:[[str]]}]`, merged cells already expanded for HTML; for PDF tables empty cells are `""` and merged *header* cells are NOT filled (only the first column of a merged group has the text). `context` = title row or the page's "…Cut off for CAP … Round (YYYY-YY)" line.

## 2. Tasks

### Task 1 — Single loader + small config/seed fixes
- Make normaliser, indexer and any other consumer read pages **only** through `scraper.pages_io.iter_pages()`. Add a test that two files with a shared key yield the fresh record, and that records sharing a URL but with different `dedupe_key` are all kept.
- `config.TABLE_SIGNATURES["contacts"]`: add `"mail"` (the exam-coordinator table header is `Mail_ id`). `scraper/seeds.py`: set `exam_details` category to `"contacts"` (that page is the exam-coordinator list; its `Designation` column holds the branch).
- Manual CSV loader: open with `utf-8-sig`, tolerate CRLF, drop blank cells, treat `context`/`source` as metadata, **ignore `*.generated.csv`**, strip header whitespace. `pdf_links.csv` rows (`title,url,category,description`, description may be empty) → `kind:"link"`; their searchable text = title (+ description if given) only.
- Add a proper root `.gitignore` (`.env`, `data/db/`, `data/pdfs/`, `data/index/`, `__pycache__/`, `venv/`). Make sure no `.env`/secrets exist in the workspace. (In the old project `.gitignore` was a *folder* containing a `.env`, so nothing was ignored.)

### Task 2 — Normaliser on the real tables
Run `python -m normaliser.records`, then check against this **expected outcome** and fix the classifier/code (not the data):
- Intake: tables with headers `Intake Capacity` (pages `programs_*`) and `Sanctioned Strength` (`admission_enquiry`, `programs_management`) → type `intake`. Example row that must exist: `{"Program":"Computer Engineering","Intake Capacity":"180"}`.
- Same program + same figure in two pages (e.g. Civil Engineering 60) must **not appear twice in an answer**: collapse identical (program-name key, numbers) across sources into one answer row listing all source URLs. Keep headers verbatim in storage.
- Rows like `UG Total 840` are totals: store with `is_total:true`; they answer "total intake" questions but never match a program name.
- Table of exam coordinators (`Name, Designation, Mail_ id, Contact No.`) → `contacts` (not `faculty`).
- Use the page `title`/`name` words (e.g. "programs postgraduate", "admission enquiry") as **hidden** extra tokens in `key_text` to separate UG/PG/management tables with empty `context`. Do not show them in answers.
- Print every unclassified table (url, header, rows) and tell me what they are (e.g. `admission_faqs`, `admission_enquiry` tables 2-8, program tables); propose signature changes; do not guess. Tables that stay unclassified must still be searchable: render them with `scraper.tables.render_table` into doc chunks for the indexer.
- PDF tables: **do not** also render PDF tables into doc text (the PDF `text` already contains them); doc chunks for PDF pages come from `text` only.

### Task 3 — Cut-off tables → exact lookup table (the main work)
The 10 cut-off PDFs (FY/DSY B.Tech, FY/DSY Diploma, M.Tech, MBA; 2024-25 and 2025-26) are wide tables:
```
row0: Branch | <garbled "Round"> | Gents  "" "" ... | Ladies "" "" ... | [extra columns: Def, EWS, TFWS, PWD, AI ...]
row1: ""     | ""               | Open SC ST VJ NT1 NT2 NT3 OBC SEBC | Open SC ST ... 
data: CIVIL  | SML NO           | 48333 94421 162097 ...
      ""     | Marks            | (85.57) (69.49) ...      ← branch is blank = same branch as the row above
```
(M.Tech uses `General` and the metric `Merit No`; some tables have a leading title row already moved into `context`; `--` and `""` mean no cut-off.)
Build a **long-format** table `cutoff_cells` in SQLite (and `data/normalised/cutoff_cells.jsonl`):
`pdf_url, page, program_level, year, round, branch, gender_or_group, category, metric, value, available, context`.
Rules:
1. Forward-fill the branch (col 0) down the rows; metric = col 1 (`SML NO` / `Merit No` / `Marks`); the values start at col 2.
2. Header: forward-fill the row-0 group label (`Gents`/`Ladies`/`General`) rightwards until the next non-empty row-0 label; category = row 1. Assert `(group, category)` is unique per table; if not, mark the table `needs_review`, log it, and **do not guess**.
3. If a continuation page's table has no header row (first row starts with a branch + metric), inherit the header of the previous page of the same PDF and mark `header_inherited:true`. Every data row must have the same number of cells as the header after padding; else log the table.
4. `value` is the cell **string exactly as written** (`(85.57)`, `--`, `""` stay as they are); `available` = value not in `{"", "-", "--"}`. Never convert to numbers, never rank, never compare.
5. `year`, `round`, `program_level` are parsed from `context` with regexes (examples: `F. Y. B. Tech. Cut off for CAP I Round (2025-2026)`, `F. Y. Diploma Cut off for CAP Ist Round (2025-26)`, `M. Tech. Cut off list for CAP First Round (2024-2025)`); if a part does not parse, store it empty and keep the full `context`. Don't guess.
6. Index one **descriptor** per (PDF, branch) as `kind:"record"` (text: program level, round, year, branch, the available categories — **no numbers**). Routing: a cut-off intent or a top hit of this kind → query `cutoff_cells` filtered by the tokens found in the question (branch via `config.ALIASES`, year, round, category words `open sc st vj nt1 nt2 nt3 obc sebc ews tfws pwd`, gender: `girls/women/female → Ladies`, `boys/men/male → Gents`, add these synonyms to config). If the question does not say category/gender, don't dump hundreds of cells: reply listing which categories/groups exist and ask which one.
7. Answer format per cell: `<program_level> · <round> · <year> · <branch> · <group> <category>: <metric> <value>` + the PDF url. Unavailable cells: say "no cut-off listed (--)".
8. The curated `cutoffs.csv` rows (percentile/rank without year/round/category) stay a separate summary: use them only when the question has no year/round/category; the answer must show the row's `context` ("year, CAP round and category NOT stated").
9. **Tests from the real data** (assert exact strings): FY B.Tech 2025-26 CAP I, CIVIL, Gents/Open: `SML NO`=`48333`, `Marks`=`(85.57)`; DSY B.Tech 2025-26, CIVIL, Gents/Open: `2187` / `91.47`; FY Diploma 2025-26, CIVIL, Gents/Open `SML NO`=`25727`, `Marks`=`85.00`; M.Tech 2024-25, Construction, General/Open: `Merit No`=`1513`, `Marks`=`14.41`; MBA 2025-26, MBA, Gents/Open `SML NO`=`21102`. Also a sanity test: per PDF, number of cells = rows × columns, none lost, and a count of `needs_review` tables (report it).
The MBA PDF is `mixed` (pages 2 and 4 have no text/table): keep its link record and mention in answers about it that some pages are images.

### Task 4 — Indexer + retrieval over the real data
- Index kinds: `doc` (chunks of page/PDF `text`, curated docs, department docs, unclassified-table renderings), `record` (structured rows + cut-off descriptors), `link` (all `pdf_link` records + `pdf_links.csv`). Report chunk counts per kind/origin. The 477-page PO-PSO-CO PDF is large: report its chunk count and the total index build time; if it dominates the index, tell me and propose a rule (don't drop it silently).
- Sources shown to users: the page/PDF URL; for `origin: curated:*` show the label "RIT summary information (please verify on ritindia.edu)" instead of a raw file name.
- The two image-only PDF families (academic calendars, information brochure) must come back as **links**, with the note that their contents are not searchable. The `academic_calendar` web page and `exam_schedule` currently have no content; until re-scraped, questions about them return the calendar PDF links.
- Contacts: the only data are the general institute number/`director@ritindia.edu` (row field `Contact For` says so) and the exam-coordinator table. A question about the *admission* office must show the general row **with its `Contact For` label** and must not call it the admission office.
- Placement questions are answered only from the curated placement sentences, returned verbatim (their scope is visible). "Highest package for CSE" must NOT be answered with the institute-wide figure as if it were CSE's (it should return the verbatim sentence or `NO_ANSWER`; add this as an adversarial eval case).

### Task 5 — Re-scrape comparison tool
Add `tools/compare_legacy_vs_fresh.py`: after I run `python -m scraper.crawl`, compare per URL the legacy tables vs fresh tables (row counts, cell-level differences, tables that disappeared) and print/write a Markdown report. Rules: fresh wins in `iter_pages`; **never delete** the legacy file; flag any fact (fee, intake, name, number) present in legacy but absent in fresh. Test it with small synthetic fixtures in `tests/fixtures/`.

### Task 6 — Evaluation with real expectations
Create `tests/eval_questions.csv` (`question, expected_substring, expected_mode`) from `tests/legacy_questions.csv` plus new cases, each expected value taken from the converted data (state the data path for each in a comment column). Must include at least:
| Question | expected_substring | mode |
|---|---|---|
| What is the intake for Computer Engineering? | `180` | structured |
| Intake of Civil Engineering | `60` | structured |
| Who is the HOD of Civil Engineering? | `Dr. P. D. Kumbhar` | structured |
| Who is the HOD of Computer Science and Engineering? | `Dr. Sachin S. Patil` | structured |
| Who is the exam coordinator for Information Technology? | `dadaso.mane@ritindia.edu` | structured |
| Tuition fee for B.Tech open category | `1,36,522` | structured |
| FY B.Tech 2025-26 CAP I cut-off Civil Gents Open | `48333` | structured |
| Where can I see the academic calendar? | `academic-calender-sem-i-2026-27.pdf` | link |
| Where is RIT located? | `Sakharale` | semantic |
| Is there a hostel for boys? | `hostel` | semantic |
| (≥ 8 out-of-scope: weather, cricket, PM of India, Mars campus, laptop price, Python code, recipe, bitcoin) | — | no_answer |
Report the score of every case and the best `MIN_SCORE` threshold on this set **with the real index** (the fixture-based 0.35 was only a first guess); show the margin between the lowest real-answer score and the highest out-of-scope score.

### Task 7 — Final check
Run the whole chain on the real data: `normaliser` → `indexer` → all tests → `tests.run_eval` → start the API and exercise guest limit 5 / token / 429. Summarise: counts per record type, unclassified tables, `needs_review` cut-off tables, eval table, and **a list of everything you could not verify** (do not paper over gaps).

## 3. Conventions & working agreement
- Python 3.10+, run from the project root with `python -m package.module`; settings only in `config.py` (add new ones there with comments); plain-assert tests runnable with `python -m tests.<name>`; use only the real converted data or small fixtures in `tests/fixtures/`, **never invent sample data in `data/`**.
- If you need a decision from me (e.g. what an unclassified table is), stop and ask with the exact rows.
- Do not read or use anything from the old project's code or embeddings; they are intentionally not in the workspace.
