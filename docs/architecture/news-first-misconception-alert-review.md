# Review và kế hoạch cảnh báo hiểu nhầm theo hướng News-first

**Trạng thái:** Proposed  
**Ngày review:** 2026-07-19  
**Phạm vi trước mắt:** Rà soát bài báo công khai, bắt đầu với nguồn `phapluat.gov.vn` đang có.  
**Phạm vi mở rộng:** Facebook, YouTube, TikTok, diễn đàn và các nguồn nội dung công khai khác.

## 1. Kết luận kiến trúc

Không nên xây một pipeline riêng cho báo chí rồi sau đó xây lại cho mạng xã hội.

Nên chuyển lõi hiện tại từ khái niệm `SocialPost` sang một hợp đồng nguồn chung:

```text
Content source
  → Content item
  → Claim occurrence
  → Legal provision as-of
  → Verdict
  → Misconception cluster
  → Risk snapshot
  → Alert + human review
```

Trong giai đoạn đầu:

- `news` là source type được bật production.
- `phapluat.gov.vn` là source adapter đầu tiên.
- Các adapter Facebook, YouTube và forum hiện có được giữ, nhưng chưa dùng làm điều kiện phát cảnh báo production cho tới khi news pipeline đạt acceptance gate.
- Citizen Portal chỉ hiển thị nội dung đính chính đã qua duyệt; không hiển thị trực tiếp cảnh báo nội bộ.

Tên nghiệp vụ trên UI nên đổi từ **“Cảnh báo tin giả”** thành **“Cảnh báo nguy cơ hiểu nhầm”** hoặc **“Tín hiệu cần xác minh”**. NLI tự động chỉ cho biết một claim có dấu hiệu không phù hợp với căn cứ đã truy xuất, không đủ để kết luận một cơ quan báo chí cố tình đăng tin giả.

## 2. Hiện trạng đã kiểm tra

### 2.1. Phần có thể tái sử dụng

CMC đã có:

- Collector cho Facebook, YouTube và RSS/forum.
- Chuẩn hóa payload, pseudonym tác giả và deduplicate theo `platform + external_id`.
- Topic classifier, legal entity linker, claim extractor và NLI.
- Graph `BaiDang → YKien → DOI_CHIEU → Khoan`.
- `AlertMeta`, bảng Postgres `alerts`, provenance và workflow triage.
- Admin Alerts, Social Radar, Content Brief và Publish Gate.
- Service lấy bài từ `phapluat.gov.vn`.

Vì vậy không cần thay stack FastAPI, Neo4j, Qdrant, PostgreSQL, Redis hay MinIO.

### 2.2. Các khoảng trống phải sửa trước

| Mức | Phát hiện | Bằng chứng | Hệ quả |
|---|---|---|---|
| P0 | Daily monitor không chạy claim check/NLI | `Backend/app/workers/social_jobs.py:83` gọi alert với `signals=[]` | Crawl tự động không thể sinh cảnh báo hiểu nhầm |
| P0 | Kết quả NLI chưa được nối vào orchestration | `Neo4jSocialRepository.save_nli()` tồn tại nhưng không có caller production | Không hình thành `YKien`, provenance và volume thực |
| P0 | News pipeline đang tách khỏi alert pipeline | `PhapLuatNewsService.sync_briefs()` đi thẳng từ scrape sang `briefs` | Bài báo chỉ thành content draft, không được kiểm tra claim |
| P1 | Alert aggregation chỉ đếm list signal trong bộ nhớ của một lần gọi | `AlertSignalService.maybe_create_alert()` dùng `Counter(signals)` | Không gom được tín hiệu qua nhiều bài hoặc nhiều lần chạy |
| P1 | Cooldown/dedupe dùng hai loại key khác nhau | Caller tìm bằng `chu_de:khoan_id`, repository tìm thuộc tính `AlertMeta.uuid` | Cảnh báo trùng có thể không bị chặn |
| P1 | Link pháp luật chạy trên toàn bài thay vì từng claim | `EntityLinker.preview(content=...)` nhận toàn bộ nội dung | Một bài có nhiều claim dễ bị ép vào cùng điều khoản |
| P1 | Chưa có `Misconception` thật | Alert chỉ nhóm theo `chu_de + khoan_id` | Các cách diễn đạt khác nhau của cùng hiểu nhầm không được gom |
| P1 | Chưa có temporal verdict | NLI chỉ có `khop/mau_thuan/khong_ro` | Không phân biệt “sai từ đầu” với “từng đúng nhưng đã lỗi thời” |
| P2 | Severity chỉ dựa vào volume | `_severity(volume)` | Một bài báo có độ phủ lớn nhưng volume=1 sẽ không được cảnh báo |
| P2 | “Issue cluster” trên UI chỉ nhóm theo query/video title | `SocialInsightsPanel.tsx:123` | Biểu đồ chưa phản ánh cụm hiểu nhầm ngữ nghĩa |
| P2 | Alert UI mong `legal_evidence`, nhưng contract signal chưa bắt buộc trường này | `Alerts.tsx` đọc `signal.legal_evidence` | Card thường không hiện được căn cứ pháp lý |
| P2 | Bộ lọc `status` của posts chưa được áp dụng trong query | `SocialAlertFacade.list_posts()` nhận nhưng không dùng `status` | UI và API có hành vi không nhất quán |

