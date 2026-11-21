"""Unit tests for Task C RAG Pipeline.
Tests:
- Exact fee answer for fixture data
- Exact intake answer for fixture data
- Exact HOD answer for fixture data
- Out-of-scope question -> NO_ANSWER
- grounded() rejects an answer with an invented number
- Image-PDF query returns the link, not invented content
"""

import json
import sqlite3
import tempfile
from pathlib import Path
import numpy as np

import config
from backend.rag import RAGPipeline
from normaliser.records import save_to_sqlite

def test_grounded_validation():
    rag = RAGPipeline()
    context = "The fee for Open category is INR 105000. Contact: info@ritindia.edu or 02342-220329."

    # Valid grounded answers
    assert rag.grounded("The Open fee is INR 105000.", context) is True
    assert rag.grounded("Contact info@ritindia.edu", context) is True
    assert rag.grounded("Call 02342-220329 for details.", context) is True

    # Invented number -> must reject!
    assert rag.grounded("The fee is INR 120000.", context) is False
    assert rag.grounded("There are 50 seats.", context) is False

    # Invented email -> must reject!
    assert rag.grounded("Email admin@ritindia.edu", context) is False

    # Invented phone -> must reject!
    assert rag.grounded("Call 9876543210", context) is False

    # Invented URL -> must reject!
    assert rag.grounded("Visit https://fakewebsite.com", context) is False

def test_rag_end_to_end_on_fixtures():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_db = tmp_path / "test.db"
        test_emb = tmp_path / "embeddings.npy"
        test_meta = tmp_path / "metadata.jsonl"

        old_db = config.DB_PATH
        old_emb = config.EMB_PATH
        old_meta = config.META_PATH

        config.DB_PATH = test_db
        config.EMB_PATH = test_emb
        config.META_PATH = test_meta

        try:
            # 1. Populate SQLite records for fee, intake, hod
            records = [
                {
                    "id": "fee_cse_open",
                    "type": "fees",
                    "source_url": "https://ritindia.edu/fees.html",
                    "page": 1,
                    "context": "B.Tech Fees 2026",
                    "data": {"Category": "Open", "Tuition Fee": "105000", "Branch": "Computer Science"},
                    "key_text": "B.Tech Fees 2026 Category Open Tuition Fee 105000 Branch Computer Science cse",
                    "source": "scraped"
                },
                {
                    "id": "intake_cse",
                    "type": "intake",
                    "source_url": "https://ritindia.edu/intake.html",
                    "page": 1,
                    "context": "UG Sanctioned Intake",
                    "data": {"Branch": "Computer Science and Engineering", "Intake": "180"},
                    "key_text": "UG Sanctioned Intake Branch Computer Science and Engineering cse Intake 180",
                    "source": "scraped"
                },
                {
                    "id": "hod_cse",
                    "type": "hods",
                    "source_url": "https://ritindia.edu/departments.html",
                    "page": 1,
                    "context": "Department Heads",
                    "data": {"Department": "Computer Science and Engineering", "HOD Name": "Dr. N. V. Dharwadkar"},
                    "key_text": "Department Heads Department Computer Science and Engineering cse HOD Name Dr. N. V. Dharwadkar",
                    "source": "scraped"
                }
            ]
            save_to_sqlite(records, test_db)

            # 2. Build semantic embeddings and metadata for documents & image-PDF links
            meta_items = [
                {
                    "kind": "link",
                    "text": "Fee Structure PDF: Scanned Document",
                    "title": "Fee Structure Scanned PDF",
                    "url": "https://ritindia.edu/scanned_fees.pdf",
                    "category": "fees",
                    "pdf_type": "image"
                },
                {
                    "kind": "doc",
                    "text": "Rajarambapu Institute of Technology was founded by late Dr. Bapuji Salunkhe in 1983. It is situated in Rajaramnagar, Sakharale, Sangli.",
                    "title": "Campus History",
                    "url": "https://ritindia.edu/about.html",
                    "category": "general"
                }
            ]

            rag = RAGPipeline()
            vecs = rag.model.encode([m["text"] for m in meta_items], convert_to_numpy=True, normalize_embeddings=True)
            np.save(test_emb, vecs.astype(np.float32))
            with open(test_meta, "w", encoding="utf-8") as f:
                for m in meta_items:
                    f.write(json.dumps(m) + "\n")

            rag.load_index()

            # Test 1: Exact fee query
            res = rag.answer("What is the fee for Open category in CSE?")
            assert res["mode"] == "structured"
            assert "105000" in res["answer"]
            assert "https://ritindia.edu/fees.html" in res["sources"]

            # Test 2: Exact intake query
            res = rag.answer("How many seats in CSE intake?")
            assert res["mode"] == "structured"
            assert "180" in res["answer"]
            assert "https://ritindia.edu/intake.html" in res["sources"]

            # Test 3: Exact HOD query
            res = rag.answer("Who is the HOD of Computer Science?")
            assert res["mode"] == "structured"
            assert "Dr. N. V. Dharwadkar" in res["answer"]
            assert "https://ritindia.edu/departments.html" in res["sources"]

            # Test 4: Out-of-scope question
            res = rag.answer("How do I bake a chocolate cake?")
            assert res["mode"] == "no_answer"
            assert res["answer"] == config.NO_ANSWER

            # Test 5: Image-PDF link query
            res = rag.answer("Where can I find the scanned fees document?")
            assert res["mode"] == "link"
            assert "https://ritindia.edu/scanned_fees.pdf" in res["sources"]
            assert "not searchable" in res["answer"].lower()

        finally:
            config.DB_PATH = old_db
            config.EMB_PATH = old_emb
            config.META_PATH = old_meta

if __name__ == "__main__":
    test_grounded_validation()
    test_rag_end_to_end_on_fixtures()
    print("test_rag: ALL PASSED")
