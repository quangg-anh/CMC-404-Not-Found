from __future__ import annotations

from typing import Any

import pytest

from app.adapters.neo4j_social import Neo4jSocialRepository
from app.pipelines.social.ingest import normalize_social_payload


class _Cursor:
    def __init__(self, *, single_record: dict[str, Any] | None = None, records: list[dict[str, Any]] | None = None):
        self.single_record = single_record
        self.records = records or []
        self.consumed = False

    async def single(self):
        return self.single_record

    async def consume(self):
        self.consumed = True

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for record in self.records:
            yield record


class _Session:
    def __init__(self, cursor: _Cursor):
        self.cursor = cursor
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def run(self, query: str, **params: Any):
        self.calls.append((query, params))
        return self.cursor


class _Driver:
    def __init__(self, cursor: _Cursor):
        self._session = _Session(cursor)

    def session(self):
        return self._session


@pytest.mark.asyncio
async def test_find_recent_alert_uses_dedupe_key_and_cooldown():
    driver = _Driver(_Cursor(single_record={"a": {"dedupe_key": "tax:k1", "status": "open"}}))
    repo = Neo4jSocialRepository(driver)

    alert = await repo.find_recent_alert("tax:k1", 90)

    query, params = driver._session.calls[0]
    assert "dedupe_key: $key" in query
    assert "duration({seconds: $cooldown_s})" in query
    assert params == {"key": "tax:k1", "cooldown_s": 90}
    assert alert == {"dedupe_key": "tax:k1", "status": "open"}


@pytest.mark.asyncio
async def test_recent_alert_signals_include_source_and_legal_provenance():
    record = {
        "bai_dang_id": "news:article-1",
        "ykien_id": "claim-1",
        "claim_text": "Claim text",
        "evidence_span": "Claim text",
        "post_content": "Claim text in article",
        "post_url": "https://news.example/article-1",
        "chu_de": "tax",
        "khoan_id": "k1",
        "label": "mau_thuan",
        "score": 0.94,
        "source_type": "news",
        "provider": "news.example",
        "legal_text": "Canonical legal text",
        "van_ban_id": "doc-1",
    }
    driver = _Driver(_Cursor(records=[record]))
    repo = Neo4jSocialRepository(driver)

    signals = await repo.get_recent_alert_signals(
        chu_de="tax",
        khoan_ids=["k1"],
        window_s=3600,
        min_score=0.7,
    )

    assert signals[0]["ykien_id"] == "claim-1"
    assert signals[0]["source_type"] == "news"
    assert signals[0]["legal_evidence"] == {
        "khoan_id": "k1",
        "van_ban": "doc-1",
        "quote": "Canonical legal text",
    }


@pytest.mark.asyncio
async def test_upsert_content_adds_generic_label_and_stable_hash():
    driver = _Driver(_Cursor(single_record={"bai_dang_id": "news:article-1"}))
    repo = Neo4jSocialRepository(driver)
    post = normalize_social_payload({
        "platform": "news",
        "external_id": "article-1",
        "content": "A legal news article",
        "url": "https://news.example/article-1",
        "source_type": "news",
        "provider": "news.example",
    })

    result = await repo.upsert_post(post)

    query, params = driver._session.calls[0]
    assert "BaiDang:NoiDungNguon" in query
    assert params["source_type"] == "news"
    assert params["provider"] == "news.example"
    assert len(params["content_hash"]) == 64
    assert result == "news:article-1"


@pytest.mark.asyncio
async def test_get_post_restores_platform_neutral_source_metadata():
    published_at = "2026-07-19T08:00:00+07:00"
    ingested_at = "2026-07-19T08:05:00+07:00"
    driver = _Driver(_Cursor(single_record={"b": {
        "platform": "news",
        "external_id": "article-1",
        "noi_dung": "A legal news article",
        "url": "https://news.example/article-1",
        "thoi_gian": published_at,
        "ingested_at": ingested_at,
        "source_type": "news",
        "provider": "news.example",
        "source_metadata_json": '{"source_topic": "tax"}',
    }}))
    post = await Neo4jSocialRepository(driver).get_post("news:article-1")
    assert post is not None
    assert post.source_metadata == {"source_topic": "tax", "source_type": "news", "provider": "news.example"}