## 3. Các quyết định kiến trúc

### ADR-NEWS-001 — Dùng hợp đồng nguồn chung

Tạo model trung lập với nền tảng:

```python
class ContentItem:
    content_id: str
    source_type: Literal["news", "social_post", "video", "comment", "forum"]
    provider: str
    source_domain: str | None
    external_id: str
    canonical_url: str

    title: str | None
    body: str
    author_hash: str | None
    published_at: datetime
    updated_at: datetime | None
    collected_at: datetime

    content_hash: str
    language: str
    engagement: dict
    raw_artifact_uri: str | None
    source_metadata: dict
```

Migration ít rủi ro:

- Giữ node `BaiDang` trong giai đoạn chuyển tiếp.
- Thêm label `NoiDungNguon` vào cùng node.
- Thêm `source_type`, `provider`, `source_domain`, `canonical_url`, `content_hash`.
- Code mới chỉ phụ thuộc `ContentItem`; adapter cũ chuyển `SocialPost → ContentItem`.
- Khi frontend và query đã chuyển hết, `BaiDang` trở thành compatibility label.

### ADR-NEWS-002 — Claim occurrence khác misconception

Một câu trong một bài báo chỉ là một lần xuất hiện của claim. Một misconception là cụm ngữ nghĩa có thể xuất hiện trong nhiều bài và nhiều nền tảng.

```text
(NoiDungNguon)-[:CHUA_CLAIM]->(YKien)
(YKien)-[:INSTANCE_OF]->(Misconception)
(YKien)-[:DOI_CHIEU]->(LegalProvision)
(Misconception)-[:CONTRADICTS]->(LegalProvision)
(Misconception)-[:BASED_ON_OUTDATED_VERSION]->(LegalProvision)
(AlertMeta)-[:CANH_BAO_VE]->(Misconception)
(AlertMeta)-[:BAO_GOM_TIN_HIEU]->(YKien)
```

Trong đó:

- `YKien` được dùng như `ClaimOccurrence` để giảm chi phí migration.
- `Misconception.canonical_claim` là diễn đạt chuẩn của cụm.
- Không cluster trực tiếp bằng topic hoặc điều khoản; hai claim cùng nói về một điều khoản vẫn có thể mang hai ý nghĩa khác nhau.

### ADR-NEWS-003 — Kiểm tra từng claim, không kiểm tra toàn bài

Pipeline đúng:

```text
Article
  → sentence/span extraction
  → checkable claims
  → retrieve legal candidates cho từng claim
  → temporal filter
  → rerank
  → NLI từng claim × provision
```

Mỗi claim bắt buộc giữ:

- `claim_text`
- `evidence_span`
- offsets trong source body
- URL và content checksum
- `provision_id`
- nguyên văn căn cứ pháp lý
- ngày hiệu lực và ngày được dùng để đối chiếu
- model/version và confidence

Nếu không tìm được căn cứ pháp lý đủ mạnh, verdict phải là `UNVERIFIABLE`; không được tự nâng thành cảnh báo sai lệch.

### ADR-NEWS-004 — Verdict có temporal awareness

Contract nghiệp vụ mới:

