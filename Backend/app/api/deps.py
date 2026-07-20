from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse
import httpx
from fastapi import Depends, HTTPException, status
from app.config import BE2Config, get_config
from app.core.security import Role, UserToken, get_current_user, require_admin, require_roles
from app.adapters.neo4j_social import Neo4jSocialRepository
from app.adapters.neo4j_temporal import Neo4jTemporalRepository
from app.adapters.postgres_content import PostgresContentRepository
from app.adapters.qdrant_vector import QdrantVectorClient
from app.adapters.minio_storage import MinioStorage
from app.intelligence.llm_router import LLMRouter
from app.intelligence.embedder import Embedder
from app.services.temporal_law_service import TemporalLawService

logger = logging.getLogger(__name__)

# Global connections / pools for real services
_db_pool: Any | None = None
_neo4j_driver: Any | None = None
_qdrant_client: Any | None = None
_http_client: httpx.AsyncClient | None = None
_llm_router: LLMRouter | None = None
_embedder: Embedder | None = None
_minio_storage: MinioStorage | None = None
_redis_client: Any | None = None
_redis_failed = False


async def get_redis() -> Any | None:
    """Optional Redis for QA cache. Returns None if unavailable (never raises)."""
    global _redis_client, _redis_failed
    if _redis_failed:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as redis_async

        url = os.getenv("REDIS_URL") or os.getenv("BE2_REDIS_URL") or "redis://localhost:6379/0"
        client = redis_async.from_url(url, encoding="utf-8", decode_responses=True)
        await client.ping()
        _redis_client = client
        return _redis_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable for QA cache: %s", exc)
        _redis_failed = True
        return None


def normalize_service_url(raw: str | None, *, default: str = "http://localhost:8002") -> str:
    """Ensure BE2 / internal service URLs have an http(s) scheme.

    Railway users often set ``BE2_INTELLIGENCE_URL=${{be2.RAILWAY_PRIVATE_DOMAIN}}:8002``
    without ``http://``, which makes httpx raise: Request URL is missing protocol.
    """
    value = (raw or "").strip().strip('"').strip("'")
    if not value:
        return default.rstrip("/")
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")


class RealLLMClient:
    """Real HTTP Client communicating with BE2 Intelligence API / Celery Worker Bridge."""

    def __init__(self, base_url: str = "http://localhost:8002", client: httpx.AsyncClient | None = None) -> None:
        self.base_url = normalize_service_url(base_url)
        self.client = client or httpx.AsyncClient(timeout=30.0)

    async def complete(self, *, route: str, model: str, task: str, prompt: str, timeout_s: float) -> dict[str, Any]:
        url = f"{self.base_url}/{route.lstrip('/')}"
        payload = {
            "model": model,
            "task": task,
            "prompt": prompt,
            "timeout_s": timeout_s,
        }
        try:
            res = await self.client.post(url, json=payload, timeout=timeout_s)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Lỗi khi kết nối tới BE2 Intelligence API ({route}): {str(e)}",
            )

    async def health(self) -> dict[str, Any]:
        try:
            res = await self.client.get(f"{self.base_url}/health", timeout=5.0)
            return res.json() if res.status_code == 200 else {"ok": False, "status": res.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}


async def get_db_pool() -> Any:
    """Retrieve or initialize asyncpg connection pool to Postgres."""
    global _db_pool
    if _db_pool is None:
        pg_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/studyhub")
        try:
            import asyncpg
            import ssl as _ssl

            ssl_mode = (os.getenv("DATABASE_SSL") or "").strip().lower()
            kwargs: dict[str, Any] = {"min_size": 2, "max_size": 10}
            if ssl_mode in {"1", "true", "yes", "require", "prefer"}:
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                kwargs["ssl"] = ctx
            _db_pool = await asyncpg.create_pool(pg_url, **kwargs)
        except Exception:
            logger.exception("PostgreSQL pool initialization failed")
    return _db_pool


