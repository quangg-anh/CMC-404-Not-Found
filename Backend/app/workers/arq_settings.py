from __future__ import annotations

from arq.connections import RedisSettings

from app.config import BE2Config, get_config
from app.workers.content_jobs import brief_generate, suggest_generate
from app.workers.social_jobs import alert_fanout, social_claim, social_ingest, social_link, social_topic

BE2_WORKER_FUNCTIONS = [
    social_ingest,
    social_topic,
    social_link,
    social_claim,
    alert_fanout,
    brief_generate,
    suggest_generate,
]

def redis_settings(config: BE2Config | None = None) -> RedisSettings:
    cfg = config or get_config()
    return RedisSettings.from_dsn(cfg.redis_url)

class WorkerSettings:
    """Arq worker settings for BE2-owned jobs only."""

    functions = BE2_WORKER_FUNCTIONS
    redis_settings = redis_settings()
    max_tries = 3
    job_timeout = get_config().default_job_timeout_s