```text
SUPPORTED
CONTRADICTED
PARTIALLY_INCORRECT
OUTDATED_BUT_PREVIOUSLY_TRUE
UNVERIFIABLE
NEEDS_REVIEW
```

Compatibility mapping:

```text
SUPPORTED                     → khop
CONTRADICTED                  → mau_thuan
PARTIALLY_INCORRECT           → mau_thuan + needs_review
OUTDATED_BUT_PREVIOUSLY_TRUE  → mau_thuan + temporal_reason
UNVERIFIABLE                  → khong_ro
NEEDS_REVIEW                  → khong_ro + needs_review
```

Đối với mỗi bài:

1. Kiểm tra nội dung theo luật có hiệu lực tại `published_at`.
2. Kiểm tra lại theo luật hiện hành.
3. Nếu claim từng được căn cứ cũ hỗ trợ nhưng hiện không còn đúng, gắn `OUTDATED_BUT_PREVIOUSLY_TRUE`.
4. Hiển thị cả căn cứ cũ, căn cứ hiện hành và ngày chuyển đổi.

Phần này phụ thuộc `TemporalLawService` trong kế hoạch lõi LAWGIC.

### ADR-NEWS-005 — Hai cơ chế phát cảnh báo

Không thể dùng chung một ngưỡng volume cho mọi nguồn.

#### Single-source critical

Một bài báo đơn lẻ được phép sinh alert khi:

```text
contradiction_confidence >= 0.90
legal_impact >= 0.80
source_reach >= 0.70
provenance_status = complete
```

Alert vẫn phải mang nhãn “tín hiệu cần xác minh”.

#### Cluster trending

Sinh alert khi:

```text
independent_source_count >= 2
OR unique_occurrence_count >= configured_threshold
```

Các bản đăng lại/syndication từ cùng một bài gốc chỉ được tính một nguồn độc lập.

### ADR-NEWS-006 — Postgres giữ workflow, Neo4j giữ quan hệ

- PostgreSQL: source configs, crawl runs, alert snapshot, trạng thái triage, audit, assignment và SLA.
- Neo4j: content → claim → misconception → legal provision → version history.
- MinIO: HTML/JSON/raw snapshot để kiểm chứng provenance.
- Qdrant: candidate retrieval và semantic cluster; không phải nguồn citation.

Không ghi toàn bộ HTML lớn vào Neo4j.

## 4. News collector framework

### 4.1. Interface

```python
class ContentCollector(Protocol):
    provider: str
    source_type: str

    async def collect(
        self,
        topics: list[str],
        *,
        since: datetime,
        limit: int,
    ) -> list[RawContentItem]: ...
```

Mỗi adapter chịu trách nhiệm:

- Lấy listing từ RSS/API/sitemap trước; HTML scraping chỉ là fallback.
- Chuẩn hóa canonical URL.
- Lấy title, lead, body, published/updated time.
- Không trộn navigation, quảng cáo, related articles vào body.
- Ghi source attribution và raw snapshot.
- Tuân thủ rate limit, robots/điều khoản nguồn và chính sách lưu trữ.

### 4.2. Source registry

Tạo bảng `source_configs`:

```text
id
provider
source_type
base_url
adapter
enabled
trust_tier
reach_tier
crawl_interval
rate_limit
retention_days
config_json
last_success_at
last_error
```

`trust_tier` không được dùng để quyết định claim đúng hay sai. Nó chỉ phục vụ ưu tiên review và đánh giá độ lan truyền.

### 4.3. Deduplication

Áp dụng ba lớp:

1. Exact URL: canonical URL.
2. Exact content: SHA-256 của normalized title + body.
3. Near duplicate: SimHash/embedding similarity.

Lưu:

```text
duplicate_of
syndicated_from
duplicate_confidence
```

Volume cảnh báo dùng `unique_occurrence_count` và `independent_source_count`, không dùng tổng số URL thô.

## 5. Alert scoring

Đề xuất score ban đầu:

```python
risk_score = (
    0.25 * legal_impact
    + 0.20 * source_reach
    + 0.15 * contradiction_confidence
    + 0.15 * velocity
    + 0.10 * source_diversity
    + 0.10 * recent_law_change
    + 0.05 * engagement
)
```

Giảm điểm khi:

