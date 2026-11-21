# RIT Assistant v3

Institutional Information Assistant for **Rajarambapu Institute of Technology (RIT)**.
Built with extractive table normalisation, unified MiniLM 384-dimensional dense embeddings, atomic SQLite guest rate limiting, and FastAPI.

---

## Architecture Overview

```text
rit_assistant_v3/
├── config.py                    # Central tunables, signatures, paths, and validation
├── requirements.txt
├── scraper/
│   ├── seeds.py                 # Seed list and allowed domains
│   ├── tables.py                # Table parser (colspan/rowspan, combined_header, render_table)
│   └── crawl.py                 # Crawler saving HTML & classifying PDFs into data/raw/
├── normaliser/
│   └── records.py               # HTML/PDF tables -> structured records.jsonl & SQLite
├── indexer/
│   └── build_index.py           # 384-d MiniLM embeddings & line-by-line metadata
├── backend/
│   ├── access.py                # Atomic SQLite rate limiter & HMAC-SHA256 tokens
│   ├── rag.py                   # Intent routing, semantic retrieval & grounded answering
│   └── app.py                   # FastAPI REST API
├── tests/
│   ├── fixtures/                # Isolated test fixtures (pages.jsonl)
│   ├── eval_questions.csv       # Benchmark questions & expected modes
│   ├── run_eval.py              # Automated 14-question evaluation harness
│   ├── test_scraper_parse.py    # Table parser unit tests
│   ├── test_pdf_classify.py     # PDF classification policy unit tests
│   ├── test_normaliser.py       # Table normalisation & override tests
│   ├── test_indexer.py          # Vector shape & unit-norm tests
│   ├── test_rag.py              # Intent routing & grounding verification tests
│   ├── test_access.py           # Atomic rate limiter & concurrent thread tests
│   └── test_api.py              # FastAPI endpoint tests
└── data/
    ├── raw/                     # pages.jsonl, pdf_registry.json, html snapshots
    ├── pdfs/                    # Downloaded PDF files
    ├── manual/                  # User CSV overrides (fees.csv, pdf_links.csv, etc.)
    ├── normalised/              # records.jsonl, unclassified_tables.jsonl
    ├── index/                   # embeddings.npy, metadata.jsonl
    └── db/                      # assistant.db (records and guest usage)
```

---

## 1. Non-Negotiable Rules & Policies

1. **Grounded In Truth**: Facts (fees, intake, cut-offs, faculty, HODs, contacts) are never invented or guessed. If not in the data, `config.NO_ANSWER` is returned.
2. **One Model Everywhere**: `sentence-transformers/all-MiniLM-L6-v2` (384-d, L2-normalized) for queries, documents, records, and links.
3. **Structured Facts Untouched**: Structured table rows are returned verbatim as strings.
4. **PDF Policy**:
   - `text`: Every page readable -> parsed as PDF page records.
   - `mixed`: Some pages readable -> text pages parsed + 1 link record.
   - `image`: Scanned photo PDFs -> **NEVER OCR'd**. Stored as link record only (`type: "pdf_link"`).
   - `too_large`: Over `MAX_PDF_MB` -> Link record only.
5. **Access Control**:
   - Guests get **5 queries total** (`config.GUEST_LIMIT`), tracked atomically via SQLite `BEGIN IMMEDIATE` transactions and a 1-year `guest_id` HTTP-only cookie.
   - Institute users (domain `ritindia.edu`) have **unlimited access** via signed HMAC-SHA256 tokens (`X-Institute-Token`).

---

## 2. Setup & Installation

### Requirements
- Python 3.10+
- Virtual environment recommended:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 3. Pipeline Run Order

Execute each stage in order from the project root:

### Stage 1: Crawl Website & Classify PDFs
```bash
python -m scraper.crawl                    # Scrape all seeds
python -m scraper.crawl --check            # Dry-run inspection
python -m scraper.crawl --only fee_structure,fees_page
python -m scraper.crawl --no-pdfs          # Skip PDF downloads
```

### Stage 2: Normalise Tables into Structured Records
```bash
python -m normaliser.records
```
Reads `data/raw/pages.jsonl` and `data/manual/*.csv`, outputs `data/normalised/records.jsonl`, `data/normalised/unclassified_tables.jsonl`, and stores records in SQLite `data/db/assistant.db`.

### Stage 3: Build MiniLM 384-d Vector Index
```bash
python -m indexer.build_index
```
Builds `data/index/embeddings.npy` (N × 384, L2-normalised float32) and `data/index/metadata.jsonl`.

