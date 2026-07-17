from __future__ import annotations

import os
from functools import lru_cache
from pydantic import BaseModel, Field, HttpUrl


class BE2Config(BaseModel):
    embedding_provider: str = Field(default="local", pattern="^(local|tei)$")
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_timeout_s: float = Field(default=30.0, gt=0)
    embedding_dimension: int | None = None
    tei_url: HttpUrl | None = None

    llm_gateway_url: HttpUrl | None = None
    llm_local_model: str = "gemma-local"
    llm_large_model: str = "large-schema-locked"
    llm_local_timeout_s: float = Field(default=20.0, gt=0)
    llm_large_timeout_s: float = Field(default=60.0, gt=0)
    llm_retry_count: int = Field(default=1, ge=0, le=3)

    topic_threshold: float = Field(default=0.55, ge=0, le=1)
    link_threshold: float = Field(default=0.70, ge=0, le=1)
    nli_confidence_threshold: float = Field(default=0.70, ge=0, le=1)
    alert_volume_threshold: int = Field(default=3, ge=1)
    alert_time_window_s: int = Field(default=3600, ge=1)
    alert_dedupe_window_s: int = Field(default=86400, ge=1)
    alert_cooldown_s: int = Field(default=3600, ge=0)

    author_hmac_secret: str | None = None
    default_job_timeout_s: int = Field(default=300, ge=1)
    redis_url: str = "redis://localhost:6379/0"


@lru_cache(maxsize=1)
def get_config() -> BE2Config:
    return BE2Config(
        embedding_provider=os.getenv("BE2_EMBEDDING_PROVIDER", "local"),
        embedding_model=os.getenv("BE2_EMBEDDING_MODEL", "BAAI/bge-m3"),
        embedding_batch_size=int(os.getenv("BE2_EMBEDDING_BATCH_SIZE", "32")),
        embedding_timeout_s=float(os.getenv("BE2_EMBEDDING_TIMEOUT_S", "30")),
        embedding_dimension=int(os.getenv("BE2_EMBEDDING_DIMENSION")) if os.getenv("BE2_EMBEDDING_DIMENSION") else None,
        tei_url=os.getenv("BE2_TEI_URL") or None,
        llm_gateway_url=os.getenv("BE2_LLM_GATEWAY_URL") or None,
        llm_local_model=os.getenv("BE2_LLM_LOCAL_MODEL", "gemma-local"),
        llm_large_model=os.getenv("BE2_LLM_LARGE_MODEL", "large-schema-locked"),
        llm_local_timeout_s=float(os.getenv("BE2_LLM_LOCAL_TIMEOUT_S", "20")),
        llm_large_timeout_s=float(os.getenv("BE2_LLM_LARGE_TIMEOUT_S", "60")),
        llm_retry_count=int(os.getenv("BE2_LLM_RETRY_COUNT", "1")),
        topic_threshold=float(os.getenv("BE2_TOPIC_THRESHOLD", "0.55")),
        link_threshold=float(os.getenv("BE2_LINK_THRESHOLD", "0.70")),
        nli_confidence_threshold=float(os.getenv("BE2_NLI_CONFIDENCE_THRESHOLD", "0.70")),
        alert_volume_threshold=int(os.getenv("BE2_ALERT_VOLUME_THRESHOLD", "3")),
        alert_time_window_s=int(os.getenv("BE2_ALERT_TIME_WINDOW_S", "3600")),
        alert_dedupe_window_s=int(os.getenv("BE2_ALERT_DEDUPE_WINDOW_S", "86400")),
        alert_cooldown_s=int(os.getenv("BE2_ALERT_COOLDOWN_S", "3600")),
        author_hmac_secret=os.getenv("BE2_AUTHOR_HMAC_SECRET"),
        default_job_timeout_s=int(os.getenv("BE2_DEFAULT_JOB_TIMEOUT_S", "300")),
        redis_url=os.getenv("BE2_REDIS_URL", "redis://localhost:6379/0"),
    )
