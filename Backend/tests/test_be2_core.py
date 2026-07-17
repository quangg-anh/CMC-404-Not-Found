from __future__ import annotations

import pytest
import httpx
from pydantic import BaseModel

from app.config import BE2Config
from app.exceptions import ValidationError
from app.adapters.postgres_content import PostgresContentRepository
from app.adapters.qdrant_vector import QdrantVectorClient
from app.intelligence.embedder import Embedder
from app.intelligence.llm_router import LLMRouter, decide_route
from app.intelligence.nli import NLIService
from app.intelligence.rerank import Reranker
from app.pipelines.content.validators import validate_citations
from app.pipelines.social.collectors import FacebookGraphCollector, ForumFeedCollector, SocialDailyMonitor, YouTubeDataCollector
from app.pipelines.social.entity_link import EntityLinker
from app.pipelines.social.ingest import normalize_social_payload
from app.schemas import BriefDraft, CandidateKhoan, Citation, NliLabel, Status, SuggestDraft, TopicResult, LinkPreview, LinkCandidate
from app.workers.arq_settings import BE2_WORKER_FUNCTIONS, cron_jobs, redis_settings
from app.workers.content_jobs import JOB_NAMES as CONTENT_JOB_NAMES
from app.workers.social_jobs import JOB_NAMES as SOCIAL_JOB_NAMES, daily_social_monitor


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

class FakeResponse:
    def __init__(self, payload, text=""):
        self.payload = payload
        self.text = text
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload

class FakeStatusResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://www.googleapis.com/youtube/v3/search")
    def raise_for_status(self):
        response = httpx.Response(self.status_code, request=self.request)
        raise httpx.HTTPStatusError("status error", request=self.request, response=response)

class FakeHttp:
    def __init__(self, payload=None, text=""):
        self.payload = payload or {}
        self.text = text
        self.calls = []
    async def get(self, url, params=None):
        self.calls.append((url, params))
        return FakeResponse(self.payload, self.text)

class FakeOpenAIEmbeddingHttp:
    def __init__(self):
        self.calls = []
    async def post(self, url, headers=None, json=None):
        self.calls.append((url, headers, json))
        return FakeResponse({"data": [
            {"index": index, "embedding": [float(index + 1), 0.0]}
            for index, _ in enumerate(json["input"])
        ]})