### Stage 4: Launch FastAPI Server
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Customizing Seeds & Manual Overrides

### Adding New Seeds
Edit `scraper/seeds.py` and append an entry to `SEEDS`:
```python
_s("new_page", "academics", "https://ritindia.edu/..."),
```

### Adding Manual Records (`data/manual/<type>.csv`)
If a table on the website is unclassified or contains errors, create `data/manual/<type>.csv` (where `<type>` is one of `fees`, `intake`, `cutoffs`, `hods`, `faculty`, `contacts`).
Example: `data/manual/fees.csv`:
```csv
context,Category,Tuition Fee,Development Fee
B.Tech First Year,Open,105000,15000
```
*Manual rows always win over scraped duplicates and are marked `source: "manual"`.*

### Adding Manual PDF Links (`data/manual/pdf_links.csv`)
For scanned/photo documents that cannot be parsed:
```csv
title,url,category,description
AICTE Mandatory Disclosure 2026,https://ritindia.edu/disclosure.pdf,compliance,Official AICTE disclosure
```

---

## 5. Enabling Optional Local LLM (Phi via Ollama)

By default, `USE_LLM` is `False`, ensuring pure extractive responses. To enable local rephrasing:
1. Install and start [Ollama](https://ollama.ai/):
   ```bash
   ollama run phi
   ```
2. Configure `.env` or set environment variables:
   ```bash
   export USE_LLM=true
   export LLM_MODEL=phi
   export OLLAMA_URL=http://localhost:11434
   ```
*Safety Guarantee*: LLM rephrasing is **only** applied to narrative document chunks. Structured records (fees, intake, etc.) and links are **never sent to the LLM**. If the LLM generates any number, email, phone number, or URL not literally present in the context, `grounded()` discards the output and falls back to the extractive passage.

---

## 6. Access Control & Security

### Issuing an Institute Token
To issue an institute token for testing or authorized users:
```bash
python -m backend.access issue user@ritindia.edu --ttl 86400
```

### Passing the Token
Include the token in HTTP headers:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Institute-Token: <token>" \
  -d '{"query": "What is the fee for Open category in B.Tech?"}'
```

---

## 7. Web UI, Feedback & IT Admin Dashboard

The system includes a zero-dependency, mobile-first Web UI served directly by FastAPI.

### Features
- **User Interface (`/`)**:
  - Accessible, responsive layout with high-contrast WCAG AA compliance and light/dark theme toggle.
  - Interactive starter question chips (Admissions, Cut-offs, Departments, Campus).
  - Character counter (0/500) and keyboard shortcut (`/` to focus search).
  - Verbatim display of assistant answers with clickable sources.
  - Live quota tracking (5 free guest queries remaining, or unlimited badge for institute members).
  - Institute token login dialog storing tokens in `sessionStorage` (cleared on tab close).
  - Privacy guarantees: no cookies/tokens exposed, chat history strictly local in `sessionStorage` with "Clear Chat" button.
- **Feedback & Question Suggestions**:
  - Feedback dialog with 1-5 star rating, category selector, comment, and optional contact email.
  - "Suggest a question" and "Alert missing question" submissions for user engagement.
  - Honeypot spam defense and in-memory rate limiting (max 5 submissions/hour/user).
- **IT Admin Dashboard (`/admin`)**:
  - Requires constant-time authentication header (`X-Admin-Key` matching `RIT_ADMIN_KEY`).
  - Search, filter by status (`new`, `in_review`, `done`, `declined`) and kind.
  - Status updates and admin notes editing.
  - Top questions frequency grouping with normalised query analysis.
  - UTF-8 with BOM CSV export protected against formula injection (`=`, `+`, `-`, `@`).
  - Automated or CLI-based data retention purging (`python -m backend.feedback purge --days 365`).

### Admin Configuration
Set the admin key in environment variables (minimum 16 characters):
```bash
export RIT_ADMIN_KEY="your_secure_admin_passkey_here_16chars_min"
```

---

## 8. Running Tests & Evaluation

Run the automated evaluation benchmark:
```bash
python -m tests.run_eval
```

Run all unit and integration test suites:
```bash
python -m tests.test_scraper_parse
python -m tests.test_pdf_classify
python -m tests.test_normaliser
python -m tests.test_indexer
python -m tests.test_rag
python -m tests.test_access
python -m tests.test_api
python -m tests.test_ui_backend
python -m tests.test_ui_static_compliance
```
