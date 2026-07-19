from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


def _load_dotenv() -> None:
    """Load Backend/.env into the process environment before any dependency reads it.

    Uses setdefault so explicitly-exported real env vars always win over the file.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError, HTTPException

from app.core.envelope import error_response
from app.core.logging import setup_logging, set_request_id, reset_request_id, get_request_id, get_logger
from app.exceptions import BE2Error

# Import Phase A Routers
from app.api.admin import legal as admin_legal
from app.api.admin import jobs as admin_jobs
from app.api.admin import qa as admin_qa
from app.api.citizen import legal as citizen_legal
from app.api.citizen import qa as citizen_qa

# Import Phase B Routers
from app.api.admin import social as admin_social
from app.api.admin import alerts as admin_alerts
from app.api.admin import graph as admin_graph
from app.api.admin import review as admin_review
from app.api.admin import dashboard as admin_dashboard

# Import Phase C Routers
from app.api.admin import briefs as admin_briefs
from app.api.admin import suggestions as admin_suggestions
from app.api.citizen import news as citizen_news

# Auth (login backed by Postgres users table)
from app.api import auth as auth_router

setup_logging("INFO")
logger = get_logger("app.main")

app = FastAPI(
    title="Legal Knowledge Graph & Social Intelligence API (BE3)",
    description="Backend Core Gateway serving Admin Dashboard & Citizen Portal with RAG QA, Versioning, and Social Intel.",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS configuration.
# Default: allow any http(s) origin (Railway custom domains, tunnels, local FE).
# Set CORS_ALLOW_ALL=false to restrict to localhost + CORS_EXTRA_ORIGINS only.
_cors_allow_all = os.getenv("CORS_ALLOW_ALL", "true").lower() in {"1", "true", "yes"}
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra = os.getenv("CORS_EXTRA_ORIGINS", "")
if _extra.strip():
    _cors_origins.extend(o.strip() for o in _extra.split(",") if o.strip())

if _cors_allow_all:
    # Reflect any Origin (cannot use "*" with allow_credentials=True).
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Any) -> Any:
    """Middleware for injecting Request ID, measuring latency, and logging."""
    start_time = time.perf_counter()
    req_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
    token = set_request_id(req_id)
    current_req_id = get_request_id()

    try:
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = current_req_id
        response.headers["X-Latency-Ms"] = str(round(latency_ms, 2))
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(BE2Error)
async def be2_error_handler(request: Request, exc: BE2Error) -> JSONResponse:
    req_id = get_request_id()
    logger.warning(f"BE2Error [{exc.code}]: {exc.message}")

    # Mặc định là 400 Bad Request
    status_code = status.HTTP_400_BAD_REQUEST

    # Map các loại lỗi cụ thể sang HTTP status thích hợp
    if exc.code in {"validation_error", "contract_missing"}:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif exc.code == "security_config_error":
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    elif getattr(exc, "retryable", False) or exc.code in {
        "external_service_error",
        "brief_persistence_error",
        "suggestion_persistence_error",
        "queue_unavailable",
        "job_enqueue_error",
        "graph_paths_unavailable"
    }:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == "brief_conflict":
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == "publish_gate_error":
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    body = error_response(
        message=exc.message,
        request_id=req_id,
        details=exc.details,
        code=exc.code,
    )
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    req_id = get_request_id()
    body = error_response(
        message=str(exc.detail),
        request_id=req_id,
        code=f"http_{exc.status_code}",
    )
    return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    req_id = get_request_id()
    errors = exc.errors()
    # Surface first error so FE toast is actionable (not only "Request validation failed").
    first = errors[0] if errors else {}
    loc = ".".join(str(x) for x in (first.get("loc") or ()) if x != "body")
    msg = str(first.get("msg") or "Request validation failed")
    summary = f"{loc}: {msg}" if loc else msg
    details = {"errors": errors}
    body = error_response(
        message=summary,
        request_id=req_id,
        details=details,
        code="validation_error",
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = get_request_id()
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    body = error_response(
        message="Internal server error occurred",
        request_id=req_id,
        code="internal_error",
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body)


@app.get("/health", summary="Health check endpoint")
@app.get("/healthz", summary="Health check alias")
async def health_check() -> dict[str, Any]:
    """Liveness only — must not touch DB/Neo4j/Redis (Railway probes this)."""
    boot_err: str | None = None
    try:
        from app.core.security import security_boot_error

        boot_err = security_boot_error()
    except Exception as exc:  # noqa: BLE001
        boot_err = str(exc)
    return {
        "status": "ok",
        "service": "be3-gateway",
        "version": "1.0.0",
        "security_ok": boot_err is None,
        "security_warning": boot_err,
    }


# Register Phase A Routers
app.include_router(admin_legal.router, prefix="/admin")
app.include_router(admin_jobs.router, prefix="/admin")
app.include_router(admin_qa.router, prefix="/admin")
app.include_router(citizen_legal.router, prefix="/citizen")
app.include_router(citizen_qa.router, prefix="/citizen")

# Register Phase B Routers
app.include_router(admin_social.router, prefix="/admin")
app.include_router(admin_alerts.router, prefix="/admin")
app.include_router(admin_graph.router, prefix="/admin")
app.include_router(admin_review.router, prefix="/admin")
app.include_router(admin_dashboard.router, prefix="/admin")

# Register Phase C Routers
app.include_router(admin_briefs.router, prefix="/admin")
app.include_router(admin_suggestions.router, prefix="/admin")
app.include_router(citizen_news.router, prefix="/citizen")

# Auth router (no prefix -> POST /auth/login, GET /auth/me)
app.include_router(auth_router.router)
