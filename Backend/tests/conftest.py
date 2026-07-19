"""Test-only dependency overrides.

Production code (`app/api/deps.py`) connects strictly to real Neo4j/Postgres/Qdrant/BE2.
For hermetic unit tests we inject lightweight, query-aware fakes via FastAPI
``dependency_overrides`` so the suite does not require live infrastructure and never blocks on
downloading embedding models.
"""
from __future__ import annotations

import os
from typing import Any

# Dev bearer shortcuts (test-admin-*) must be enabled before app.security loads settings.
os.environ.setdefault("ENABLE_DEV_TOKENS", "true")
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("AUTH_TOKEN_SECRET", "test-auth-token-secret-at-least-32-chars")

import pytest

from app.main import app
from app.api import deps
from app.adapters.qdrant_vector import QdrantVectorClient
from app.intelligence.llm_router import LLMRouter

CANONICAL_KHOAN = "Người nộp thuế phải kê khai đúng hạn theo quy định tại Khoản 15/2020/ND-CP::D1.K1."
VALID_QUOTE = "Người nộp thuế phải kê khai đúng hạn"

VAN_BAN = {
    "vb_id": "vb-15-2020",
    "so_hieu": "15/2020/ND-CP",
    "ten": "Nghị định 15/2020/ND-CP",
    "visibility": "public",
    "trang_thai": "hieu_luc",
    "ngay_ban_hanh": "2020-01-15",
}

BRIEFS: dict[str, dict[str, Any]] = {
    "brief-101": {"id": "brief-101", "tieu_de": "Tin đã xuất bản", "media_type": "text", "status": "published", "citations": [{"khoan_id": "15/2020/ND-CP::D1.K1", "quote": VALID_QUOTE}], "created_by": None, "created_at": None, "published_at": None},
    "brief-102": {"id": "brief-102", "tieu_de": "Bản nháp chờ duyệt", "media_type": "text", "status": "review", "citations": [{"khoan_id": "15/2020/ND-CP::D1.K1", "quote": VALID_QUOTE}], "created_by": None, "created_at": None, "published_at": None},
    "brief-no-cit": {"id": "brief-no-cit", "tieu_de": "Thiếu căn cứ", "media_type": "text", "status": "review", "citations": [], "created_by": None, "created_at": None, "published_at": None},
}

SUGGESTS: dict[str, dict[str, Any]] = {
    "suggest-102": {"id": "suggest-102", "tieu_de": "Đề xuất đính chính", "noi_dung_dinh_chinh": "Đính chính mức phạt.", "khoan_doi_chieu_id": "15/2020/ND-CP::D1.K1", "status": "draft", "created_by": None, "created_at": None},
}

# In-memory jobs table so ingest → GET /admin/jobs/{id} works in hermetic tests.
JOBS: dict[str, dict[str, Any]] = {}


class FakeEmbedder:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]


class FakeAsyncConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        q = query.lower()
        key = args[0] if args else None
        if "from jobs" in q and "where id" in q:
            return JOBS.get(str(key))
        if "from briefs where id" in q:
            return BRIEFS.get(str(key))
        if "from suggestions where id" in q:
            return SUGGESTS.get(str(key))
        if "from alerts where id" in q:
            return {"id": str(key), "payload_json": {"alert_id": str(key), "nli_label": "mau_thuan", "severity": "high", "status": "open", "cluster_size": 12}, "created_at": None}
        if "insert into briefs" in q:
            return {"id": key}
        if "insert into suggestions" in q:
            return {"id": key}
        return None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = query.lower()
        if "from jobs" in q:
            rows = list(JOBS.values())
            if "limit" in q and args:
                limit = int(args[-1])
                return rows[:limit]
            return rows
        if "from job_events" in q:
            return []
        if "from briefs" in q:
            if "where status" in q and args:
                return [b for b in BRIEFS.values() if b["status"] == args[0]]
            return list(BRIEFS.values())
        if "from suggestions" in q:
            return list(SUGGESTS.values())
        return []

    async def execute(self, query: str, *args: Any) -> str:
        q = query.lower()
        if "insert into jobs" in q and args:
            job_id = str(args[0])
            job_type = "legal_ingest"
            if "'social_ingest'" in query:
                job_type = "social_ingest"
            elif "'legal_ingest'" in query:
                job_type = "legal_ingest"
            payload = args[1] if len(args) > 1 else "{}"
            created = args[2] if len(args) > 2 else None
            JOBS[job_id] = {
                "id": job_id,
                "type": job_type,
                "status": "queued",
                "stage": "queued",
                "payload_json": payload,
                "error": None,
                "created_at": created,
                "updated_at": created,
            }
            return "INSERT 0 1"
        if "update jobs" in q and args:
            job_id = str(args[-1])
            if job_id in JOBS:
                if "status" in q and len(args) >= 1:
                    JOBS[job_id]["status"] = args[0]
                if "error" in q and len(args) >= 2:
                    JOBS[job_id]["error"] = args[1]
                return "UPDATE 1"
            return "UPDATE 0"
        if "delete from briefs" in q and args:
            key = str(args[0])
            if key in BRIEFS:
                del BRIEFS[key]
                return "DELETE 1"
            return "DELETE 0"
        if "delete from suggestions" in q and args:
            key = str(args[0])
            if key in SUGGESTS:
                del SUGGESTS[key]
                return "DELETE 1"
            return "DELETE 0"
        return "OK"

    async def fetchval(self, query: str, *args: Any) -> Any:
        q = query.lower()
        if "count(*)" in q and "from briefs" in q:
            return len([b for b in BRIEFS.values() if b.get("status") in {"draft", "review"}])
        if "count(*)" in q and "from suggestions" in q:
            return len([s for s in SUGGESTS.values() if s.get("status") == "ready"])
        if "count(*)" in q and "from alerts" in q:
            return 1
        return 0


