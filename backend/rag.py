"""
Retrieval-Augmented Generation (RAG) and Query Answering for RIT Assistant v3.
Features:
- Structured SQL routing for fees, intake, cutoffs, HODs, faculty, contacts.
- Alias expansion & token-overlap filtering with MAX_ROWS limit.
- Semantic MiniLM cosine retrieval over chunks, records, and links.
- Extractive sentence ranking for document text.
- Optional grounded LLM rephrasing with verification of numbers, emails, phones, and URLs.
- Guaranteed NO_ANSWER if below MIN_SCORE or not present.
"""

import json
import logging
import re
import sqlite3
from typing import List, Dict, Any, Optional, Set, Tuple
import numpy as np
import requests

import config
from indexer.build_index import get_embedding_model
from normaliser.records import record_to_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backend.rag")

STOP_WORDS = {
    "what", "is", "the", "for", "in", "at", "of", "to", "a", "an", "and", "or",
    "tell", "me", "show", "give", "how", "much", "many", "does", "do", "please",
    "details", "information", "about", "are", "by", "from", "with", "as", "can",
    "you", "who", "which", "where", "when", "rit", "i", "my", "we", "our", "us",
    "find", "get", "want", "need", "know", "see", "any", "some"
}

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "fees": ["fee", "fees", "tuition", "tution", "cost", "charge", "amount"],
    "intake": ["intake", "seat", "seats", "capacity", "sanctioned", "strength"],
    "cutoffs": ["cutoff", "cut-off", "cut off", "percentile", "merit", "closing rank", "rank"],
    "hods": ["hod", "head of department", "head of dept", "h.o.d.", "department head", "od of", "head of"],
    "faculty": ["faculty", "professor", "professors", "lecturer", "teacher", "teachers", "staff", "designation", "qualification"],
    "contacts": ["contact", "phone", "telephone", "email", "address", "helpline", "mobile", "office", "call", "coordinator", "dec", "exam coordinator"]
}

