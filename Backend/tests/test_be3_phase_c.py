from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_publish_gate_role_and_citation_guardrails():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Case 1: Role check - admin_phap_che cannot publish briefs -> 403 Forbidden
        headers_phap_che = {"Authorization": "Bearer test-admin-phap-che"}
        res_forbidden = await client.post("/admin/briefs/brief-102/publish", headers=headers_phap_che)
        assert res_forbidden.status_code == 403

        # Case 2: Citations optional — brief without citations can still publish
        headers_truyen_thong = {"Authorization": "Bearer test-admin-truyen-thong"}
        res_no_cit = await client.post("/admin/briefs/brief-no-cit/publish", headers=headers_truyen_thong)
        assert res_no_cit.status_code == 200
        assert res_no_cit.json()["data"]["status"] == "published"

        # Case 3: Valid brief with accurate quotes -> 200 OK, transitions to published with audit_id
        res_ok = await client.post("/admin/briefs/brief-102/publish", headers=headers_truyen_thong)
        assert res_ok.status_code == 200
        data_ok = res_ok.json()["data"]
        assert data_ok["status"] == "published"
        assert "audit_id" in data_ok
        assert data_ok["published_by"] == "user-truyen-thong-1"


@pytest.mark.asyncio
async def test_suggestions_guardrail_cannot_be_published():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-admin-truyen-thong"}

        # Valid update: draft -> ready
        res_ready = await client.patch("/admin/suggestions/suggest-102", json={"status": "ready"}, headers=headers)
        assert res_ready.status_code == 200
        assert res_ready.json()["data"]["status"] == "ready"

        # Guardrail violation attempt: update to status='published' -> 400 Bad Request
        res_violation = await client.patch("/admin/suggestions/suggest-102", json={"status": "published"}, headers=headers)
        assert res_violation.status_code == 400
        assert "Guardrail Violation" in res_violation.json()["data"]["message"]


@pytest.mark.asyncio
async def test_citizen_news_portal_isolation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # List news: must strictly return status=published
        res_list = await client.get("/citizen/news")
        assert res_list.status_code == 200
        items = res_list.json()["data"]["items"]
        assert all(x["status"] == "published" for x in items)

        # Get detail of a published brief (brief-101) -> 200 OK
        res_published = await client.get("/citizen/news/brief-101")
        assert res_published.status_code == 200
        assert res_published.json()["data"]["id"] == "brief-101"

        # Get detail of a draft brief (brief-102 or brief-no-cit) -> 404 Not Found
        res_draft = await client.get("/citizen/news/brief-102")
        assert res_draft.status_code == 404
        assert "chưa được xuất bản" in res_draft.json()["data"]["message"]