class FakeAsyncPool:
    def acquire(self):
        return FakeAsyncConnection()

    async def execute(self, query: str, *args: Any) -> str:
        async with FakeAsyncConnection() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        async with FakeAsyncConnection() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        async with FakeAsyncConnection() as conn:
            return await conn.fetchrow(query, *args)


class _Hit:
    def __init__(self, id_val: str, score: float, payload: dict[str, Any]):
        self.id = id_val
        self.score = score
        self.payload = payload


class FakeRawQdrant:
    async def get_collection(self, collection: str) -> dict[str, Any]:
        return {"vectors": {"size": 1536, "distance": "Cosine"}}

    async def search(self, collection_name: str, query_vector: list[float], limit: int, query_filter: Any | None = None) -> list[Any]:
        return [
            _Hit(
                "15/2020/ND-CP::D1.K1",
                0.92,
                {"khoan_id": "15/2020/ND-CP::D1.K1", "van_ban_id": "vb-15-2020", "visibility": "public", "noi_dung": CANONICAL_KHOAN},
            ),
        ][:limit]

    async def upsert(self, collection_name: str, points: list[Any]) -> None:
        return None


class _FakeCursor:
    def __init__(self, query: str, params: dict[str, Any]):
        self.q = query.lower()
        self.params = params

    async def single(self):
        # Idea 01 time-travel: "15/2020/ND-CP::D1.K1" is treated as replaced by a văn bản effective
        # 2026-07-01. It only becomes INVALID once as_of reaches the far-future test date, so the
        # default (today) QA tests keep seeing it as valid.
        if "invalid_ids" in self.q:
            as_of = str(self.params.get("as_of", ""))
            if as_of >= "2027-01-01":
                return {"invalid_ids": ["15/2020/ND-CP::D1.K1"]}
            return {"invalid_ids": []}
        if "match (k:khoan" in self.q and "k.noi_dung" in self.q:
            return {"noi_dung": CANONICAL_KHOAN}
        # Admin review PATCH clears needs_review on matching social/legal nodes.
        if "needs_review = false" in self.q or "review_action" in self.q:
            neo_id = str(self.params.get("id", ""))
            if neo_id in {"fb:post-101", "15/2020/ND-CP::D1.K1", "vb-15-2020"} or neo_id.startswith("fb:"):
                return {"c": 1}
            return {"c": 0}
        if "count(" in self.q and " as cnt" in self.q:
            return {"cnt": 3}
        if "van_ban" in self.q or "vanbanphapluat" in self.q:
            if "collect" in self.q:
                return {"v": dict(VAN_BAN), "khoans": []}
        return None

    async def consume(self):
        return None

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        if " as kid" in self.q and " as nd" in self.q:
            # QAService._direct_lookup / graph keyword search returning khoản rows
            yield {
                "kid": "15/2020/ND-CP::D1.K1",
                "nd": CANONICAL_KHOAN,
                "hits": 3,
            }
            return
        if "co_khoan" in self.q and "vb_id" in self.q and "return kid" in self.q:
            yield {
                "kid": "15/2020/ND-CP::D1.K1",
                "vb_id": "vb-15-2020",
                "so_hieu": "15/2020/ND-CP",
                "ten_van_ban": "Nghị định 15",
                "dieu_id": "15/2020/ND-CP::D1",
                "so_dieu": "Điều 1",
                "tieu_de_dieu": "Kê khai thuế",
                "khoan_id": "15/2020/ND-CP::D1.K1",
                "noi_dung": CANONICAL_KHOAN,
            }
            return
        if "doi_chieu" in self.q and "clarity_risk" in self.q:
            # Idea 02 clarity index aggregate.
            yield {
                "khoan_id": "168/2024/ND-CP::D6.K6",
                "noi_dung": "Phạt tiền đối với hành vi có nồng độ cồn...",
                "mau_thuan": 22,
                "khong_ro": 10,
                "volume": 47,
                "clarity_risk": 0.681,
            }
            return
        if "tu_ngay" in self.q:
            # Time-travel notice: rule changes on 2026-07-01, so only show it for earlier as_of.
            as_of = str(self.params.get("as_of", ""))
            if as_of < "2026-07-01":
                yield {"cu": "15/2020/ND-CP", "moi": "168/2024/ND-CP", "tu_ngay": "2026-07-01"}
            return
        if "vanbanphapluat" in self.q and "return v" in self.q and "collect" not in self.q:
            yield {"v": dict(VAN_BAN)}
        elif "(t:chude)" in self.q and ("return t" in self.q or "as topic" in self.q):
            topic = {"slug": "nong-do-con", "ten": "Nồng độ cồn", "post_count": 42}
            if "as topic" in self.q:
                yield {"topic": topic}
            else:
                yield {"t": topic}
        elif "needs_review = true" in self.q:
            yield {"id": 1, "labels": ["BaiDang"], "n": {"bai_dang_id": "fb:post-101", "noi_dung": "Bài đăng cần rà soát", "review_reason": "Low NLI confidence"}}


