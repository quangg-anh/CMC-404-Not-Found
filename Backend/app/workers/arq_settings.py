from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings

from app.config import BE2Config, get_config
from app.workers.content_jobs import brief_generate, daily_news_briefs, suggest_generate
from app.workers.legal_jobs import legal_ingest, legal_extract
from app.workers.social_jobs import alert_fanout, daily_social_monitor, social_claim, social_ingest, social_link, social_topic

BE2_WORKER_FUNCTIONS = [
    social_ingest,
    social_topic,
    social_link,
    social_claim,
    alert_fanout,
    daily_social_monitor,
    brief_generate,
    suggest_generate,
    daily_news_briefs,
]

# Legal ingest is BE1/BE3 territory (kept out of the scope-limited BE2 worker).
LEGAL_WORKER_FUNCTIONS = [legal_ingest, legal_extract]

def redis_settings(config: BE2Config | None = None) -> RedisSettings:
    cfg = config or get_config()
    return RedisSettings.from_dsn(cfg.redis_url)


async def worker_startup(ctx: dict) -> None:
    """Populate the arq job context with real service instances (fixes KeyError on first job)."""
    from app.api.deps import get_db_pool, get_neo4j_driver, get_qdrant_client, get_minio, RealLLMClient
    from app.adapters.neo4j_social import Neo4jSocialRepository
    from app.adapters.neo4j_legal import Neo4jLegalRepository
    from app.adapters.postgres_content import PostgresContentRepository
    from app.intelligence.embedder import Embedder
    from app.intelligence.llm_router import LLMRouter
    from app.pipelines.social.ingest import SocialIngestService
    from app.pipelines.social.topic_classify import TopicClassifier
    from app.pipelines.social.entity_link import EntityLinker
    from app.pipelines.social.claim_check import ClaimChecker
    from app.pipelines.social.alert_signal import AlertSignalService
    from app.pipelines.social.collectors import build_default_monitor
    from app.pipelines.content.brief_generate import BriefGenerateService
    from app.pipelines.content.suggest_generate import SuggestGenerateService
    from app.services.phapluat_news_service import PhapLuatNewsService

    cfg = get_config()
    pool = await get_db_pool()
    driver = await get_neo4j_driver()
    qdrant = await get_qdrant_client()
    minio = await get_minio()
    embedder = Embedder(cfg)
    router = LLMRouter(config=cfg, client=RealLLMClient(base_url=os.getenv("BE2_INTELLIGENCE_URL", "http://localhost:8002")))

    social_repo = Neo4jSocialRepository(driver) if driver else None
    legal_repo = Neo4jLegalRepository(driver) if driver else None
    content_repo = PostgresContentRepository(pool) if pool else None

    ctx["config"] = cfg
    ctx["neo4j_driver"] = driver
    ctx["db_pool"] = pool
    ctx["qdrant"] = qdrant
    ctx["minio"] = minio
    ctx["embedder"] = embedder
    ctx["llm_router"] = router
    ctx["legal_repo"] = legal_repo
    ctx["social_repo"] = social_repo
    ctx["social_ingest_service"] = SocialIngestService(social_repo, cfg)
    ctx["topic_classifier"] = TopicClassifier(qdrant, embedder, cfg)
    ctx["entity_linker"] = EntityLinker(qdrant, social_repo, embedder, None, cfg)
    ctx["claim_checker"] = ClaimChecker(router, None)
    ctx["alert_signal_service"] = AlertSignalService(social_repo, cfg)
    ctx["social_daily_monitor"] = build_default_monitor(cfg)
    ctx["brief_generate_service"] = BriefGenerateService(legal_repo, content_repo, router)
    ctx["suggest_generate_service"] = SuggestGenerateService(legal_repo, content_repo, router)
    ctx["phapluat_news_service"] = PhapLuatNewsService(pool)

def cron_jobs(config: BE2Config | None = None) -> list:
    cfg = config or get_config()
    jobs = []
    if cfg.social_monitor_enabled:
        jobs.append(cron(daily_social_monitor, hour=cfg.social_monitor_cron_hour, minute=cfg.social_monitor_cron_minute, name="daily_social_monitor"))
    if cfg.news_brief_enabled:
        jobs.append(cron(daily_news_briefs, hour=cfg.news_brief_cron_hour, minute=cfg.news_brief_cron_minute, name="daily_news_briefs"))
    return jobs


async def worker_shutdown(ctx: dict) -> None:
    driver = getattr(ctx.get("social_repo"), "driver", None)
    if driver is not None and hasattr(driver, "close"):
        try:
            await driver.close()
        except Exception:
            pass


class WorkerSettings:
    """Arq worker settings for BE2-owned jobs only."""

    functions = BE2_WORKER_FUNCTIONS
    redis_settings = redis_settings()
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    cron_jobs = cron_jobs()
    max_tries = 3
    job_timeout = get_config().default_job_timeout_s


class LegalWorkerSettings:
    """Arq worker settings for BE3 legal ingest jobs (run: arq app.workers.arq_settings.LegalWorkerSettings)."""

    functions = LEGAL_WORKER_FUNCTIONS
    redis_settings = redis_settings()
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    max_tries = 3
    job_timeout = get_config().default_job_timeout_s