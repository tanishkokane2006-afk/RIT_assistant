"""Central configuration for RIT Assistant v3 (Rajarambapu Institute of Technology).
All settings, tunables, paths, and signatures live here.
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple

# Offline HuggingFace execution
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

BASE_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Directories & Files
# --------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_HTML_DIR = RAW_DIR / "html"
PDF_DIR = DATA_DIR / "pdfs"
MANUAL_DIR = DATA_DIR / "manual"
NORMALISED_DIR = DATA_DIR / "normalised"
INDEX_DIR = DATA_DIR / "index"
DB_DIR = DATA_DIR / "db"

PAGES_JSONL = RAW_DIR / "pages.jsonl"
PDF_REGISTRY = RAW_DIR / "pdf_registry.json"
SCRAPE_LOG = RAW_DIR / "scrape_log.json"

UNCLASSIFIED_JSONL = NORMALISED_DIR / "unclassified_tables.jsonl"
RECORDS_JSONL = NORMALISED_DIR / "records.jsonl"
MANUAL_PDF_LINKS_CSV = MANUAL_DIR / "pdf_links.csv"

DB_PATH = DB_DIR / "assistant.db"

EMB_PATH = INDEX_DIR / "embeddings.npy"
META_PATH = INDEX_DIR / "metadata.jsonl"

def ensure_directories():
    """Ensure all required project directories exist."""
    dirs = [
        DATA_DIR,
        RAW_DIR,
        RAW_HTML_DIR,
        PDF_DIR,
        MANUAL_DIR,
        NORMALISED_DIR,
        INDEX_DIR,
        DB_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

ensure_directories()

# --------------------------------------------------------------------------
# Scraper Tunables
# --------------------------------------------------------------------------
VERIFY_SSL = False
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RITAssistantBot/3.0"
RESPECT_ROBOTS = True
REQUEST_TIMEOUT = 15
RETRIES = 3
MAX_PDF_MB = 20
CRAWL_DELAY = 1.0
FOLLOW_PDF_LINKS = True
MAX_PDFS_PER_PAGE = 10

# --------------------------------------------------------------------------
# Embeddings & Retrieval
# --------------------------------------------------------------------------
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
CHUNK_WORDS = 250
CHUNK_OVERLAP = 50
TOP_K = 5
MIN_SCORE = 0.35
MAX_ROWS = 6

NO_ANSWER = "I could not find information about that in the official RIT records."

# --------------------------------------------------------------------------
# LLM Tunables (Optional Local Phi via Ollama)
# --------------------------------------------------------------------------
USE_LLM = os.getenv("USE_LLM", "true").lower() in ("true", "1", "yes")
LLM_MODEL = os.getenv("LLM_MODEL", "phi")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# --------------------------------------------------------------------------
# Structured Table Signatures
# --------------------------------------------------------------------------
RECORD_TYPES: Tuple[str, ...] = ("fees", "intake", "cutoffs", "hods", "faculty", "contacts")

# A table is eligible for a type ONLY IF the header text itself contains one of its words.
# Page category breaks ties (+2).
TABLE_SIGNATURES: Dict[str, List[str]] = {
    "fees": [
        "fee", "fees", "tuition", "tution", "development", "caution", "amount",
        "exam fee", "examination fee", "gymkhana", "eligibility fee", "total fee"
    ],
    "intake": [
        "intake", "sanctioned intake", "sanctioned strength", "intake capacity",
        "seats", "capacity", "quota seats", "total intake", "seat", "strength"
    ],
    "cutoffs": [
        "cutoff", "cut-off", "percentile", "merit", "rank", "closing rank", "cet score", "jee score"
    ],
    "hods": [
        "hod", "head of department", "head of dept", "h.o.d.", "department head"
    ],
    "faculty": [
        "faculty", "professor", "designation", "qualification", "assistant professor",
        "associate professor", "staff", "lecturer", "experience"
    ],
    "contacts": [
        "contact", "phone", "telephone", "email", "mail", "mobile", "address", "extension",
        "fax", "helpline", "in-charge"
    ]
}

# --------------------------------------------------------------------------
# Query Intent & Aliases
# --------------------------------------------------------------------------
ALIASES: Dict[str, List[str]] = {
    "cse": ["computer science and engineering", "computer science & engineering", "computer science"],
    "csit": ["computer science and information technology", "information technology", "cs & it", "cs and it", "it"],
    "it": ["information technology", "computer science and information technology", "csit", "cs & it"],
    "etc": ["electronics and telecommunication", "electronics & telecommunication", "ece"],
    "ece": ["electronics and telecommunication", "electronics & telecommunication", "etc"],
    "me": ["mechanical engineering", "mech"],
    "civil": ["civil engineering"],
    "ee": ["electrical engineering"],
    "aids": ["artificial intelligence and data science", "ai & ds", "ai and ds"],
    "aiml": ["artificial intelligence and machine learning", "ai & ml", "ai and ml"],
    "dsy": ["direct second year", "lateral entry"],
    "fy": ["first year", "1st year"],
    "btech": ["undergraduate", "b.tech", "b.e.", "b tech"],
    "mtech": ["postgraduate", "m.tech", "m.e.", "m tech"],
    "mba": ["management", "m.b.a."],
    "bba": ["b.b.a.", "bachelor of business administration"],
    "phd": ["doctorate", "ph.d.", "research"],
}

# --------------------------------------------------------------------------
# Access Control & Security
# --------------------------------------------------------------------------
GUEST_LIMIT = 5
_env_domains = os.getenv("RIT_INSTITUTE_DOMAINS")
if _env_domains:
    INSTITUTE_DOMAINS: Tuple[str, ...] = tuple(d.strip().lower() for d in _env_domains.split(",") if d.strip())
else:
    INSTITUTE_DOMAINS: Tuple[str, ...] = ("ritindia.edu",)
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "rit_assistant_secret_key_change_in_prod")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))  # 24 hours
MAX_QUERY_CHARS = 500
CORS_ORIGINS: List[str] = ["*"]

# --------------------------------------------------------------------------
# UI & Feedback Settings
# --------------------------------------------------------------------------
INSTITUTE_NAME = os.getenv("RIT_INSTITUTE_NAME", "Rajarambapu Institute of Technology")
ASSISTANT_NAME = os.getenv("RIT_ASSISTANT_NAME", "RIT Assistant")
SUPPORT_EMAIL = os.getenv("RIT_SUPPORT_EMAIL", "director@ritindia.edu")
PRIVACY_URL = os.getenv("RIT_PRIVACY_URL", "#privacy")
ADMIN_KEY = os.getenv("RIT_ADMIN_KEY")  # Must be >= 16 chars when set to enable admin API
FEEDBACK_DB_PATH = Path(os.getenv("RIT_FEEDBACK_DB", str(DB_DIR / "feedback.db")))
FEEDBACK_RETENTION_DAYS = int(os.getenv("RIT_FEEDBACK_RETENTION_DAYS", "365"))

# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate() -> bool:
    """Validate project configuration and directory accessibility."""
    ensure_directories()
    assert EMBED_DIM == 384, f"Invalid EMBED_DIM: {EMBED_DIM}, must be 384"
    assert GUEST_LIMIT > 0, "GUEST_LIMIT must be positive"
    assert len(TOKEN_SECRET) >= 16, "TOKEN_SECRET must be at least 16 chars"
    assert len(RECORD_TYPES) == 6, "RECORD_TYPES must match specification"
    return True

if __name__ == "__main__":
    validate()
    print("Configuration validated successfully.")
    print(f"Base Directory: {BASE_DIR}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"Embedding Model: {MODEL_NAME} ({EMBED_DIM}-d)")
    print(f"Guest Limit: {GUEST_LIMIT} queries")
