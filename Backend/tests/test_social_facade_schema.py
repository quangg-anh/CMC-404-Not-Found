from __future__ import annotations

import pytest

from app.services.social_facade import SocialAlertFacade


class _FailThenOkConn:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, query: str, *args):  # noqa: ANN001
        self.calls += 1
        if "signals" in query:
            raise Exception('column "signals" does not exist')
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "chu_de": "thue",
                "khoan_ids": [],
                "severity": "high",
                "volume": 3,
                "status": "open",
                "created_at": None,
            }
        ]

    async def fetchrow(self, query: str, *args):  # noqa: ANN001
        rows = await self.fetch(query, *args)
        return rows[0] if rows else None


class _Pool:
    def __init__(self, conn) -> None:
        self.conn = conn

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *args):
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_list_alerts_falls_back_without_signals_column():
    facade = SocialAlertFacade(pool=_Pool(_FailThenOkConn()), neo4j_driver=None)
    items = await facade.list_alerts()
    assert len(items) == 1
    assert items[0]["chu_de"] == "thue"
    assert items[0]["signals"] == []
    assert items[0]["provenance_status"] == "missing"


@pytest.mark.asyncio
async def test_list_topics_does_not_query_missing_postgres_table():
    class _BoomPool:
        def acquire(self):
            raise AssertionError("Postgres topics table must not be queried")

    facade = SocialAlertFacade(pool=_BoomPool(), neo4j_driver=None)
    assert await facade.list_topics() == []


@pytest.mark.asyncio
async def test_ingest_post_raises_when_insert_fails():
    """INSERT failure must not return a false-success queued status."""
    from app.exceptions import JobEnqueueError

    class _FailConn:
        async def execute(self, query: str, *args):  # noqa: ANN001
            raise RuntimeError("connection refused")

    facade = SocialAlertFacade(pool=_Pool(_FailConn()), neo4j_driver=None)
    with pytest.raises(JobEnqueueError) as ei:
        await facade.ingest_post(
            {"platform": "facebook", "url": "https://facebook.com/post/1", "noi_dung": "x"}
        )
    assert ei.value.code == "job_enqueue_error"


@pytest.mark.asyncio
async def test_ingest_post_raises_when_pool_missing():
    from app.exceptions import JobEnqueueError

    facade = SocialAlertFacade(pool=None, neo4j_driver=None)
    with pytest.raises(JobEnqueueError):
        await facade.ingest_post(
            {"platform": "facebook", "url": "https://facebook.com/post/1", "noi_dung": "x"}
        )
