"""Unit tests for Task B Indexer.
Tests:
- Vector shapes match metadata count (N x 384)
- Unit-norm vectors
- Link rows present (scraped and manual)
- Deterministic output for same input
- Abort on empty index
"""

import json
import csv
import tempfile
from pathlib import Path
import numpy as np

import config
from indexer.build_index import build_index, chunk_text, get_embedding_model

def test_chunk_text():
    words = [f"word{i}" for i in range(100)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_words=40, overlap=10)
    assert len(chunks) == 3
    assert chunks[0].startswith("word0")
    assert "word39" in chunks[0]
    # Check overlap
    assert "word30" in chunks[1]
    assert chunks[2].endswith("word99")

def test_build_index_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pages_file = tmp_path / "pages.jsonl"
        records_file = tmp_path / "records.jsonl"
        manual_links_csv = tmp_path / "manual_links.csv"
        emb_file = tmp_path / "embeddings.npy"
        meta_file = tmp_path / "metadata.jsonl"

        # 1. Page with text and pdf_link
        p1 = {
            "type": "html",
            "title": "About RIT",
            "url": "https://ritindia.edu/about",
            "category": "general",
            "text": "Rajarambapu Institute of Technology was established in 1983."
        }
        p2 = {
            "type": "pdf_link",
            "title": "Fee Structure PDF",
            "url": "https://ritindia.edu/fees.pdf",
            "category": "fees",
            "pdf_type": "image",
            "text": "Scanned Document: Fee Structure PDF"
        }
        with open(pages_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(p1) + "\n")
            f.write(json.dumps(p2) + "\n")

        # 2. Structured record
        r1 = {
            "id": "rec_123",
            "type": "fees",
            "source_url": "https://ritindia.edu/fees",
            "context": "B.Tech Fees",
            "data": {"Category": "Open", "Tuition Fee": "105000"}
        }
        with open(records_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(r1) + "\n")

        # 3. Manual link
        with open(manual_links_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "url", "category", "description"])
            writer.writerow(["Mandatory Disclosure", "https://ritindia.edu/md.pdf", "compliance", "AICTE mandatory disclosure 2026"])

        # Run indexer
        count, shape = build_index(
            pages_jsonl_path=pages_file,
            records_jsonl_path=records_file,
            manual_pdf_links_csv=manual_links_csv,
            emb_path=emb_file,
            meta_path=meta_file
        )

        # Expected:
        # p1 (1 chunk) + p2 (1 link) + r1 (1 record) + manual (1 link) = 4 items
        assert count == 4
        assert shape == (4, config.EMBED_DIM)
        assert shape[1] == 384

        # Read back embeddings
        embeddings = np.load(emb_file)
        assert embeddings.shape == (4, 384)
        assert embeddings.dtype == np.float32

        # Check unit norm
        norms = np.linalg.norm(embeddings, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-4)

        # Read back metadata
        with open(meta_file, "r", encoding="utf-8") as f:
            metadata = [json.loads(line) for line in f if line.strip()]
        assert len(metadata) == 4

        kinds = [m["kind"] for m in metadata]
        assert "doc" in kinds
        assert "link" in kinds
        assert "record" in kinds

        # Link records present
        links = [m for m in metadata if m["kind"] == "link"]
        assert len(links) == 2
        link_titles = [l["title"] for l in links]
        assert "Fee Structure PDF" in link_titles
        assert "Mandatory Disclosure" in link_titles

        # Deterministic check: running on the same input produces identical matrix
        emb_file2 = tmp_path / "embeddings2.npy"
        meta_file2 = tmp_path / "metadata2.jsonl"
        build_index(
            pages_jsonl_path=pages_file,
            records_jsonl_path=records_file,
            manual_pdf_links_csv=manual_links_csv,
            emb_path=emb_file2,
            meta_path=meta_file2
        )
        embeddings2 = np.load(emb_file2)
        assert np.allclose(embeddings, embeddings2, atol=1e-5)

def test_empty_index_abort():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        empty_pages = tmp_path / "empty_pages.jsonl"
        empty_records = tmp_path / "empty_records.jsonl"
        empty_csv = tmp_path / "empty.csv"

        try:
            build_index(
                pages_jsonl_path=empty_pages,
                records_jsonl_path=empty_records,
                manual_pdf_links_csv=empty_csv,
                emb_path=tmp_path / "emb.npy",
                meta_path=tmp_path / "meta.jsonl"
            )
            assert False, "Should have raised RuntimeError on empty index"
        except RuntimeError as e:
            assert "empty" in str(e).lower()

if __name__ == "__main__":
    test_chunk_text()
    test_build_index_pipeline()
    test_empty_index_abort()
    print("test_indexer: ALL PASSED")
