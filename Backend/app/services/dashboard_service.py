from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DashboardService:
    """Real-time operational metrics for the Admin Command Center."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver

    async def get_summary(self) -> dict[str, Any]:
        high_alerts = 0
        total_alerts = 0
        active_jobs = 0
        failed_jobs = 0
        needs_review = 0
        pending_briefs = 0
        ready_suggestions = 0
        legal_docs_count = 0
        social_posts_count = 0
        topic_count = 0
        sync_status = "unknown"

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    high_alerts = int(
                        await conn.fetchval(
                            """
                            SELECT COUNT(*) FROM alerts
                            WHERE severity = 'high'
                              AND status::text IN ('open', 'triaged')
                            """
                        )
                        or 0
                    )
                    total_alerts = int(
                        await conn.fetchval(
                            """
                            SELECT COUNT(*) FROM alerts
                            WHERE status::text IN ('open', 'triaged')
                            """
                        )
                        or 0
                    )

                    jrows = await conn.fetch("SELECT status FROM jobs")
                    active_jobs = sum(1 for x in jrows if x["status"] in {"running", "queued"})
                    failed_jobs = sum(1 for x in jrows if x["status"] == "failed")
                    needs_review = sum(1 for x in jrows if x["status"] == "needs_review")

                    pending_briefs = int(
                        await conn.fetchval(
                            """
                            SELECT COUNT(*) FROM briefs
                            WHERE status::text IN ('draft', 'review')
                            """
                        )
                        or 0
                    )
                    ready_suggestions = int(
                        await conn.fetchval(
                            """
                            SELECT COUNT(*) FROM suggestions
                            WHERE status::text = 'ready'
                            """
                        )
                        or 0
                    )
            except Exception:
                logger.warning("Failed to fetch Postgres dashboard metrics", exc_info=True)

        if self.driver and hasattr(self.driver, "session"):
            try:
                async with self.driver.session() as session:
                    res_vb = await session.run("MATCH (v:VanBanPhapLuat) RETURN count(v) AS cnt")
                    rec_vb = await res_vb.single()
                    legal_docs_count = int(rec_vb["cnt"]) if rec_vb else 0

                    res_post = await session.run("MATCH (b:BaiDang) RETURN count(b) AS cnt")
                    rec_post = await res_post.single()
                    social_posts_count = int(rec_post["cnt"]) if rec_post else 0

                    res_topic = await session.run("MATCH (c:ChuDe) RETURN count(c) AS cnt")
                    rec_topic = await res_topic.single()
                    topic_count = int(rec_topic["cnt"]) if rec_topic else 0

                    sync_status = "in_sync"
            except Exception:
                sync_status = "degraded"
                logger.warning("Failed to fetch Neo4j dashboard metrics", exc_info=True)

        return {
            "alerts": {
                "high_severity_active": high_alerts,
                "total_monitored": total_alerts,
            },
            "pipeline_jobs": {
                "running": active_jobs,
                "failed": failed_jobs,
                "needs_review": needs_review,
                "health_status": "healthy" if failed_jobs == 0 else "degraded",
            },
            "knowledge_graph": {
                "legal_documents_count": legal_docs_count,
                "social_posts_monitored": social_posts_count,
                "topic_count": topic_count,
                "sync_status": sync_status,
            },
            "content_briefs": {
                "pending_review": pending_briefs,
                "ready_suggestions": ready_suggestions,
            },
        }
