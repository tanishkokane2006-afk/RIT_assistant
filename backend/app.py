"""
FastAPI application for RIT Assistant v3.
Features:
- POST /chat: query answering with institute token validation or guest cookie rate limiting.
- GET /usage: check remaining quota.
- GET /health: report index size, model, and LLM status.
- CORS support and exception shielding.
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from backend.access import access_control, verify_token
from backend.rag import rag_pipeline
from backend.feedback import router as feedback_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backend.app")

# Startup validation
config.validate()

app = FastAPI(
    title="RIT Assistant v3",
    description="Institutional AI Assistant for Rajarambapu Institute of Technology",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none';"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/admin"):
        response.headers["X-Robots-Tag"] = "noindex"
    return response

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[str]
    mode: str
    remaining: Optional[int]

class UsageResponse(BaseModel):
    user_id: str
    is_institute: bool
    remaining: Optional[int]
    allowed: bool
    unlimited: bool = Field(False, description="Whether user has unlimited queries")

class HealthResponse(BaseModel):
    status: str
    index_size: int
    model: str
    llm_enabled: bool

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error processing %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."}
    )

def resolve_user(request: Request, response: Response) -> tuple[str, bool]:
    """
    Resolve user identity:
    1. Header X-Institute-Token -> verified institute user
    2. Otherwise -> cookie guest_id (or issue new cookie)
    """
    token_header = request.headers.get("X-Institute-Token")
    if token_header:
        email = verify_token(token_header)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, expired, or untrusted institute token."
            )
        return email, True

    # Guest user via cookie
    guest_id = request.cookies.get("guest_id")
    if not guest_id:
        guest_id = f"guest_{uuid.uuid4().hex[:12]}"
        response.set_cookie(
            key="guest_id",
            value=guest_id,
            max_age=31536000,  # 1 year
            httponly=True,
            samesite="lax"
        )
    return guest_id, False

@app.get("/health", response_model=HealthResponse)
def health_endpoint():
    """System health, index status, and model configuration."""
    index_size = len(rag_pipeline.metadata) if rag_pipeline.metadata else 0
    return HealthResponse(
        status="ok",
        index_size=index_size,
        model=config.MODEL_NAME,
        llm_enabled=config.USE_LLM
    )

@app.get("/usage", response_model=UsageResponse)
def usage_endpoint(request: Request, response: Response):
    """Check remaining queries for current user."""
    user_id, is_institute = resolve_user(request, response)
    allowed, remaining = access_control.get_remaining(user_id, institute=is_institute)
    return UsageResponse(
        user_id=user_id,
        is_institute=is_institute,
        remaining=remaining,
        allowed=allowed,
        unlimited=is_institute
    )

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest, request: Request, response: Response):
    """
    Submit question to RIT Assistant.
    Enforces query length constraints and guest rate limits.
    """
    query = payload.query.strip() if payload.query else ""
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty."
        )
    if len(payload.query) > config.MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Query exceeds maximum allowed length of {config.MAX_QUERY_CHARS} characters."
        )

    user_id, is_institute = resolve_user(request, response)

    # Access control check & atomic quota consumption
    allowed, remaining = access_control.consume(user_id, institute=is_institute)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Guest query limit reached (5 queries). Please log in with an institute account for unlimited access."
        )

    # Log query without sensitive token info
    logger.info("Query received from %s (institute=%s): %s", user_id, is_institute, query)

    # Answering via RAG
    res = rag_pipeline.answer(query)

    return ChatResponse(
        answer=res["answer"],
        sources=res["sources"],
        mode=res["mode"],
        remaining=remaining
    )

# Include feedback, suggestions, UI config, and admin endpoints
app.include_router(feedback_router)

# Admin page route (X-Robots-Tag: noindex)
@app.get("/admin", include_in_schema=False)
def admin_page():
    admin_file = config.BASE_DIR / "ui" / "admin.html"
    if not admin_file.exists():
        raise HTTPException(status_code=404, detail="Admin interface not found.")
    return FileResponse(str(admin_file), media_type="text/html", headers={"X-Robots-Tag": "noindex"})

# Static UI files mounted at / (must be after API routes)
ui_dir = config.BASE_DIR / "ui"
if ui_dir.exists():
    app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")