- Provenance thiếu.
- Legal linking có confidence thấp.
- Nội dung là bản sao/syndication.
- Claim chỉ nằm trong trích dẫn của người khác nhưng bị gán nhầm cho tác giả bài.

Severity:

```text
critical  >= 0.85
high      >= 0.70
medium    >= 0.50
low       <  0.50
```

Mỗi alert phải trả cả `risk_factors`, ví dụ:

```json
{
  "risk_score": 0.82,
  "risk_factors": [
    {"code": "HIGH_LEGAL_IMPACT", "score": 0.90},
    {"code": "RECENT_RULE_CHANGE", "score": 1.00},
    {"code": "HIGH_REACH_SOURCE", "score": 0.75},
    {"code": "STRONG_CONTRADICTION", "score": 0.93}
  ]
}
```

## 6. API và UI

### 6.1. API mới

```text
GET  /admin/monitor/sources
POST /admin/monitor/sources
POST /admin/monitor/runs
GET  /admin/monitor/runs/{id}

GET  /admin/content-items
GET  /admin/content-items/{id}
GET  /admin/claims
GET  /admin/misconceptions
GET  /admin/misconceptions/{id}

GET   /admin/alerts
GET   /admin/alerts/{id}
PATCH /admin/alerts/{id}
```

Giữ các route `/admin/social/*` làm alias trong một release để frontend cũ tiếp tục hoạt động.

### 6.2. Admin navigation

Đổi:

```text
Radar Mạng xã hội
```

thành:

```text
Radar thông tin
```

Các tab:

```text
Tổng quan
Nguồn báo
Bài đã thu thập
Claim cần xác minh
Cụm hiểu nhầm
Cảnh báo
Nguồn & lịch chạy
```

Khi mở rộng social:

```text
Nguồn báo | Mạng xã hội | Video/Bình luận | Diễn đàn
```

không cần thay page hoặc API contract.

### 6.3. Alert detail

Màn hình chi tiết phải có:

- Canonical claim của misconception.
- Verdict và confidence.
- Exact evidence span trong bài.
- Danh sách nguồn độc lập và bản đăng lại.
- Căn cứ Điều/Khoản/Điểm nguyên văn.
- Hiệu lực tại ngày đăng và hiệu lực hiện tại.
- Risk score có giải thích.
- Timeline volume/velocity.
- Audit của model và reviewer.

Hành động:

```text
Xác minh
Đánh dấu bản trùng
Sửa liên kết pháp lý
Gắn “thông tin lỗi thời”
Tạo bản đính chính
Bỏ qua có lý do
Đóng cảnh báo
```

### 6.4. Citizen Portal

Citizen Portal chỉ nhận:

- Bài giải thích đã `published`.
- Bản đính chính đã qua Publish Gate.
- Citation hợp lệ và temporal status rõ ràng.

Không trả:

- Tên tác giả/tài khoản chưa cần thiết.
- Raw alert chưa review.
- Điểm “uy tín” của tờ báo.
- Kết luận “tin giả” chỉ từ NLI tự động.

## 7. Lộ trình triển khai

### Phase N0 — Khép kín pipeline hiện tại

**Mục tiêu:** Một fixture article phải đi trọn đường tới alert.

1. Sửa `_chain_social_review()` thành orchestration trung lập `review_content_item()`.
2. Link từng claim thay vì link toàn bài.
3. Fetch legal provision text từ Neo4j bằng canonical ID.
4. Chạy claim check/NLI.
5. Gọi `save_nli()` cho từng result.
6. Query các eligible signals trong time window từ database.
7. Sửa dedupe/cooldown theo `dedupe_key` thật.
8. Gắn `legal_evidence` đầy đủ vào signal.
9. Thêm integration test content → claim → NLI → alert.

### Phase N1 — Đưa `phapluat.gov.vn` vào monitor

1. Tách collector ra khỏi `PhapLuatNewsService`.
2. Giữ `sync_briefs()` nhưng cho nó dùng chung collector.
3. Chuyển mỗi `NewsItem` thành `ContentItem(source_type="news")`.
4. Lưu raw snapshot và checksum.
5. Chạy `review_content_item()`.
6. Thêm filter `source_type=news` trên Admin.
7. Bật feature flag `NEWS_MISCONCEPTION_MONITOR_ENABLED`.

### Phase N2 — Misconception cluster và risk