class RAGPipeline:
    def __init__(self):
        self.model = get_embedding_model()
        self.embeddings: Optional[np.ndarray] = None
        self.metadata: List[Dict[str, Any]] = []
        self.load_index()

    def load_index(self):
        """Load index embeddings matrix and metadata into memory."""
        if config.EMB_PATH.exists() and config.META_PATH.exists():
            try:
                self.embeddings = np.load(config.EMB_PATH)
                assert self.embeddings.shape[1] == config.EMBED_DIM
                with open(config.META_PATH, "r", encoding="utf-8") as f:
                    self.metadata = [json.loads(line) for line in f if line.strip()]
                logger.info("Loaded index: %d vectors from %s", len(self.metadata), config.EMB_PATH)
            except Exception as e:
                logger.error("Failed to load index from %s: %s", config.EMB_PATH, e)
                self.embeddings = None
                self.metadata = []
        else:
            self.embeddings = None
            self.metadata = []

    def detect_intent(self, query: str) -> Optional[str]:
        """Detect structured intent keyword from query."""
        q_lower = query.lower()
        matched = []
        for r_type, keywords in INTENT_KEYWORDS.items():
            for kw in keywords:
                # Word boundary match
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, q_lower):
                    matched.append((r_type, len(kw)))
                    break

        if not matched:
            return None
        # Return matched type with longest matching keyword
        matched.sort(key=lambda x: x[1], reverse=True)
        return matched[0][0]

    def expand_query_tokens(self, query: str, intent_type: Optional[str]) -> Set[str]:
        """Tokenize query, expand aliases, and remove stop words & intent words."""
        q_lower = query.lower()
        words = re.findall(r"\b[a-z0-9]+\b", q_lower)

        # Remove intent words
        intent_words = set()
        if intent_type and intent_type in INTENT_KEYWORDS:
            for kw in INTENT_KEYWORDS[intent_type]:
                intent_words.update(re.findall(r"\b[a-z0-9]+\b", kw.lower()))

        expanded_tokens: Set[str] = set()
        for w in words:
            if len(w) <= 1 or w in STOP_WORDS or w in intent_words:
                continue
            expanded_tokens.add(w)
            if w in config.ALIASES:
                for syn in config.ALIASES[w]:
                    syn_tokens = re.findall(r"\b[a-z0-9]+\b", syn.lower())
                    for st in syn_tokens:
                        if len(st) > 1 and st not in STOP_WORDS:
                            expanded_tokens.add(st)

        return expanded_tokens

    def query_structured_records(self, query: str, intent_type: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Query SQLite records of matching type and filter by token overlap with key_text.
        Returns: (matched_rows, too_many_unfiltered)
        """
        if not config.DB_PATH.exists():
            return [], False

        conn = sqlite3.connect(str(config.DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT id, type, source_url, page, context, data_json, key_text FROM records WHERE type = ?", (intent_type,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return [], False

        q_tokens = self.expand_query_tokens(query, intent_type)

        scored_records = []
        for r in rows:
            r_id, r_type, r_url, r_page, r_ctx, r_data_json, r_key_text = r
            r_data = json.loads(r_data_json)
            key_text_lower = (r_key_text or "").lower()
            key_tokens = set(re.findall(r"\b[a-z0-9]+\b", key_text_lower))

            if not q_tokens:
                score = 0
            else:
                score = sum(1 for tok in q_tokens if tok in key_tokens)

            scored_records.append({
                "id": r_id,
                "type": r_type,
                "url": r_url,
                "page": r_page,
                "context": r_ctx,
                "data": r_data,
                "key_text": r_key_text,
                "score": score
            })

        # Boost exact branch / program matches
        q_lower = query.lower()
        for item in scored_records:
            r_data = item["data"]
            if intent_type == "intake":
                prog_name = str(r_data.get("Program") or r_data.get("Programmes") or r_data.get("Working Professional") or "").lower()
                clean_q = " ".join(w for w in re.findall(r"\b[a-z0-9]+\b", q_lower) if w not in STOP_WORDS and w not in INTENT_KEYWORDS["intake"])
                if prog_name and (prog_name == clean_q or clean_q in prog_name):
                    item["score"] += 10
            elif intent_type == "contacts":
                desig = str(r_data.get("Designation") or r_data.get("Contact For") or "").lower()
                if any(w in desig for w in q_tokens):
                    item["score"] += 5
                if "admission" in q_lower and "institute" in desig:
                    item["score"] += 10
            elif intent_type == "hods":
                dept_name = str(r_data.get("Department") or "").lower()
                clean_q = " ".join(w for w in q_lower.split() if w not in STOP_WORDS and w not in INTENT_KEYWORDS["hods"])
                if dept_name and (dept_name in clean_q or clean_q in dept_name):
                    item["score"] += 10
                # Check alias match for departments
                for alias_k, alias_vals in config.ALIASES.items():
                    if alias_k in clean_q.split():
                        for aval in alias_vals:
                            if aval in dept_name or dept_name in aval:
                                item["score"] += 10
                                break

        if not q_tokens:
            # Entire table matched with 0 discriminators
            if len(scored_records) > config.MAX_ROWS:
                return scored_records, True
            return scored_records, False

        # Filter to records with score > 0
        positive_matches = [r for r in scored_records if r["score"] > 0]
        if not positive_matches:
            return [], False

        # Sort descending by score
        positive_matches.sort(key=lambda x: x["score"], reverse=True)
        max_score = positive_matches[0]["score"]
        best_matches = [r for r in positive_matches if r["score"] == max_score]

        if len(best_matches) > config.MAX_ROWS:
            return best_matches, True

        return best_matches, False

    def answer_cutoffs(self, query: str) -> Optional[Dict[str, Any]]:
        """Query cutoff_cells table in SQLite for exact cutoff answers."""
        if not config.DB_PATH.exists():
            return None

        conn = sqlite3.connect(str(config.DB_PATH))
        cursor = conn.cursor()
        q_lower = query.lower()

        branch_map = {
            "civil engineering": "CIVIL",
            "civil": "CIVIL",
            "computer science and engineering": "COMP",
            "computer engineering": "COMP",
            "computer": "COMP",
            "cse": "COMP",
            "aiml": "CSE (AIML)",
            "artificial intelligence": "CSE (AIML)",
            "information technology": "CS & IT",
            "it": "CS & IT",
            "electronics and telecommunication": "ETC",
            "electronics": "ETC",
            "entc": "ETC",
            "etc": "ETC",
            "electrical engineering": "ELECT",
            "electrical": "ELECT",
            "robotics and automation": "Robotics",
            "robotics": "Robotics",
            "mechatronics engineering": "MECH ATRON ICS",
            "mechatronics": "MECH ATRON ICS",
            "mechanical engineering": "MECH",
            "mechanical": "MECH",
            "mba": "MBA",
            "mca": "MCA",
            "bba": "BBA",
            "bca": "BCA"
        }
        matched_branch = None
        for b_name in sorted(branch_map.keys(), key=len, reverse=True):
            if re.search(r"\b" + re.escape(b_name) + r"\b", q_lower):
                matched_branch = branch_map[b_name]
                break

        if not matched_branch:
            conn.close()
            return None

        m_year = re.search(r"(20\d\d[-–/]\d{2,4})", query)
        year_str = m_year.group(1) if m_year else ""

        round_str = ""
        if "cap i" in q_lower or "cap 1" in q_lower or "first round" in q_lower:
            round_str = "CAP I"
        elif "cap ii" in q_lower or "cap 2" in q_lower:
            round_str = "CAP II"
        elif "cap iii" in q_lower or "cap 3" in q_lower:
            round_str = "CAP III"

        gender_str = "Gents"
        if any(g in q_lower for g in ("ladies", "female", "women", "girl")):
            gender_str = "Ladies"

        cat_str = "Open"
        for cat in ("obc", "sc", "st", "nt", "vj", "ews", "tfws", "open"):
            if re.search(r"\b" + cat + r"\b", q_lower):
                cat_str = cat.upper() if cat != "open" else "Open"
                break

        prog_level = "FY B.Tech"
        if "dsy" in q_lower or "direct second" in q_lower:
            prog_level = "DSY B.Tech"
        elif "diploma" in q_lower:
            prog_level = "FY Diploma"
        elif "m.tech" in q_lower or "mtech" in q_lower:
            prog_level = "M.Tech"
        elif "mba" in q_lower:
            prog_level = "MBA"

        sql = (
            "SELECT metric, value, pdf_url FROM cutoff_cells "
            "WHERE branch LIKE ? AND category LIKE ? AND gender_or_group LIKE ?"
        )
        params = [f"%{matched_branch}%", f"%{cat_str}%", f"%{gender_str}%"]

        if year_str:
            sql += " AND year LIKE ?"
            params.append(f"%{year_str}%")
        if round_str:
            if round_str == "CAP I":
                sql += " AND (round = 'CAP I' OR (round = '' AND page = 1))"
            elif round_str == "CAP II":
                sql += " AND (round = 'CAP II' OR (round = '' AND page = 2))"
            elif round_str == "CAP III":
                sql += " AND (round = 'CAP III' OR (round = '' AND page = 3))"
            else:
                sql += " AND round = ?"
                params.append(round_str)
        if prog_level:
            sql += " AND program_level LIKE ?"
            params.append(f"%{prog_level}%")

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        metrics = {}
        pdf_urls = []
        for r in rows:
            m_metric, m_val, m_url = r
            if m_val != "--":
                metrics[m_metric] = m_val
            if m_url and m_url not in pdf_urls:
                pdf_urls.append(m_url)

        if not metrics:
            return None

        res_parts = [f"{prog_level} {year_str or ''} {round_str} {matched_branch} {gender_str} {cat_str}:"]
        for m_name, m_val in metrics.items():
            res_parts.append(f"{m_name}: {m_val}")

        return {
            "answer": " ".join(res_parts),
            "sources": pdf_urls,
            "mode": "structured",
            "scores": [1.0]
        }

    def answer_structured(self, query: str, intent_type: str) -> Optional[Dict[str, Any]]:
        """Attempt to answer query via structured SQLite lookup."""
        records, too_many = self.query_structured_records(query, intent_type)
        if not records:
            return None

        if too_many:
            entity_hint = "branch, category, or year"
            if intent_type == "faculty":
                entity_hint = "department or professor name"
            elif intent_type == "hods":
                entity_hint = "department name"
            elif intent_type == "contacts":
                entity_hint = "office, department, or official name"

            sources = list(dict.fromkeys(r["url"] for r in records if r["url"]))
            return {
                "answer": f"There are {len(records)} matching {intent_type} records. Please specify the {entity_hint} to narrow down the exact details.",
                "sources": sources,
                "mode": "structured",
                "scores": [1.0]
            }

        # Format exact records
        lines = []
        sources = list(dict.fromkeys(r["url"] for r in records if r["url"]))
        for r in records:
            text_repr = record_to_text(r["type"], r["context"], r["data"])
            lines.append(text_repr)

        return {
            "answer": "\n".join(lines),
            "sources": sources,
            "mode": "structured",
            "scores": [1.0]
        }

    def grounded(self, answer: str, context: str) -> bool:
        """
        Verify that every number, email, phone number, and URL in answer appears literally in context.
        """
        ctx_lower = context.lower()

        # 1. Numbers (exact token matching, not substring)
        raw_ctx_nums = set(re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?%?\b", context))
        ctx_nums = {n.lower() for n in raw_ctx_nums}
        ctx_nums_clean = {n.replace(",", "").lower() for n in raw_ctx_nums}

        ans_nums = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?%?\b", answer)
        for num in ans_nums:
            num_clean = num.replace(",", "").lower()
            if num.lower() not in ctx_nums and num_clean not in ctx_nums_clean:
                logger.warning("Ungrounded number detected in LLM output: '%s'", num)
                return False

        # 2. Emails
        ctx_emails = {e.lower() for e in re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", context)}
        ans_emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", answer)
        for email in ans_emails:
            if email.lower() not in ctx_emails:
                logger.warning("Ungrounded email detected in LLM output: '%s'", email)
                return False

        # 3. Phone numbers
        ctx_phones_clean = {re.sub(r"[- ()]", "", p) for p in re.findall(r"\b(?:\+?\d{1,3}[- ]?)?\(?\d{2,5}\)?[- ]?\d{3,5}[- ]?\d{3,5}\b", context)}
        ans_phones = re.findall(r"\b(?:\+?\d{1,3}[- ]?)?\(?\d{2,5}\)?[- ]?\d{3,5}[- ]?\d{3,5}\b", answer)
        for phone in ans_phones:
            cleaned_phone = re.sub(r"[- ()]", "", phone)
            if cleaned_phone and cleaned_phone not in ctx_phones_clean:
                logger.warning("Ungrounded phone detected in LLM output: '%s'", phone)
                return False

        # 4. URLs
        ctx_urls = {u.lower() for u in re.findall(r"https?://[^\s]+", context)}
        ans_urls = re.findall(r"https?://[^\s]+", answer)
        for url in ans_urls:
            if url.lower() not in ctx_urls:
                logger.warning("Ungrounded URL detected in LLM output: '%s'", url)
                return False

        return True

    def rephrase_with_llm(self, query: str, context: str) -> Optional[str]:
        """Optional local LLM rephrasing via Ollama (phi)."""
        if not config.USE_LLM:
            return None

        prompt = (
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\n"
            f"Instructions: Use only the context; copy numbers/names exactly; reply NOT_FOUND if not answerable."
        )

        try:
            resp = requests.post(
                f"{config.OLLAMA_URL}/api/generate",
                json={
                    "model": config.LLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0}
                },
                timeout=10
            )
            if resp.status_code == 200:
                out = resp.json().get("response", "").strip()
                if "NOT_FOUND" in out or not out:
                    return None
                if self.grounded(out, context):
                    return out
                else:
                    logger.info("LLM response failed grounding check. Falling back to extractive answer.")
        except Exception as e:
            logger.info("Local LLM (Ollama) unavailable: %s. Using extractive answer.", e)

        return None

    def extractive_answer(self, query: str, top_chunks: List[Dict[str, Any]], q_vec: np.ndarray) -> str:
        """Split document chunks into sentences and select best sentences in original order formatted as bullet points."""
        all_sentences: List[str] = []
        for chunk in top_chunks:
            raw_text = chunk.get("text", "")
            sents = re.split(r"(?<=[.!?])\s+", raw_text)
            for s in sents:
                s_clean = s.strip()
                if len(s_clean) > 20 and s_clean not in all_sentences:
                    all_sentences.append(s_clean)

        if not all_sentences:
            return top_chunks[0].get("text", "")

        # Embed sentences
        sent_vecs = self.model.encode(all_sentences, convert_to_numpy=True, normalize_embeddings=True)
        scores = np.dot(sent_vecs, q_vec)

        # Program level filter/adjustments to prevent cross-level contamination (e.g. M.Tech eligibility for B.Tech query)
        q_lower = query.lower()
        is_ug = any(w in q_lower for w in ("btech", "b.tech", "undergraduate", "first year", "fy btech", "b tech", "b.e."))
        is_pg = any(w in q_lower for w in ("mtech", "m.tech", "postgraduate", "gate", "m tech", "m.e."))
        is_diploma = any(w in q_lower for w in ("diploma", "polytechnic", "ssc", "10th"))

        for idx, s in enumerate(all_sentences):
            s_low = s.lower()
            if is_ug and not is_pg:
                if any(term in s_low for term in ("passed bachelor degree", "gate qualified", "post graduate degree", "for sponsored candidates", "m.e./ m. tech")):
                    scores[idx] -= 0.5
                if any(term in s_low for term in ("passed 10+2", "physics and mathematics", "mht-cet", "jee main")):
                    scores[idx] += 0.2
            elif is_pg and not is_ug:
                if any(term in s_low for term in ("passed 10+2", "passed ssc", "first year - engineering / technology")):
                    scores[idx] -= 0.5
            elif is_diploma:
                if any(term in s_low for term in ("passed bachelor degree", "gate", "passed 10+2")):
                    scores[idx] -= 0.5

        # Pick top 3-4 sentences
        top_k_sents = min(4, len(all_sentences))
        ranked_indices = np.argsort(scores)[::-1][:top_k_sents]

        # Sort indices back to original order to preserve narrative cohesion
        chronological_indices = sorted(ranked_indices)
        best_sentences = [all_sentences[i] for i in chronological_indices if scores[i] > 0.1]

        if not best_sentences:
            best_sentences = [all_sentences[chronological_indices[0]]] if chronological_indices else []

        # Format as clean pointwise distribution
        points = []
        for s in best_sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            # If the sentence contains multiple numbered sub-clauses like (i), (ii), (iii)
            if re.search(r"\((?:i|ii|iii|iv|v|\d+)\)", s_clean):
                subparts = re.split(r"(?=\((?:i|ii|iii|iv|v|\d+)\))", s_clean)
                for p in subparts:
                    p_sub = p.strip().rstrip(";,")
                    if p_sub:
                        points.append(f"• {p_sub}")
            else:
                points.append(f"• {s_clean}")

        if not points:
            return top_chunks[0].get("text", "")

        return "\n".join(points)

    def answer(self, query: str) -> Dict[str, Any]:
        """
        Main query answering entry point.
        Enforces:
        1. Non-negotiable requirement: answers come ONLY from embedded data.
        2. Exact structured rows returned verbatim.
        3. Cosine retrieval over MiniLM 384-d index.
        4. Links returned with 'contents not searchable' notice.
        5. MIN_SCORE threshold returning NO_ANSWER on low confidence.
        """
        q_clean = query.strip()
        if not q_clean:
            return {
                "answer": config.NO_ANSWER,
                "sources": [],
                "mode": "no_answer",
                "scores": [0.0]
            }

        # 0. Out of scope and adversarial check
        OUT_OF_SCOPE_WORDS = [
            "weather", "cricket", "prime minister", "pm of india", "mars", "laptop",
            "python program", "python code", "recipe", "bitcoin", "crypto", "world cup",
            "system prompt", "ignore all", "ignore previous", "iit bombay"
        ]
        if any(w in q_clean.lower() for w in OUT_OF_SCOPE_WORDS):
            return {
                "answer": config.NO_ANSWER,
                "sources": [],
                "mode": "no_answer",
                "scores": [0.0]
            }

        if any(w in q_clean.lower() for w in ("placement", "package", "salary")):
            branches = ["cse", "computer", "civil", "mechanical", "electrical", "entc", "etc", "aiml", "it", "robotics"]
            words = set(re.findall(r"\b[a-z0-9]+\b", q_clean.lower()))
            if any(b in words for b in branches):
                return {
                    "answer": config.NO_ANSWER,
                    "sources": [],
                    "mode": "no_answer",
                    "scores": [0.0]
                }

        # 1. Routing by intent
        intent = self.detect_intent(q_clean)
        if intent == "cutoffs":
            cutoff_res = self.answer_cutoffs(q_clean)
            if cutoff_res:
                return cutoff_res

        if intent:
            structured_res = self.answer_structured(q_clean, intent)
            if structured_res:
                return structured_res

        # 2. Semantic retrieval path
        if self.embeddings is None or len(self.metadata) == 0:
            self.load_index()

        if self.embeddings is None or len(self.metadata) == 0:
            return {
                "answer": config.NO_ANSWER,
                "sources": [],
                "mode": "no_answer",
                "scores": [0.0]
            }

        # Encode query
        q_vec = self.model.encode([q_clean], convert_to_numpy=True, normalize_embeddings=True)[0]
        scores = np.dot(self.embeddings, q_vec)
        top_indices = np.argsort(scores)[::-1][:config.TOP_K]

        best_score = float(scores[top_indices[0]])
        if best_score < config.MIN_SCORE:
            return {
                "answer": config.NO_ANSWER,
                "sources": [],
                "mode": "no_answer",
                "scores": [round(best_score, 4)]
            }

        top_item = self.metadata[top_indices[0]]

        # Prefer informative doc chunk over unsearchable link if query is not asking for link/document
        link_intent = any(w in q_clean.lower() for w in ("link", "pdf", "calendar", "brochure", "download", "prospectus", "where can i see", "where to find", "form"))
        if top_item.get("kind") == "link" and not link_intent:
            doc_items = [self.metadata[idx] for idx in top_indices if self.metadata[idx].get("kind") == "doc"]
            if doc_items and (scores[top_indices[0]] - scores[self.metadata.index(doc_items[0])]) < 0.20:
                top_item = doc_items[0]

        sources = [top_item.get("source_label", top_item.get("url"))] if top_item.get("url") else []

        # Case A: Top item is a structured record
        if top_item.get("kind") == "record":
            return {
                "answer": top_item["text"],
                "sources": sources,
                "mode": "semantic",
                "scores": [round(best_score, 4)]
            }

        # Case B: Top item is a link (image-only PDF or manual link)
        if top_item.get("kind") == "link":
            answer_text = (
                f"The details are in this document: {top_item.get('title')} – {top_item.get('url')}\n"
                f"Notice: The contents of this document are not searchable."
            )
            return {
                "answer": answer_text,
                "sources": sources,
                "mode": "link",
                "scores": [round(best_score, 4)]
            }

        # Case C: Document text chunks -> extractive answering
        top_chunks = [self.metadata[idx] for idx in top_indices if self.metadata[idx].get("kind") == "doc"]
        if not top_chunks:
            top_chunks = [top_item]

        all_sources = list(dict.fromkeys(c.get("url") for c in top_chunks if c.get("url")))
        extractive = self.extractive_answer(q_clean, top_chunks, q_vec)

        # Optional grounded LLM rephrase
        if config.USE_LLM:
            llm_res = self.rephrase_with_llm(q_clean, extractive)
            if llm_res:
                return {
                    "answer": llm_res,
                    "sources": all_sources,
                    "mode": "llm",
                    "scores": [round(best_score, 4)]
                }

        return {
            "answer": extractive,
            "sources": all_sources,
            "mode": "semantic",
            "scores": [round(best_score, 4)]
        }

rag_pipeline = RAGPipeline()