class FakeYouTubeHttp:
    def __init__(self):
        self.calls = []
    async def get(self, url, params=None):
        self.calls.append((url, params))
        if "commentThreads" in url:
            return FakeResponse({"items": [
                {"snippet": {"topLevelComment": {"id": "comment-1", "snippet": {"authorDisplayName": "user-1", "authorChannelId": {"value": "author-channel-1"}, "authorChannelUrl": "https://www.youtube.com/channel/author-channel-1", "textDisplay": "Tôi cần hỏi về thuế doanh nghiệp", "publishedAt": "2026-07-17T00:01:00Z", "updatedAt": "2026-07-17T00:04:00Z", "likeCount": 2}}}},
                {"snippet": {"topLevelComment": {"id": "comment-2", "snippet": {"authorDisplayName": "user-2", "authorChannelId": {"value": "author-channel-2"}, "textDisplay": "Công ty mới thành lập kê khai thuế như thế nào", "publishedAt": "2026-07-17T00:02:00Z", "likeCount": 1}}}},
                {"snippet": {"topLevelComment": {"id": "comment-3", "snippet": {"authorDisplayName": "user-3", "authorChannelId": {"value": "author-channel-3"}, "textDisplay": "Hóa đơn điện tử thuế sai thì xử lý ra sao", "publishedAt": "2026-07-17T00:03:00Z", "likeCount": 0}}}},
            ]})
        return FakeResponse({"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "Luật thuế doanh nghiệp", "description": "Giải thích pháp luật", "publishedAt": "2026-07-17T00:00:00Z", "channelId": "c1", "channelTitle": "Kênh pháp luật"}}]})

class FakeYouTubeFallbackHttp:
    def __init__(self):
        self.calls = []
    async def get(self, url, params=None):
        self.calls.append((url, params))
        if "commentThreads" in url:
            video_id = params["videoId"]
            if video_id == "locked-video":
                return FakeResponse({"items": []})
            if video_id == "off-topic-video":
                return FakeResponse({"items": [
                    {"snippet": {"topLevelComment": {"id": "off-topic-comment", "snippet": {"authorDisplayName": "user-off", "textDisplay": "Bình luận về bóng đá không liên quan pháp luật", "publishedAt": "2026-07-17T00:02:00Z", "likeCount": 5}}}},
                ]})
            return FakeResponse({"items": [
                {"snippet": {"topLevelComment": {"id": "good-comment", "snippet": {"authorDisplayName": "user-good", "authorChannelId": {"value": "author-good"}, "textDisplay": "Bình luận về thuế và quy định pháp luật doanh nghiệp", "publishedAt": "2026-07-17T00:03:00Z", "likeCount": 10}}}},
            ]})
        return FakeResponse({"items": [
            {"id": {"videoId": "locked-video"}, "snippet": {"title": "Video thuế mới nhất", "description": "Pháp luật thuế", "publishedAt": "2026-07-17T00:00:00Z", "channelId": "c1"}},
            {"id": {"videoId": "off-topic-video"}, "snippet": {"title": "Video thuế viral", "description": "Pháp luật thuế", "publishedAt": "2026-07-16T00:00:00Z", "channelId": "c2"}},
            {"id": {"videoId": "good-video"}, "snippet": {"title": "Video thuế có bình luận đúng chủ đề", "description": "Pháp luật thuế", "publishedAt": "2026-07-15T00:00:00Z", "channelId": "c3"}},
        ]})

class FakeYouTubeRotatingKeyHttp(FakeYouTubeHttp):
    async def get(self, url, params=None):
        self.calls.append((url, params))
        if params["key"] == "bad-key":
            return FakeStatusResponse(429)
        return await super().get(url, params)


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
    embedder = Embedder(BE2Config(embedding_provider="local", embedding_batch_size=1, embedding_dimension=2), model=FakeModel())
    assert len(await embedder.embed_texts([" a ", "b"])) == 2
    with pytest.raises(ValidationError):
        await embedder.embed_texts([])
    with pytest.raises(ValidationError):
        embedder._validate_vectors([[1.0], [1.0, 2.0]], 2)

@pytest.mark.asyncio
async def test_openai_compatible_embedding_uses_injected_http_not_ollama():
    http = FakeOpenAIEmbeddingHttp()
    cfg = BE2Config(
        embedding_provider="openai",
        embedding_base_url="http://localhost:11434/v1",
        embedding_api_key="ollama",
        embedding_model="bge-m3",
        embedding_dimension=2,
    )
    vectors = await Embedder(cfg, http_client=http).embed_texts(["một", "hai"])
    assert vectors == [[1.0, 0.0], [2.0, 0.0]]
    assert http.calls[0][0] == "http://localhost:11434/v1/embeddings"
    assert http.calls[0][2]["model"] == "bge-m3"


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
        embedder=Embedder(BE2Config(embedding_provider="local", embedding_dimension=2), model=FakeModel()),
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

@pytest.mark.asyncio
async def test_nli_default_heuristic_supports_gold_patterns():
    result = await NLIService(BE2Config(nli_confidence_threshold=0.7)).nli_pair(
        "To chuc phai thong bao cho co quan quan ly khi xay ra su co lo lot du lieu.",
        "Khong dung rang chuc phai thong bao cho co quan quan ly khi xay ra su co lo lot du.",
    )
    assert result["label"] == "mau_thuan"

    unknown = await NLIService(BE2Config()).nli_pair("Quy dinh ve bao ve du lieu.", "Van de nay chua duoc quy dinh ro rang.")
    assert unknown["label"] == "khong_ro"

def test_be2_worker_settings_are_scope_limited():
    names = {fn.__name__ for fn in BE2_WORKER_FUNCTIONS}
    assert names == SOCIAL_JOB_NAMES | CONTENT_JOB_NAMES
    assert "publish" not in " ".join(names)
    settings = redis_settings(BE2Config(redis_url="redis://localhost:6379/5"))
    assert settings.database == 5

def test_daily_social_monitor_cron_enabled_and_disabled():
    assert cron_jobs(BE2Config(social_monitor_enabled=False)) == []
    jobs = cron_jobs(BE2Config(social_monitor_enabled=True, social_monitor_cron_hour=7, social_monitor_cron_minute=30))
    assert len(jobs) == 1

@pytest.mark.asyncio
async def test_facebook_collector_uses_graph_api_contract():
    cfg = BE2Config(facebook_access_token="token", facebook_page_ids=["page-1"], social_monitor_topics=["thuế"])
    http = FakeHttp({"data": [{"id": "page-1_1", "message": "Bài viết về thuế và pháp luật", "permalink_url": "https://facebook.com/page-1/posts/1", "created_time": "2026-07-17T00:00:00+0000", "from": {"id": "author-raw"}}]})
    posts = await FacebookGraphCollector(cfg, http).collect(["thuế"], limit_per_topic=5)
    assert posts[0]["platform"] == "facebook"
    assert posts[0]["external_id"] == "page-1_1"
    assert posts[0]["author_id"] == "author-raw"
    assert "access_token" in http.calls[0][1]

@pytest.mark.asyncio
async def test_youtube_collector_uses_real_search_contract_and_topic_comment_limit():
    cfg = BE2Config(youtube_api_key="key", social_monitor_topics=["thuế"], youtube_search_order="relevance", youtube_search_results_per_topic=25, youtube_comments_per_video=20, youtube_comments_per_topic=2)
    http = FakeYouTubeHttp()
    posts = await YouTubeDataCollector(cfg, http).collect(["thuế"], limit_per_topic=3)
    assert posts[0]["platform"] == "youtube"
    assert posts[0]["url"] == "https://www.youtube.com/watch?v=v1"
    assert http.calls[0][1]["part"] == "snippet"
    assert http.calls[0][1]["order"] == "date"
    assert http.calls[0][1]["maxResults"] == 25
    assert http.calls[0][1]["regionCode"] == "VN"
    assert http.calls[0][1]["relevanceLanguage"] == "vi"
    assert http.calls[0][1]["publishedAfter"]
    assert posts[0]["youtube_kind"] == "video"
    assert posts[0]["comments"][0]["text"] == "Tôi cần hỏi về thuế doanh nghiệp"
    assert posts[0]["comment_count"] == 3
    assert posts[1]["youtube_kind"] == "comment"
    assert posts[1]["external_id"] == "v1:comment-1"
    assert "Người bình luận: user-1" in posts[1]["content"]
    assert "Link video: https://www.youtube.com/watch?v=v1" in posts[1]["content"]
    assert "Link bình luận: https://www.youtube.com/watch?v=v1&lc=comment-1" in posts[1]["content"]
    assert "Tôi cần hỏi về thuế doanh nghiệp" in posts[1]["content"]
    assert posts[1]["author_id"] == "author-channel-1"
    assert posts[1]["video_url"] == "https://www.youtube.com/watch?v=v1"
    assert posts[1]["comment_url"] == "https://www.youtube.com/watch?v=v1&lc=comment-1"
    assert posts[1]["comment_author_name"] == "user-1"
    assert posts[1]["comment_author_profile_url"] == "https://www.youtube.com/channel/author-channel-1"
    assert posts[1]["comment_like_count"] == 2
    assert posts[1]["comment_published_at"] == "2026-07-17T00:01:00Z"
    assert posts[1]["comment_updated_at"] == "2026-07-17T00:04:00Z"
    assert posts[1]["video_channel_title"] == "Kênh pháp luật"
    assert posts[2]["external_id"] == "v1:comment-2"
    assert len([post for post in posts if post.get("youtube_kind") == "comment"]) == 2

@pytest.mark.asyncio
async def test_youtube_collector_rotates_api_keys_on_quota_error():
    cfg = BE2Config(youtube_api_keys=["bad-key", "good-key"], youtube_api_key="legacy-key", youtube_comments_per_topic=1)
    http = FakeYouTubeRotatingKeyHttp()
    posts = await YouTubeDataCollector(cfg, http).collect(["thuế"], limit_per_topic=1)
    keys_used = [call[1]["key"] for call in http.calls if "search" in call[0]]
    assert keys_used[:2] == ["bad-key", "good-key"]
    assert posts[0]["youtube_kind"] == "video"
    assert any(post.get("youtube_kind") == "comment" for post in posts)

@pytest.mark.asyncio
async def test_youtube_collector_skips_locked_empty_and_off_topic_comments():
    cfg = BE2Config(youtube_api_key="key", youtube_comments_per_video=10, youtube_comments_per_topic=1, youtube_search_order="viewCount")
    http = FakeYouTubeFallbackHttp()
    posts = await YouTubeDataCollector(cfg, http).collect(["thuế"], limit_per_topic=1)
    assert [call[1]["order"] for call in http.calls if "search" in call[0]][0] == "date"
    assert all(post.get("video_id") != "locked-video" for post in posts)
    assert all(post.get("video_id") != "off-topic-video" for post in posts)
    assert any(post.get("video_id") == "good-video" for post in posts)
    assert posts[-1]["content"].endswith("Bình luận về thuế và quy định pháp luật doanh nghiệp")

@pytest.mark.asyncio
async def test_forum_feed_collector_parses_rss_topic():
    xml = """<?xml version="1.0"?><rss><channel><item><title>Tin thuế mới</title><description>Chính sách pháp luật về thuế</description><link>https://example.com/tax</link><pubDate>Fri, 17 Jul 2026 00:00:00 GMT</pubDate><author>newsroom</author></item></channel></rss>"""
    cfg = BE2Config(forum_feed_urls=["https://example.com/rss"])
    posts = await ForumFeedCollector(cfg, FakeHttp(text=xml)).collect(["thuế"], limit_per_topic=3)
    assert posts[0]["platform"] == "forum"
    assert posts[0]["url"] == "https://example.com/tax"
    assert posts[0]["source_topic"] == "thuế"

@pytest.mark.asyncio
async def test_daily_social_monitor_dedupes_and_worker_ingests():
    class FakeCollector:
        async def collect(self, topics, *, limit_per_topic=None):
            return [
                {"platform": "facebook", "external_id": "1", "content": "nội dung pháp luật", "author_id": "a"},
                {"platform": "facebook", "external_id": "1", "content": "trùng", "author_id": "a"},
            ]
    monitor = SocialDailyMonitor([FakeCollector()])
    posts = await monitor.collect(["thuế"], limit_per_topic=5)
    assert len(posts) == 1

    class FakeIngestService:
        async def ingest(self, payload):
            class Post:
                def model_dump(self_inner):
                    return {"id": payload["external_id"]}
            return Post()

    result = await daily_social_monitor({"config": BE2Config(social_monitor_topics=["thuế"]), "social_daily_monitor": monitor, "social_ingest_service": FakeIngestService()})
    assert result["status"] == "success"
    assert result["data"]["collected"] == 1

@pytest.mark.asyncio
async def test_daily_social_monitor_dry_run_collects_without_ingest():
    class FakeCollector:
        async def collect(self, topics, *, limit_per_topic=None):
            return [{"platform": "youtube", "external_id": "comment-1", "content": "nội dung về thuế", "author_id": "a"}]

    class FailingIngestService:
        async def ingest(self, payload):
            raise AssertionError("dry_run must not ingest")

    result = await daily_social_monitor(
        {"config": BE2Config(social_monitor_topics=["thuế"]), "social_daily_monitor": SocialDailyMonitor([FakeCollector()]), "social_ingest_service": FailingIngestService()},
        {"job_id": "dry", "correlation_id": "dry", "payload": {"topics": ["thuế"], "limit_per_topic": 1}, "dry_run": True},
    )
    assert result["status"] == "success"
    assert result["data"]["dry_run"] is True
    assert result["data"]["collected"] == 1
    assert result["data"]["ingested"] == []

@pytest.mark.asyncio
async def test_daily_social_monitor_ingests_then_chains_topic_link_alert():
    class FakeCollector:
        async def collect(self, topics, *, limit_per_topic=None):
            return [{"platform": "youtube", "external_id": "comment-1", "content": "nội dung về thuế", "author_id": "a"}]

    class FakeIngestService:
        async def ingest(self, payload):
            return normalize_social_payload(payload, BE2Config(author_hmac_secret="secret"))

    class ChainRepo:
        def __init__(self):
            self.post = None
            self.topic = None
            self.alert_calls = []
        async def get_post(self, bai_dang_id):
            return self.post
        async def save_topic(self, result):
            self.topic = result
        async def get_topic(self, bai_dang_id):
            return self.topic

    class Classifier:
        async def classify(self, *, bai_dang_id, content):
            return TopicResult(bai_dang_id=bai_dang_id, slug="thue", score=0.9, status="classified", model="fake")

    class Linker:
        async def preview(self, *, bai_dang_id, content, topic, dry_run=True):
            return LinkPreview(bai_dang_id=bai_dang_id, candidates=[], proposed_edges=[LinkCandidate(khoan_id="k1", score=0.8)], dry_run=dry_run, status="ok")

    class AlertService:
        async def maybe_create_alert(self, *, signals, dry_run=False):
            return None

    repo = ChainRepo()
    ingest = FakeIngestService()
    original_ingest = ingest.ingest

    async def ingest_and_store(payload):
        post = await original_ingest(payload)
        repo.post = post
        return post

    ingest.ingest = ingest_and_store
    result = await daily_social_monitor(
        {
            "config": BE2Config(social_monitor_topics=["thuế"]),
            "social_daily_monitor": SocialDailyMonitor([FakeCollector()]),
            "social_ingest_service": ingest,
            "social_repo": repo,
            "topic_classifier": Classifier(),
            "entity_linker": Linker(),
            "alert_signal_service": AlertService(),
        },
        {"job_id": "chain", "correlation_id": "chain", "payload": {"topics": ["thuế"], "limit_per_topic": 1, "chain": True}, "dry_run": False},
    )
    assert result["status"] == "success"
    assert result["data"]["chain"][0]["topic"]["slug"] == "thue"
    assert result["data"]["chain"][0]["link"]["proposed_edges"][0]["khoan_id"] == "k1"
    assert result["data"]["chain"][0]["alert"] is None

@pytest.mark.asyncio
async def test_qdrant_baidang_contract_platform_enum():
    client = QdrantVectorClient(FakeQdrant())
    with pytest.raises(ValidationError):
        await client.upsert_baidang(point_id="1", vector=[0.1, 0.2], bai_dang_id="x:1", chu_de="tax", platform="x")
    await client.upsert_baidang(point_id="1", vector=[0.1, 0.2], bai_dang_id="facebook:1", chu_de="tax", platform="facebook")

@pytest.mark.asyncio
async def test_postgres_content_adapter_uses_contract_columns():
    pool = FakePool()
    repo = PostgresContentRepository(pool)
    await repo.save_brief(BriefDraft(title="t", bullets=["b"], citations=[Citation(khoan_id="k1", quote="q")], status=Status.NEEDS_REVIEW, model="m", audit={"uuid": "00000000-0000-0000-0000-000000000001"}))
    await repo.save_suggestion(SuggestDraft(draft_content="d", related_alert_ids=["00000000-0000-0000-0000-000000000002"], status=Status.DRAFT, disclaimer="internal"))
    queries = "\n".join(query for query, _ in pool.conn.calls)
    assert "INSERT INTO briefs (id, tieu_de, media_type, status, citations)" in queries
    assert "INSERT INTO suggestions (id, draft_text, alert_ids, khoan_ids, claim_labels, status)" in queries
    assert "payload_json" not in queries

class FakeQdrant:
    async def get_collection(self, collection):
        return {"config": {"params": {"vectors": {"size": 2, "distance": "Cosine"}}}}
    async def upsert(self, **kwargs):
        self.last_upsert = kwargs

class FakeConn:
    def __init__(self):
        self.calls = []
    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return {"id": args[0]}
    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return []

class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn
    async def __aenter__(self):
        return self.conn
    async def __aexit__(self, exc_type, exc, tb):
        return False

class FakePool:
    def __init__(self):
        self.conn = FakeConn()
    def acquire(self):
        return FakeAcquire(self.conn)
