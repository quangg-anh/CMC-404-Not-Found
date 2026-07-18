from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_clarity_index_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Requires admin auth (router-level require_admin).
        res_forbidden = await client.get("/admin/graph/clarity-index")
        assert res_forbidden.status_code == 403

        headers = {"Authorization": "Bearer test-admin-truyen-thong"}
        res = await client.get("/admin/graph/clarity-index", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["total"] >= 1
        top = data["items"][0]
        assert top["khoan_id"] == "168/2024/ND-CP::D6.K6"
        assert 0.0 <= top["clarity_risk"] <= 1.0
        assert top["volume"] == 47


@pytest.mark.asyncio
async def test_admin_social_ingest_and_link_preview():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-admin-truyen-thong"}

        # Link preview
        res_preview = await client.post("/admin/social/link-preview", json={"url": "https://facebook.com/post/999"}, headers=headers)
        assert res_preview.status_code == 200
        assert res_preview.json()["data"]["domain"] == "facebook.com"

        # Ingest post
        payload = {"platform": "facebook", "url": "https://facebook.com/post/999", "noi_dung": "Chia sẻ sai lệch về nghị định"}
        res_ingest = await client.post("/admin/ingest/social", json=payload, headers=headers)
        assert res_ingest.status_code == 200
        assert "job_id" in res_ingest.json()["data"]

        # List topics & posts
        res_topics = await client.get("/admin/social/topics", headers=headers)
        assert res_topics.status_code == 200
        assert len(res_topics.json()["data"]["items"]) > 0


@pytest.mark.asyncio
async def test_admin_alerts_triage_creates_suggestion_draft():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-admin-truyen-thong"}

        # Get alert detail
        res_detail = await client.get("/admin/alerts/alert-meta-01", headers=headers)
        assert res_detail.status_code == 200
        data = res_detail.json()["data"]
        assert data["alert_id"] == "alert-meta-01"
        assert data["nli_label"] == "mau_thuan"

        # Triage alert -> create_suggest
        triage_payload = {"action": "create_suggest", "note": "Đính chính gấp mức phạt 500 triệu là sai"}
        res_triage = await client.patch("/admin/alerts/alert-meta-01", json=triage_payload, headers=headers)
        assert res_triage.status_code == 200
        triage_data = res_triage.json()["data"]
        assert triage_data["new_status"] == "triaged"
        # suggestions.id is a UUID (Data/schema/postgres/003); ensure a valid draft id was returned.
        assert triage_data["created_suggestion_id"]
        import uuid as _uuid

        _uuid.UUID(triage_data["created_suggestion_id"])  # raises if not a valid UUID


@pytest.mark.asyncio
async def test_admin_graph_neighborhood_query():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-admin-phap-che"}

        # Query neighborhood depth=2
        res = await client.get("/admin/graph/neighborhood?seed_id=13/2023/ND-CP::D4.K1&depth=2", headers=headers)
        assert res.status_code == 200
        body = res.json()["data"]
        assert body["seed_id"] == "13/2023/ND-CP::D4.K1"
        assert body["depth"] == 2
        assert isinstance(body["nodes"], list)
        assert isinstance(body["edges"], list)


@pytest.mark.asyncio
async def test_admin_review_queue_and_dashboard_summary():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-admin-ops"}

        # Review list
        res_review = await client.get("/admin/review", headers=headers)
        assert res_review.status_code == 200
        items = res_review.json()["data"]["items"]
        assert len(items) > 0

        # Review process
        res_process = await client.patch("/admin/review/fb:post-101", json={"action": "approve", "note": "Đã kiểm chứng ok"}, headers=headers)
        assert res_process.status_code == 200
        assert res_process.json()["data"]["status"] == "processed"

        # Dashboard Summary
        res_dashboard = await client.get("/admin/dashboard/summary", headers=headers)
        assert res_dashboard.status_code == 200
        dash = res_dashboard.json()["data"]
        assert "alerts" in dash
        assert "pipeline_jobs" in dash
        assert "knowledge_graph" in dash
