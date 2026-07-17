from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.neo4j_social import Neo4jSocialRepository
from app.config import get_config
from app.intelligence.embedder import Embedder
from app.pipelines.social.alert_signal import AlertSignalService
from app.pipelines.social.collectors import build_default_monitor
from app.pipelines.social.entity_link import EntityLinker
from app.pipelines.social.ingest import SocialIngestService
from app.pipelines.social.topic_classify import TopicClassifier
from app.workers.social_jobs import daily_social_monitor


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


async def _get_neo4j_driver() -> Any | None:
    from app.api.deps import get_neo4j_driver

    return await get_neo4j_driver()

async def _get_qdrant_client() -> Any | None:
    from app.api.deps import get_qdrant_client

    return await get_qdrant_client()


async def main() -> int:
    parser = argparse.ArgumentParser(description="BE2 daily social monitor smoke runner")
    parser.add_argument("--topics", help="Comma-separated topics. Defaults to BE2_SOCIAL_MONITOR_TOPICS.")
    parser.add_argument("--limit", type=int, default=None, help="Limit per topic. Defaults to config.")
    parser.add_argument("--ingest", action="store_true", help="Write collected posts into Neo4j BaiDang.")
    parser.add_argument("--verify", action="store_true", help="After ingest, read first stored BaiDang from Neo4j.")
    parser.add_argument("--no-chain", action="store_true", help="Skip topic/link/alert chain after ingest.")
    args = parser.parse_args()

    cfg = get_config()
    topics = _csv(args.topics) or cfg.social_monitor_topics
    if not topics:
        print(json.dumps({"status": "failed", "error": "No topics configured."}, ensure_ascii=False))
        return 2

    driver = await _get_neo4j_driver() if args.ingest or args.verify else None
    if args.ingest and driver is None:
        print(json.dumps({"status": "failed", "error": "Neo4j unavailable; rerun without --ingest for dry-run collect."}, ensure_ascii=False))
        return 2

    repo = Neo4jSocialRepository(driver) if driver else None
    qdrant = await _get_qdrant_client() if args.ingest and not args.no_chain else None
    embedder = Embedder(cfg) if qdrant else None
    ctx = {
        "config": cfg,
        "social_daily_monitor": build_default_monitor(cfg),
        "social_ingest_service": SocialIngestService(repo, cfg) if repo else None,
        "social_repo": repo,
        "topic_classifier": TopicClassifier(qdrant, embedder, cfg) if qdrant else None,
        "entity_linker": EntityLinker(qdrant, repo, embedder, None, cfg) if qdrant and repo else None,
        "alert_signal_service": AlertSignalService(repo, cfg) if repo else None,
    }
    envelope = {
        "job_id": "manual-daily-social-smoke",
        "correlation_id": "manual-daily-social-smoke",
        "payload": {"topics": topics, "limit_per_topic": args.limit or cfg.social_monitor_limit_per_topic, "chain": not args.no_chain},
        "dry_run": not args.ingest,
    }
    result = await daily_social_monitor(ctx, envelope)

    verified: dict[str, Any] | None = None
    ingested = ((result.get("data") or {}).get("ingested") or []) if isinstance(result, dict) else []
    if args.verify and repo and ingested:
        first = ingested[0]
        bai_dang_id = f"{first.get('platform')}:{first.get('external_id')}"
        post = await repo.get_post(bai_dang_id)
        verified = {"bai_dang_id": bai_dang_id, "found": post is not None}

    print(json.dumps({"worker_result": result, "verified": verified}, ensure_ascii=False, default=str, indent=2))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