async def get_neo4j_driver() -> Any:
    """Retrieve or initialize AsyncGraphDatabase driver to Neo4j."""
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        try:
            from neo4j import AsyncGraphDatabase
            _neo4j_driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        except Exception as exc:
            logger.warning(
                "Neo4j driver unavailable at %s — legal graph writes/reads will be skipped: %s",
                uri, exc,
            )
    return _neo4j_driver


async def get_qdrant_client() -> QdrantVectorClient:
    """Retrieve or initialize AsyncQdrantClient wrapper to Qdrant vector store."""
    global _qdrant_client
    if _qdrant_client is None:
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        try:
            from qdrant_client import AsyncQdrantClient
            raw_client = AsyncQdrantClient(url=url, timeout=10.0)
            _qdrant_client = QdrantVectorClient(raw_client)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Không thể kết nối vector store Qdrant: {str(e)}",
            )
    return _qdrant_client


async def get_llm_router(config: BE2Config = Depends(get_config)) -> LLMRouter:
    """Retrieve LLMRouter connected to real BE2 endpoints."""
    global _llm_router
    if _llm_router is None:
        be2_url = normalize_service_url(os.getenv("BE2_INTELLIGENCE_URL"), default="http://localhost:8002")
        _llm_router = LLMRouter(config=config, client=RealLLMClient(base_url=be2_url))
    return _llm_router


async def get_embedder(config: BE2Config = Depends(get_config)) -> Embedder | None:
    """Retrieve the OpenAI-compatible embedder (FastAPI Depends(get_config)).

    Scripts: ``await get_embedder(get_config())`` — pass config explicitly so FastAPI
    dependency injection is not required.
    """
    global _embedder
    if _embedder is None:
        try:
            _embedder = Embedder(config=config)
        except Exception as exc:
            logger.warning("Embedder init failed — Qdrant vector indexing will be skipped: %s", exc)
            return None
    return _embedder


async def get_minio() -> MinioStorage | None:
    """Retrieve or initialize the MinIO storage client for raw legal files.

    Returns None (instead of raising) if MinIO/the client lib is unavailable, so text/URL-based
    ingest keeps working even when object storage is down. The upload endpoint checks for None.
    """
    global _minio_storage
    if _minio_storage is None:
        endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
        access = os.getenv("MINIO_ROOT_USER", "minio_admin")
        secret = os.getenv("MINIO_ROOT_PASSWORD", "change_me_minio")
        bucket = os.getenv("MINIO_BUCKET_LEGAL", "legal-raw")
        try:
            from minio import Minio

            parsed = urlparse(endpoint)
            host = parsed.netloc or parsed.path
            secure = parsed.scheme == "https"
            client = Minio(host, access_key=access, secret_key=secret, secure=secure)
            _minio_storage = MinioStorage(client, bucket)
        except Exception:  # noqa: BLE001 - object storage is optional for text ingest
            return None
    return _minio_storage


async def get_postgres_repo(pool: Any = Depends(get_db_pool)) -> PostgresContentRepository:
    if pool is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Kết nối cơ sở dữ liệu Postgres chưa sẵn sàng.")
    return PostgresContentRepository(pool=pool)


async def get_neo4j_repo(driver: Any = Depends(get_neo4j_driver)) -> Neo4jSocialRepository:
    if driver is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Kết nối Neo4j Graph Database chưa sẵn sàng.")
    return Neo4jSocialRepository(driver=driver)

async def get_temporal_law_service(
    driver: Any = Depends(get_neo4j_driver),
) -> TemporalLawService:
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j temporal graph is not available.",
        )
    return TemporalLawService(Neo4jTemporalRepository(driver))


# Re-export security dependencies for convenience
__all__ = [
    "Role",
    "UserToken",
    "get_current_user",
    "require_admin",
    "require_roles",
    "get_db_pool",
    "get_neo4j_driver",
    "get_qdrant_client",
    "get_llm_router",
    "get_embedder",
    "get_minio",
    "get_postgres_repo",
    "get_neo4j_repo",
    "get_temporal_law_service",
    "get_redis",
]
