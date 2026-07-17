from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.config import BE2Config
from app.exceptions import ValidationError
from app.intelligence.embedder import Embedder
from app.intelligence.llm_router import LLMRouter, decide_route
from app.intelligence.nli import NLIService
from app.intelligence.rerank import Reranker
from app.pipelines.content.validators import validate_citations
from app.pipelines.social.entity_link import EntityLinker
from app.pipelines.social.ingest import normalize_social_payload
from app.schemas import CandidateKhoan, Citation, NliLabel, TopicResult
from app.workers.arq_settings import BE2_WORKER_FUNCTIONS, redis_settings
from app.workers.content_jobs import JOB_NAMES as CONTENT_JOB_NAMES
from app.workers.social_jobs import JOB_NAMES as SOCIAL_JOB_NAMES


class SimpleOut(BaseModel):
    value: str


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)
    async def health(self):
        return {"ok": True}


class FakeModel:
    def encode(self, batch, normalize_embeddings=True):
        return [[float(len(text)), 0.0] for text in batch]


class FakeVector:
    def __init__(self, hits=None):
        self.hits = hits or []
    async def search(self, collection, vector, *, limit, query_filter=None):
        return self.hits


class FakeRepo:
    def __init__(self):
        self.edges = []
    async def create_link_edge(self, bai_dang_id, candidate, *, method):
        self.edges.append((bai_dang_id, candidate.khoan_id, method))


@pytest.mark.asyncio
async def test_router_policy_schema_retry_needs_review():
    assert decide_route("parse_light", "low") == "local"
    assert decide_route("ner_re_complex", "high") == "large"
    assert decide_route("rerank", "high") == "large"
    router = LLMRouter(BE2Config(llm_retry_count=1), FakeLLM([{"output": {"bad": 1}}, {"output": {"bad": 2}}]))
    result = await router.complete("ner_re_complex", "prompt", SimpleOut, "high")
    assert result["needs_review"] is True
    assert len(router.client.calls) == 2


@pytest.mark.asyncio
async def test_context_required_for_brief():
    router = LLMRouter(BE2Config(), FakeLLM([]))
    with pytest.raises(Exception):
        await router.complete("brief", "no retrieved context", SimpleOut, "high")


@pytest.mark.asyncio
async def test_embedding_validation():
    embedder = Embedder(BE2Config(embedding_batch_size=1), model=FakeModel())
    assert len(await embedder.embed_texts([" a ", "b"])) == 2
    with pytest.raises(ValidationError):
        await embedder.embed_texts([])
    with pytest.raises(ValidationError):
        embedder._validate_vectors([[1.0], [1.0, 2.0]], 2)


@pytest.mark.asyncio
async def test_nli_closed_labels_low_confidence_safe():
    class Model:
        def predict(self, **kwargs):
            return {"label": "contradiction", "score": 0.2, "model": "fake"}
    result = await NLIService(BE2Config(nli_confidence_threshold=0.7), Model()).nli_pair("premise", "hypothesis")
    assert result["label"] in {label.value for label in NliLabel}
    assert result["label"] == "khong_ro"
    assert 0 <= result["score"] <= 1


def test_citation_substring_validation():
    source = [CandidateKhoan(khoan_id="k1", noi_dung="Người nộp thuế phải kê khai đúng hạn.", score=1)]
    validate_citations([Citation(khoan_id="k1", quote="kê khai đúng hạn")], source)
    with pytest.raises(ValidationError):
        validate_citations([Citation(khoan_id="k1", quote="không có")], source)
    with pytest.raises(ValidationError):
        validate_citations([Citation(khoan_id="k2", quote="kê khai")], source)


@pytest.mark.asyncio
async def test_entity_link_invariants_dry_run_and_unknown_id():
    repo = FakeRepo()
    linker = EntityLinker(
        FakeVector([{"score": 0.9, "payload": {"khoan_id": "k1"}}]),
        repo,
        embedder=Embedder(BE2Config(), model=FakeModel()),
        reranker=Reranker(LLMRouter(BE2Config(), FakeLLM([{"output": {"items": [{"khoan_id": "k1", "score": 0.9}]}}]))),
        config=BE2Config(link_threshold=0.7),
    )
    blocked = await linker.preview(bai_dang_id="facebook:1", content="test", topic=TopicResult(bai_dang_id="facebook:1", score=0.1, status="needs_review", model="m"), dry_run=True)
    assert blocked.proposed_edges == []
    ok = await linker.preview(bai_dang_id="facebook:1", content="test", topic=TopicResult(bai_dang_id="facebook:1", slug="tax", score=0.9, status="classified", model="m"), dry_run=True)
    assert ok.proposed_edges[0].khoan_id == "k1"
    assert repo.edges == []


@pytest.mark.asyncio
async def test_rerank_rejects_unknown_candidate_id():
    reranker = Reranker(LLMRouter(BE2Config(), FakeLLM([{"output": {"items": [{"khoan_id": "made-up", "score": 1.0}]}}])))
    with pytest.raises(ValidationError):
        await reranker.rerank("query", [{"khoan_id": "k1"}])


def test_ingest_pseudonymizes_author():
    post = normalize_social_payload({"platform": "Facebook", "external_id": "1", "content": "nội dung", "author_id": "raw-id"}, BE2Config(author_hmac_secret="secret"))
    assert post.platform == "facebook"
    assert post.external_id == "1"
    assert post.tac_gia_hash != "raw-id"

def test_be2_worker_settings_are_scope_limited():
    names = {fn.__name__ for fn in BE2_WORKER_FUNCTIONS}
    assert names == SOCIAL_JOB_NAMES | CONTENT_JOB_NAMES
    assert "publish" not in " ".join(names)
    settings = redis_settings(BE2Config(redis_url="redis://localhost:6379/5"))
    assert settings.database == 5
