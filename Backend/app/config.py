from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from pydantic import BaseModel, Field, HttpUrl
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

def _csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]

def _bool_env(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() not in {"0", "false", "no"}


class BE2Config(BaseModel):
    # ---- OpenAI-compatible AI stack (no Ollama / no local torch) ----
    # Shared host for chat + embeddings unless embedding_base_url is overridden.
    openai_base_url: HttpUrl | None = None
    openai_api_key: str | None = None

    # Embeddings: POST {embedding_base_url}/embeddings
    embedding_provider: str = Field(default="openai", pattern="^(openai)$")
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_timeout_s: float = Field(default=60.0, gt=0)
    embedding_dimension: int | None = 1536
    embedding_base_url: HttpUrl | None = None
    embedding_api_key: str | None = None

    # Two chat models (router picks by task complexity → /local vs /large on BE2 gateway)
    llm_gateway_url: HttpUrl | None = None
    llm_local_model: str = "gpt-4o-mini"
    llm_large_model: str = "gpt-4o"
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

    social_monitor_enabled: bool = True
    social_monitor_topics: list[str] = Field(default_factory=list)
    social_monitor_limit_per_topic: int = Field(default=10, ge=1, le=100)
    social_monitor_lookback_hours: int = Field(default=24, ge=1, le=168)
    social_monitor_cron_hour: int = Field(default=6, ge=0, le=23)
    social_monitor_cron_minute: int = Field(default=0, ge=0, le=59)
    facebook_access_token: str | None = None
    facebook_page_ids: list[str] = Field(default_factory=list)
    facebook_api_version: str = "v20.0"
    youtube_api_key: str | None = None
    youtube_api_keys: list[str] = Field(default_factory=list)
    youtube_channel_ids: list[str] = Field(default_factory=list)
    youtube_search_order: str = Field(default="relevance", pattern="^(date|rating|relevance|title|videoCount|viewCount)$")
    youtube_search_results_per_topic: int = Field(default=25, ge=1, le=50)
    youtube_region_code: str | None = "VN"
    youtube_relevance_language: str | None = "vi"
    youtube_filter_vietnamese: bool = True
    youtube_comments_enabled: bool = True
    youtube_comments_per_video: int = Field(default=20, ge=1, le=100)
    youtube_comments_per_topic: int = Field(default=50, ge=1, le=500)
    youtube_comments_as_posts: bool = True
    youtube_min_comment_length: int = Field(default=12, ge=1, le=500)
    youtube_skip_comment_urls: bool = True
    youtube_skip_videos_without_comments: bool = True
    youtube_require_topic_in_comments: bool = True
    forum_feed_urls: list[str] = Field(default_factory=list)

    news_brief_enabled: bool = False
    news_brief_cron_hour: int = Field(default=7, ge=0, le=23)
    news_brief_cron_minute: int = Field(default=0, ge=0, le=59)
    news_brief_limit_per_topic: int = Field(default=5, ge=1, le=20)


@lru_cache(maxsize=1)
def get_config() -> BE2Config:
    openai_base = (os.getenv("BE2_OPENAI_BASE_URL") or "").strip() or None
    openai_key = (os.getenv("BE2_OPENAI_API_KEY") or "").strip() or None

    # Embeddings default to the same OpenAI-compatible host/key as chat (no Ollama).
    emb_base = (os.getenv("BE2_EMBEDDING_BASE_URL") or openai_base or "").strip() or None
    emb_key = (os.getenv("BE2_EMBEDDING_API_KEY") or openai_key or "").strip() or None

    provider = (os.getenv("BE2_EMBEDDING_PROVIDER", "openai") or "openai").lower()
    if provider != "openai":
        provider = "openai"

    # Two LLM models. Legacy BE2_OPENAI_MODEL fills either slot if the specific var is missing.
    legacy_model = (os.getenv("BE2_OPENAI_MODEL") or "").strip() or None
    llm_local = (os.getenv("BE2_LLM_LOCAL_MODEL") or legacy_model or "gpt-4o-mini").strip()
    llm_large = (os.getenv("BE2_LLM_LARGE_MODEL") or legacy_model or "gpt-4o").strip()

    emb_dim_raw = os.getenv("BE2_EMBEDDING_DIMENSION")
    emb_dim = int(emb_dim_raw) if emb_dim_raw else 1536

    return BE2Config(
        openai_base_url=openai_base,
        openai_api_key=openai_key,
        embedding_provider=provider,
        embedding_model=os.getenv("BE2_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_batch_size=int(os.getenv("BE2_EMBEDDING_BATCH_SIZE", "32")),
        embedding_timeout_s=float(os.getenv("BE2_EMBEDDING_TIMEOUT_S", "60")),
        embedding_dimension=emb_dim,
        embedding_base_url=emb_base,
        embedding_api_key=emb_key,
        llm_gateway_url=os.getenv("BE2_LLM_GATEWAY_URL") or None,
        llm_local_model=llm_local,
        llm_large_model=llm_large,
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
        social_monitor_enabled=_bool_env("BE2_SOCIAL_MONITOR_ENABLED"),
        social_monitor_topics=_csv_env("BE2_SOCIAL_MONITOR_TOPICS"),
        social_monitor_limit_per_topic=int(os.getenv("BE2_SOCIAL_MONITOR_LIMIT_PER_TOPIC", "10")),
        social_monitor_lookback_hours=int(os.getenv("BE2_SOCIAL_MONITOR_LOOKBACK_HOURS", "24")),
        social_monitor_cron_hour=int(os.getenv("BE2_SOCIAL_MONITOR_CRON_HOUR", "6")),
        social_monitor_cron_minute=int(os.getenv("BE2_SOCIAL_MONITOR_CRON_MINUTE", "0")),
        facebook_access_token=os.getenv("BE2_FACEBOOK_ACCESS_TOKEN"),
        facebook_page_ids=_csv_env("BE2_FACEBOOK_PAGE_IDS"),
        facebook_api_version=os.getenv("BE2_FACEBOOK_API_VERSION", "v20.0"),
        youtube_api_key=os.getenv("BE2_YOUTUBE_API_KEY"),
        youtube_api_keys=_csv_env("BE2_YOUTUBE_API_KEYS"),
        youtube_channel_ids=_csv_env("BE2_YOUTUBE_CHANNEL_IDS"),
        youtube_search_order=os.getenv("BE2_YOUTUBE_SEARCH_ORDER", "relevance"),
        youtube_search_results_per_topic=int(os.getenv("BE2_YOUTUBE_SEARCH_RESULTS_PER_TOPIC", "25")),
        youtube_region_code=os.getenv("BE2_YOUTUBE_REGION_CODE", "VN") or None,
        youtube_relevance_language=os.getenv("BE2_YOUTUBE_RELEVANCE_LANGUAGE", "vi") or None,
        youtube_filter_vietnamese=_bool_env("BE2_YOUTUBE_FILTER_VIETNAMESE"),
        youtube_comments_enabled=_bool_env("BE2_YOUTUBE_COMMENTS_ENABLED"),
        youtube_comments_per_video=int(os.getenv("BE2_YOUTUBE_COMMENTS_PER_VIDEO", "20")),
        youtube_comments_per_topic=int(os.getenv("BE2_YOUTUBE_COMMENTS_PER_TOPIC", "50")),
        youtube_comments_as_posts=_bool_env("BE2_YOUTUBE_COMMENTS_AS_POSTS"),
        youtube_min_comment_length=int(os.getenv("BE2_YOUTUBE_MIN_COMMENT_LENGTH", "12")),
        youtube_skip_comment_urls=_bool_env("BE2_YOUTUBE_SKIP_COMMENT_URLS"),
        youtube_skip_videos_without_comments=_bool_env("BE2_YOUTUBE_SKIP_VIDEOS_WITHOUT_COMMENTS"),
        youtube_require_topic_in_comments=_bool_env("BE2_YOUTUBE_REQUIRE_TOPIC_IN_COMMENTS"),
        forum_feed_urls=_csv_env("BE2_FORUM_FEED_URLS"),
        news_brief_enabled=_bool_env("BE2_NEWS_BRIEF_ENABLED", "false"),
        news_brief_cron_hour=int(os.getenv("BE2_NEWS_BRIEF_CRON_HOUR", "7")),
        news_brief_cron_minute=int(os.getenv("BE2_NEWS_BRIEF_CRON_MINUTE", "0")),
        news_brief_limit_per_topic=int(os.getenv("BE2_NEWS_BRIEF_LIMIT_PER_TOPIC", "5")),
    )
