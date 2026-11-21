"""
Index builder for RIT Assistant v3.
Embeds document chunks, structured records, and PDF links using sentence-transformers/all-MiniLM-L6-v2 (384-d).
Saves normalized embeddings matrix and line-by-line metadata.

Run from project root:
    python -m indexer.build_index
"""

import csv
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer

import config
from scraper.pages_io import iter_pages
from scraper.tables import render_table
from normaliser.records import record_to_text
from normaliser.cutoffs import extract_cutoff_cells_from_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("indexer.build_index")

_model_instance = None

def get_embedding_model() -> SentenceTransformer:
    """Load and cache the singleton MiniLM embedding model."""
    global _model_instance
    if _model_instance is None:
        logger.info("Loading embedding model: %s", config.MODEL_NAME)
        model = SentenceTransformer(config.MODEL_NAME)
        dim = model.get_sentence_embedding_dimension()
        assert dim == config.EMBED_DIM, (
            f"Embedding model dimension mismatch: got {dim}, expected {config.EMBED_DIM}"
        )
        _model_instance = model
    return _model_instance

def chunk_text(text: str, chunk_words: int = config.CHUNK_WORDS, overlap: int = config.CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping word chunks."""
    if not text or not text.strip():
        return []

    words = text.split()
    if len(words) <= chunk_words:
        return [" ".join(words)]

    chunks = []
    step = max(1, chunk_words - overlap)
    for i in range(0, len(words), step):
        sub = words[i : i + chunk_words]
        if sub:
            chunks.append(" ".join(sub))
        if i + chunk_words >= len(words):
            break
    return chunks

def collect_index_items() -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Collect all items to embed across kinds (doc, record, link) and origins.
    Returns: (texts_to_embed, metadata_list, stats_dict)
    """
    texts_to_embed: List[str] = []
    metadata_list: List[Dict[str, Any]] = []

    stats = {
        "kinds": {"doc": 0, "record": 0, "link": 0},
        "origins": {},
        "popso_chunks": 0
    }

    # 1. Pages via iter_pages() (doc text chunks and pdf_link records)
    for page in iter_pages():
        p_type = page.get("type", "")
        p_title = page.get("title", "")
        p_url = page.get("url", "")
        p_cat = page.get("category", "")
        p_pdf_type = page.get("pdf_type", "")
        origin = page.get("origin", "legacy_scrape")
        is_popso = "PO-PSO-CO" in p_url or "courses_po_pso_co" in page.get("name", "")

        source_label = (
            "RIT summary information (please verify on ritindia.edu)"
            if origin.startswith("curated:")
            else p_url
        )

        if p_type in ("html", "pdf"):
            raw_text = page.get("text", "")
            chunks = chunk_text(raw_text)
            for chunk in chunks:
                embed_text = f"{p_title} - {chunk}" if p_title else chunk
                texts_to_embed.append(embed_text)

                meta = {
                    "kind": "doc",
                    "text": chunk,
                    "url": p_url,
                    "source_label": source_label,
                    "title": p_title,
                    "category": p_cat,
                    "origin": origin
                }
                if p_pdf_type:
                    meta["pdf_type"] = p_pdf_type
                metadata_list.append(meta)

                stats["kinds"]["doc"] += 1
                stats["origins"][origin] = stats["origins"].get(origin, 0) + 1
                if is_popso:
                    stats["popso_chunks"] += 1

        elif p_type == "pdf_link":
            link_text = page.get("text", "") or p_title
            # Ensure scanned images have clear notice
            if p_pdf_type == "image" and "not searchable" not in link_text:
                link_text = f"{link_text}. Notice: This document contains scanned images and its contents are not searchable."

            texts_to_embed.append(link_text)
            meta = {
                "kind": "link",
                "text": link_text,
                "url": p_url,
                "source_label": source_label,
                "title": p_title,
                "category": p_cat,
                "pdf_type": p_pdf_type or "image",
                "origin": origin
            }
            metadata_list.append(meta)
            stats["kinds"]["link"] += 1
            stats["origins"][origin] = stats["origins"].get(origin, 0) + 1

    # 2. Unclassified tables (rendered as Markdown tables and indexed as doc)
    if config.UNCLASSIFIED_JSONL.exists():
        with open(config.UNCLASSIFIED_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    tbl = json.loads(line)
                except Exception:
                    continue
                ctx = tbl.get("context", "")
                rows = tbl.get("rows", [])
                h_rows = tbl.get("header_rows", 1)
                md_table = render_table(rows, h_rows)
                doc_text = f"Table: {ctx}\n{md_table}" if ctx else md_table

                texts_to_embed.append(doc_text)
                meta = {
                    "kind": "doc",
                    "text": doc_text,
                    "url": tbl.get("source_url", ""),
                    "source_label": tbl.get("source_url", ""),
                    "title": ctx or "Unclassified Table",
                    "category": tbl.get("category", "admissions"),
                    "origin": "unclassified_tables"
                }
                metadata_list.append(meta)
                stats["kinds"]["doc"] += 1
                stats["origins"]["unclassified_tables"] = stats["origins"].get("unclassified_tables", 0) + 1

    # 3. Structured records from records.jsonl
    if config.RECORDS_JSONL.exists():
        with open(config.RECORDS_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue

                r_type = rec.get("type", "")
                r_ctx = rec.get("context", "")
                r_data = rec.get("data", {})
                r_sentence = record_to_text(r_type, r_ctx, r_data)

                # Label for curated records
                r_origin = rec.get("origin", "records")
                source_lbl = (
                    "RIT summary information (please verify on ritindia.edu)"
                    if "curated" in str(rec.get("source_url", "")) or "curated" in str(r_origin)
                    else rec.get("source_url", "")
                )

                texts_to_embed.append(r_sentence)
                meta = {
                    "kind": "record",
                    "text": r_sentence,
                    "url": rec.get("source_url", ""),
                    "source_label": source_lbl,
                    "title": r_ctx or r_type,
                    "category": r_type,
                    "record_id": rec.get("id", ""),
                    "origin": "records.jsonl"
                }
                metadata_list.append(meta)
                stats["kinds"]["record"] += 1
                stats["origins"]["records.jsonl"] = stats["origins"].get("records.jsonl", 0) + 1

    # 4. Cut-off descriptors from cutoff PDFs
    try:
        _, descriptors, _ = extract_cutoff_cells_from_pages()
        for desc in descriptors:
            desc_text = desc["text"]
            texts_to_embed.append(desc_text)
            meta = {
                "kind": "record",
                "text": desc_text,
                "url": desc.get("pdf_url", ""),
                "source_label": desc.get("pdf_url", ""),
                "title": f"{desc.get('branch', '')} Cut-off ({desc.get('program_level', '')} {desc.get('year', '')})",
                "category": "cutoffs",
                "origin": "cutoff_descriptors",
                "details": desc
            }
            metadata_list.append(meta)
            stats["kinds"]["record"] += 1
        stats["origins"]["cutoff_descriptors"] = len(descriptors)
    except Exception as e:
        logger.error("Failed extracting cutoff descriptors: %s", e)

    # 5. Rows of data/manual/pdf_links.csv
    if config.MANUAL_PDF_LINKS_CSV.exists():
        try:
            with open(config.MANUAL_PDF_LINKS_CSV, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                count_manual = 0
                for row in reader:
                    title = row.get("title", "").strip()
                    url = row.get("url", "").strip()
                    category = row.get("category", "general").strip()
                    desc = row.get("description", "").strip()

                    link_text = f"{title}: {desc}" if desc else title
                    texts_to_embed.append(link_text)
                    meta = {
                        "kind": "link",
                        "text": link_text,
                        "url": url,
                        "source_label": url,
                        "title": title,
                        "category": category,
                        "pdf_type": "manual",
                        "origin": "manual_pdf_links"
                    }
                    metadata_list.append(meta)
                    stats["kinds"]["link"] += 1
                    count_manual += 1
                stats["origins"]["manual_pdf_links"] = count_manual
        except Exception as e:
            logger.error("Failed loading manual PDF links %s: %s", config.MANUAL_PDF_LINKS_CSV, e)

    return texts_to_embed, metadata_list, stats

def build_index(
    emb_path: Path = config.EMB_PATH,
    meta_path: Path = config.META_PATH
) -> Tuple[int, Tuple[int, ...], Dict[str, Any], float]:
    """
    Build L2-normalized 384-dimensional embeddings matrix and write metadata.
    Returns: (num_items, shape, stats, build_time_seconds)
    """
    config.ensure_directories()
    t0 = time.time()

    texts_to_embed, metadata_list, stats = collect_index_items()

    if not texts_to_embed:
        raise RuntimeError("Index is empty: no documents, records, or links found to embed.")

    assert len(texts_to_embed) == len(metadata_list)

    model = get_embedding_model()
    dim = model.get_sentence_embedding_dimension()
    assert dim == config.EMBED_DIM, f"Model dimension {dim} != {config.EMBED_DIM}"

    logger.info("Embedding %d items with %s (%d-d)...", len(texts_to_embed), config.MODEL_NAME, dim)
    embeddings = model.encode(
        texts_to_embed,
        batch_size=64,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True
    )
    embeddings = embeddings.astype(np.float32)

    # Double check normalization
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

    # Save embeddings matrix
    np.save(emb_path, embeddings)

    # Save line-by-line metadata (row i <-> line i)
    with open(meta_path, "w", encoding="utf-8") as f:
        for meta in metadata_list:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    build_time = time.time() - t0
    logger.info("Successfully built index in %.1fs: %d vectors saved to %s", build_time, len(metadata_list), emb_path)
    return len(metadata_list), embeddings.shape, stats, build_time

if __name__ == "__main__":
    count, shape, stats, b_time = build_index()
    print(f"\nIndex built in {b_time:.1f}s: {count} items, shape {shape}")
    print(f"Kinds: {stats['kinds']}")
    print(f"Origins: {stats['origins']}")
    print(f"PO-PSO-CO chunks: {stats['popso_chunks']} ({(stats['popso_chunks'] / count) * 100:.1f}%)")
