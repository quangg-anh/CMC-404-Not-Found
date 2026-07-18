from __future__ import annotations

import pytest

from app.services.dashboard_service import DashboardService


class _FakeConn:
    def __init__(self, counts: dict[str, int], job_statuses: list[str] | None = None) -> None:
        self.counts = counts
        self.job_statuses = job_statuses or []
        self.queries: list[str] = []

    async def fetchval(self, query: str, *args):  # noqa: ANN001
        self.queries.append(query)
        q = " ".join(query.split()).lower()
        if "from alerts" in q and "severity = 'high'" in q:
            return self.counts.get("high_alerts", 0)
        if "from alerts" in q:
            return self.counts.get("total_alerts", 0)
        if "from briefs" in q:
            return self.counts.get("briefs", 0)
        if "from suggestions" in q:
            return self.counts.get("suggestions", 0)
        return 0

    async def fetch(self, query: str, *args):  # noqa: ANN001
        self.queries.append(query)
        if "from jobs" in query.lower():
            return [{"status": s} for s in self.job_statuses]
        return []


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *args):
                return False

        return _Ctx()


class _FakeResult:
    def __init__(self, cnt: int) -> None:
        self.cnt = cnt

    async def single(self):
        return {"cnt": self.cnt}


class _FakeSession:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.calls = 0

    async def run(self, query: str, **kwargs):  # noqa: ANN003
        self.calls += 1
        q = query.lower()
        if "vanbanphapluat" in q:
            return _FakeResult(self.counts.get("vb", 0))
        if "baidang" in q:
            return _FakeResult(self.counts.get("posts", 0))
        if "chude" in q:
            return _FakeResult(self.counts.get("topics", 0))
        return _FakeResult(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeDriver:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts

    def session(self):
        return _FakeSession(self.counts)


@pytest.mark.asyncio
async def test_dashboard_summary_uses_real_counts_not_hardcoded_defaults():
    conn = _FakeConn(
        counts={"high_alerts": 1, "total_alerts": 4, "briefs": 3, "suggestions": 2},
        job_statuses=["running", "queued", "failed", "needs_review", "success"],
    )
    service = DashboardService(pool=_FakePool(conn), neo4j_driver=_FakeDriver({"vb": 12, "posts": 88, "topics": 7}))
    summary = await service.get_summary()

    assert summary["alerts"]["high_severity_active"] == 1
    assert summary["alerts"]["total_monitored"] == 4
    assert summary["pipeline_jobs"]["running"] == 2
    assert summary["pipeline_jobs"]["failed"] == 1
    assert summary["pipeline_jobs"]["needs_review"] == 1
    assert summary["pipeline_jobs"]["health_status"] == "degraded"
    assert summary["knowledge_graph"]["legal_documents_count"] == 12
    assert summary["knowledge_graph"]["social_posts_monitored"] == 88
    assert summary["knowledge_graph"]["topic_count"] == 7
    assert summary["knowledge_graph"]["sync_status"] == "in_sync"
    assert summary["content_briefs"]["pending_review"] == 3
    assert summary["content_briefs"]["ready_suggestions"] == 2


@pytest.mark.asyncio
async def test_dashboard_summary_zeros_when_backends_missing():
    summary = await DashboardService(pool=None, neo4j_driver=None).get_summary()
    assert summary["alerts"]["total_monitored"] == 0
    assert summary["knowledge_graph"]["legal_documents_count"] == 0
    assert summary["knowledge_graph"]["sync_status"] == "unknown"
    assert summary["content_briefs"]["pending_review"] == 0