1. Tạo `Misconception`.
2. Cluster claim bằng lexical + embedding + cùng legal target.
3. Thêm independent-source dedupe.
4. Thêm risk score và velocity snapshot.
5. Thêm single-source critical trigger.
6. Thay graph UI “query/video title” bằng misconception thật.

### Phase N3 — Mở rộng các báo khác

1. Source registry.
2. RSS/API/sitemap adapters.
3. Per-source parsing tests.
4. Health, retry, rate limit và circuit breaker.
5. Dashboard coverage theo nguồn.

Mỗi nguồn mới chỉ cần thêm adapter và config, không sửa domain pipeline.

### Phase N4 — Mở rộng mạng xã hội

1. Map Facebook/YouTube/forum collectors hiện có vào `ContentItem`.
2. Thêm `engagement` và velocity theo nền tảng.
3. Thêm TikTok adapter khi có API/quyền truy cập hợp lệ.
4. Thêm retention và pseudonym policy theo source type.
5. Chạy canary từng nguồn.

## 8. Acceptance tests

| ID | Kịch bản | Kết quả bắt buộc |
|---|---|---|
| N01 | Bài báo có claim mâu thuẫn và citation đầy đủ | Tạo `YKien`, `DOI_CHIEU`, cluster và alert |
| N02 | Không tìm được legal provision | `UNVERIFIABLE`, không tạo alert sai lệch |
| N03 | Claim không nằm nguyên văn trong source | Bị loại hoặc `NEEDS_REVIEW` |
| N04 | Một bài có ba claim về ba quy định | Link và NLI độc lập từng claim |
| N05 | Ba URL là bản đăng lại cùng bài | `independent_source_count = 1` |
| N06 | Một bài reach cao, impact cao, contradiction ≥ 0.90 | Kích hoạt single-source critical |
| N07 | Claim từng đúng theo luật cũ | `OUTDATED_BUT_PREVIOUSLY_TRUE` |
| N08 | Bài đăng trước ngày luật mới có hiệu lực | Không đánh giá bằng luật tương lai |
| N09 | Citation node không tồn tại/hết hiệu lực | Fail closed |
| N10 | Chạy monitor lặp trong cooldown | Không tạo alert trùng |
| N11 | Alert thiếu provenance | Không hiển thị như cảnh báo hoàn chỉnh |
| N12 | Raw alert chưa review | Citizen API không trả |
| N13 | Adapter một nguồn bị lỗi | Nguồn khác vẫn chạy; run báo `partial` |
| N14 | Social adapter được bật sau | Không cần thay contract alert/UI |

## 9. Metrics trước khi bật production

```text
Claim span exactness                         >= 95%
Legal linker Recall@5                       >= 85%
Citation node/effective-date validity        = 100%
Contradiction precision trên gold news set  >= 90%
Duplicate/syndication precision             >= 95%
Outdated verdict F1                         >= 80%
Unsupported alert rate                       = 0%
Alert provenance completeness                = 100%
P95 một article end-to-end                  <= 120 giây
```

Gold set news đầu tiên nên có tối thiểu:

- 50 bài không có claim pháp lý kiểm chứng được.
- 50 claim đúng.
- 50 claim mâu thuẫn.
- 30 claim đúng một phần.
- 30 claim từng đúng nhưng lỗi thời.
- 30 cặp bài đăng lại/syndication.

## 10. Thứ tự PR đề xuất

```text
PR-N0.1  ContentItem contract + compatibility adapter
PR-N0.2  Closed-loop orchestration + provision fetch
PR-N0.3  Persist NLI + DB window aggregation + dedupe fix
PR-N0.4  End-to-end alert provenance test

PR-N1.1  PhapLuatNewsCollector extraction
PR-N1.2  News ingest + raw snapshot + feature flag
PR-N1.3  News filters and alert detail UI

PR-N2.1  Misconception graph/schema
PR-N2.2  Semantic clustering + independent-source dedupe
PR-N2.3  Explainable risk + single-source critical
PR-N2.4  Radar thông tin UI
```

Điểm bắt đầu đúng là `PR-N0.2` và `PR-N0.3`: nếu chưa khép kín claim/NLI/persistence/aggregation thì thêm nhiều báo chỉ làm tăng số bài thu thập, không tăng số cảnh báo có thể tin cậy.