class FakeNeo4jSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def run(self, query: str, **kwargs: Any):
        return _FakeCursor(query, kwargs)


class FakeNeo4jDriver:
    def session(self, **kwargs: Any):
        return FakeNeo4jSession()

    async def close(self):
        return None


class FakeLLMClient:
    """Simulates a BE2 LLM gateway. Produces a hallucinated (non-canonical) quote only when the
    prompt explicitly asks to, so the fail-closed path can be exercised deterministically."""

    async def complete(self, *, route: str, model: str, task: str, prompt: str, timeout_s: float) -> dict[str, Any]:
        if task == "qa":
            low = prompt.lower()
            if "hallucinate" in low or "bịa đặt" in low:
                return {
                    "answer": "Câu trả lời có trích dẫn bịa đặt.",
                    "citations": [{"khoan_id": "15/2020/ND-CP::D1.K1", "quote": "Đoạn văn bịa đặt hoàn toàn không có trong Khoản."}],
                    "confidence": "high",
                }
            if "contradict" in low or "mâu thuẫn" in low:
                # Verbatim-but-contradicting: the quote is EXACTLY canonical (passes substring check),
                # but the answer states the opposite -> Idea 03 NLI must catch it and refuse.
                return {
                    "answer": "Người nộp thuế không phải kê khai đúng hạn.",
                    "citations": [{"khoan_id": "15/2020/ND-CP::D1.K1", "quote": VALID_QUOTE}],
                    "confidence": "high",
                }
            return {
                "answer": "Theo quy định, người nộp thuế phải kê khai đúng hạn.",
                "citations": [{"khoan_id": "15/2020/ND-CP::D1.K1", "quote": VALID_QUOTE}],
                "confidence": "high",
            }
        return {"result": "ok"}

    async def health(self) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture(autouse=True)
def _override_external_dependencies():
    JOBS.clear()

    async def _fake_pool():
        return FakeAsyncPool()

    async def _fake_driver():
        return FakeNeo4jDriver()

    async def _fake_qdrant():
        return QdrantVectorClient(FakeRawQdrant())

    async def _fake_embedder():
        return FakeEmbedder()

    async def _fake_llm_router():
        return LLMRouter(client=FakeLLMClient())

    app.dependency_overrides[deps.get_db_pool] = _fake_pool
    app.dependency_overrides[deps.get_neo4j_driver] = _fake_driver
    app.dependency_overrides[deps.get_qdrant_client] = _fake_qdrant
    app.dependency_overrides[deps.get_embedder] = _fake_embedder
    app.dependency_overrides[deps.get_llm_router] = _fake_llm_router
    yield
    app.dependency_overrides.clear()
