# Kế hoạch thực thi lõi LAWGIC cho CMC — phiên bản 2

**Trạng thái:** Ready for implementation  
**Ngày cập nhật:** 2026-07-19  
**Phạm vi:** Phần lõi còn lại sau khi pipeline cảnh báo hiểu nhầm news-first đã được khép kín.  
**Đội hình giả định:** 3 Backend, 1 Frontend, 1 Database.

## 1. Tóm tắt quyết định

CMC giữ nguyên FastAPI, Neo4j, Qdrant, PostgreSQL, Redis, MinIO và cấu trúc modular monolith hiện tại. Không tách microservice mới trong đợt này.

Critical path:

```text
Contract + fixture
  → parser giữ Điểm
  → immutable provision writer
  → migration + dual-write
  → TemporalLawService
  → QA/citation v2
  → amendment review + commit
  → temporal misconception
  → evaluation + rollout
```

Phần cảnh báo news-first đã hoàn thành nền tảng kỹ thuật và có 96 test backend. Nó chỉ được nối với temporal verdict sau khi TemporalLawService và Citation Contract v2 sẵn sàng.

## 2. Baseline code đã xác nhận

| Khu vực | Code hiện tại | Khoảng hở cần xử lý |
|---|---|---|
| Parser | `parser.py` tạo `diem_list` | `pipeline.py::_build_tree()` bỏ `diem_list`; writer không ghi `Diem` |
| ID | Có `generate_diem_id()` | Chưa có ID vật lý cho từng phiên bản bất biến |
| Neo4j writer | Ghi `VanBanPhapLuat → Dieu → Khoan` | `SET noi_dung` ghi đè; chưa checksum, interval, lineage, conflict |
| Vector | Collection `khoan` | Chưa index leaf node Điều/Khoản/Điểm; payload còn chứa text được QA dùng trực tiếp |
| Time travel | `qa_service.py` lọc `THAY_THE` cấp văn bản | Sai với sửa đổi một Điểm/Khoản riêng lẻ |
| Citation | Exact substring và NLI heuristic | Contract chỉ có `khoan_id`; validator chấp nhận `preloaded_sources` thay vì luôn hydrate Neo4j |
| Diff | `version_diff.py` dùng `difflib` | Chưa pairing, impact classification, review queue hoặc graph commit |
| Misconception | `YKien`, alert và provenance đã có | Chưa cluster semantic và chưa có verdict lỗi thời |
| Evaluation | Gold citation/link/NLI nhỏ | Chưa có parser, temporal, amendment, exact-node, refusal benchmark |

## 3. Phạm vi và nguyên tắc

### Trong phạm vi

- Versioning bất biến cho `Dieu`, `Khoan`, `Diem`.
- Truy vấn pháp luật tại một ngày và lịch sử phiên bản.
- Retrieval node lá sâu nhất và Citation Contract v2.
- Amendment matching, review và commit có kiểm soát.
- Misconception temporal: từng đúng nhưng hiện lỗi thời.
- Gold set, acceptance test, CI gate và rollout bằng feature flag.

### Ngoài phạm vi đợt này

- Thay toàn bộ stack hoặc tách microservice.
- Full event sourcing/bitemporal database.
- Tự động hợp nhất mọi văn bản pháp luật Việt Nam không cần review.
- Bật quét báo/MXH production trước khi qua precision gate.
- Xóa collection, node hoặc API v1 trong cùng release.

### Invariants bắt buộc

1. Node đã công bố không được ghi đè nguyên văn.
2. Neo4j là nguồn canonical; Qdrant chỉ trả candidate ID.
3. Khoảng hiệu lực là nửa mở: `effective_from <= as_of < effective_to`.
4. Mọi temporal read đi qua `TemporalLawService`.
5. Citation dùng node lá sâu nhất có đủ nội dung để hỗ trợ claim.
6. Không có căn cứ hợp lệ thì Citizen QA phải từ chối.
7. Amendment không chắc chắn không được tự ghi temporal edge.
8. Migration additive, idempotent, có dry-run và rollback bằng read flag.

## 4. Data contract mục tiêu

Tạo `Backend/app/domain/legal_provision.py`:

```python
class LegalProvisionVersion(BaseModel):
    provision_id: str
    lineage_id: str
    parent_lineage_id: str | None
    level: Literal["dieu", "khoan", "diem"]
    version_no: int

    source_vb_id: str
    logical_vb_id: str
    article: str
    clause: str | None
    point: str | None

    text: str
    effective_from: date
    effective_to: date | None
    text_checksum: str
    source_checksum: str | None

    visibility: Literal["public", "internal"]
    recorded_at: datetime
    review_status: Literal["approved", "needs_review"]
```

### Quy tắc ID

- `lineage_id`: định danh logic ổn định, ví dụ `logical_doc::D5.K2.Pa`.
- `provision_id`: định danh phiên bản vật lý bất biến, ví dụ `lineage_id@2026-07-01#checksum12`.
- Node hiện có giữ nguyên `dieu_id/khoan_id/diem_id`; migration chỉ bổ sung `provision_id` và `lineage_id`, không đổi khóa cũ.
- Resolver v2 nhận `provision_id`, `lineage_id` hoặc ID v1 trong một release tương thích.
- Phiên bản mới dùng `provision_id` làm canonical ID; trường ID cấp cũ chỉ là alias deprecated.

### Label và quan hệ

Mỗi node version dùng hai label:

```text
(:LegalProvision:Dieu)
(:LegalProvision:Khoan)
(:LegalProvision:Diem)
```

Quan hệ:

```text
(old:LegalProvision)-[:SUPERSEDED_BY {
  effective_from,
  change_type,
  confidence,
  review_id,
  source_vb_id
}]->(new:LegalProvision)

(old:LegalProvision)-[:AMENDED_BY]->(amending:VanBanPhapLuat)
```

Giữ `CO_DIEU`, `CO_KHOAN`, `CO_DIEM`. Khi một Điểm thay đổi, không nhân bản cha không đổi; cả hai version có cùng `parent_lineage_id`, và TemporalLawService chọn version hợp lệ theo ngày.

## 5. Work breakdown theo phase

## Phase L0 — Contract, ontology và fixture khóa hành vi

**Thời lượng:** 2 ngày  
**Owner:** DB + BE1 + BE3  
**Phụ thuộc:** Không

| Task | Nội dung | File chính | Kết quả |
|---|---|---|---|
| L0.1 | Tạo domain model và enum | `Backend/app/domain/legal_provision.py`, `citation_contract.py` | Pydantic contract dùng chung |
| L0.2 | Nâng ontology 2.0 additive | `Data/schema/ontology.json` | Property, label, edge và invariant mới |
| L0.3 | Thêm constraint/index | `Data/schema/neo4j_constraints.cypher` | `provision_id`, `lineage_id`, interval indexes |
| L0.4 | Tạo temporal fixture | `Backend/tests/fixtures/temporal_legal.py` | V1/V2/V3, partial amendment, future, repeal |
| L0.5 | Viết acceptance catalog | `Data/schema/acceptance_queries.cypher` | Query T01–T20 cố định |
| L0.6 | Thêm feature flags config | `Backend/app/config.py`, `.env.example` | Write/read/strict/commit flags mặc định an toàn |

Fixture bắt buộc:

- V1 có Điểm a và b.
- V2 chỉ sửa Điểm a từ `2026-07-01`.
- V3 sửa tiếp Điểm a.
- Khoản không có Điểm.
- Điều không có Khoản.
- Node future-effective.
- Node repealed không có successor.
- Citation hợp lệ, citation giả và citation đúng node nhưng sai ngày.

**Exit gate L0**

- Contract validate được tất cả fixture.
- Expected active `provision_id` tại từng ngày được khóa trước khi viết service.
- Ontology, constraints và domain contract không mâu thuẫn.
- Feature flags mặc định không thay đổi hành vi v1.

## Phase L1 — Parser và immutable Neo4j writer

**Thời lượng:** 4–5 ngày  
**Owner:** BE1 + DB  
**Phụ thuộc:** L0

| Task | Nội dung | File chính |
|---|---|---|
| L1.1 | Giữ `diem_list` trong `_build_tree()` | `Backend/app/pipelines/legal/pipeline.py` |
| L1.2 | Sinh ID, lineage, parent lineage và checksum | `Backend/app/pipelines/legal/normalize.py` |
| L1.3 | Không tự biến Điều không Khoản thành Khoản thật | `Backend/app/pipelines/legal/parser.py` |
| L1.4 | Ghi đủ Điều/Khoản/Điểm trong một transaction | `Backend/app/adapters/neo4j_legal.py` |
| L1.5 | Chặn overwrite checksum khác | `neo4j_legal.py` |
| L1.6 | Trả report count/conflict theo từng cấp | ingest facade và worker legal |
| L1.7 | Unit + repository tests | `Backend/tests/test_legal_parser_v2.py`, `test_neo4j_legal_v2.py` |

Writer semantics:

```text
same provision_id + same checksum    → idempotent success
same provision_id + different text   → conflict, needs_review, no overwrite
same lineage + new approved version  → create node, close old interval, link edge
invalid interval                     → reject before transaction
```

Không đóng interval trong ingest bình thường. Chỉ amendment commit đã được approve mới được phép đóng node cũ.

**Exit gate L1**

- Parser → tree → writer giữ 100% Điều/Khoản/Điểm của fixture.
- Re-ingest hai lần không tăng node/edge.
- Conflict không làm thay đổi canonical text.
- Test chứng minh sửa Điểm a không làm mất Điểm b.

## Phase L2 — Migration và Qdrant dual-write

**Thời lượng:** 3–4 ngày  
**Owner:** DB + BE1 + BE2  
**Phụ thuộc:** L1

| Task | Nội dung | File chính |
|---|---|---|
| L2.1 | Tạo collection `legal_provision` | `Data/schema/qdrant/collections.json` |
| L2.2 | Index leaf node và metadata | `Backend/app/pipelines/legal/pipeline.py` |
| L2.3 | Tạo reindex script resumable | `Backend/scripts/reindex_legal_provisions.py` |
| L2.4 | Tạo migration dry-run/apply | `Backend/scripts/migrate_temporal_v2.py` |
| L2.5 | Báo raw source thiếu Điểm cần re-ingest | migration report |
| L2.6 | Shadow compare v1/v2 counts | `Backend/scripts/compare_legal_v1_v2.py` |

Qdrant payload v2 không chứa canonical quote:

```json
{
  "provision_id": "...",
  "lineage_id": "...",
  "level": "diem",
  "logical_vb_id": "...",
  "effective_from": "2026-07-01",
  "effective_to": null,
  "visibility": "public",
  "text_checksum": "...",
  "text_preview": "debug only"
}
```

Migration modes:

```text
--dry-run        chỉ report
--apply          backfill additive
--document ID    giới hạn một văn bản
--resume-from    tiếp tục batch lỗi
```

**Exit gate L2**

- Migration chạy lặp không tạo dữ liệu trùng.
- Có danh sách văn bản phải re-ingest từ MinIO/raw source.
- Qdrant v2 và Neo4j có cùng tập `provision_id` trên fixture.
- Tắt v2 read vẫn dùng được collection `khoan` cũ.

### L2 implementation status - 2026-07-19

The safe preparation slice is complete: collection contract, feature-flagged dual-index, read-only migration inventory, additive-only bootstrap, resumable checksum-aware reindex and Neo4j/Qdrant parity tooling. The graph migration `--apply` path is intentionally not implemented/executed yet because legacy documents with uncertain Point coverage must be reviewed from raw source first. Live/staging mutation remains behind snapshot and Go/No-Go 1.
## Phase L3 — TemporalLawService và API lịch sử

**Thời lượng:** 4–5 ngày  
**Owner:** BE3 + DB  
**Phụ thuộc:** L2

Tạo:

```text
Backend/app/adapters/neo4j_temporal.py
Backend/app/services/temporal_law_service.py
Backend/app/api/admin/temporal.py
Backend/app/api/citizen/temporal.py
```

Interface:

```python
law_as_of(as_of, *, logical_vb_id=None, lineage_ids=None, visibility="public")
get_provision(provision_id, *, as_of=None)
resolve_version(identifier, as_of)
timeline(identifier)
compare_versions(old_id, new_id)
hydrate_candidates(candidate_ids, *, as_of, audience)
```

Leaf selection:

1. Điểm hợp lệ nếu Khoản có Điểm tại `as_of`.
2. Khoản hợp lệ nếu không có Điểm hợp lệ tại `as_of`.
3. Điều hợp lệ nếu không có Khoản hợp lệ tại `as_of`.
4. Không trả đồng thời cha và con nếu claim chỉ cần node con.
5. Nếu claim cần preamble cha và hành vi ở Điểm, trả hai node rõ ràng.

API:

```text
GET /admin/legal/provisions/{id}/timeline
GET /admin/legal/documents/{id}/as-of?date=YYYY-MM-DD
GET /admin/legal/provisions/{old_id}/compare/{new_id}
GET /citizen/legal/provisions/{id}?as_of=YYYY-MM-DD
```

**Exit gate L3**

- `2026-06-30` trả V1; `2026-07-01` trả V2.
- Partial amendment chỉ đổi Điểm a.
- V1 → V2 → V3 đúng thứ tự và không cycle.
- Future/repealed không lọt sai ngày.
- Citizen không thấy node internal.

## Phase L4 — Retrieval và Citation Contract v2

**Thời lượng:** 5–6 ngày  
**Owner:** BE2 + BE3 + FE  
**Phụ thuộc:** L3

### L4A — Retrieval service

Tạo `Backend/app/services/legal_retrieval_service.py`:

```text
exact reference
  + lexical/full-text
  + Qdrant vector
  → reciprocal-rank fusion
  → graph expansion
  → TemporalLawService.hydrate_candidates()
  → rerank
```

Không khóa trọng số trước khi có benchmark. So sánh năm cấu hình:

```text
lexical
vector
lexical + vector
lexical + vector + graph
lexical + vector + graph + reranker
```

### L4B — Citation v2

Tạo `Backend/app/domain/citation_contract.py` và refactor:

- `Backend/app/services/citation_validator.py`
- `Backend/app/services/qa_service.py`
- `Backend/app/schemas.py`
- Citizen/Admin QA routes

Contract tối thiểu:

```json
{
  "status": "answered",
  "as_of": "2026-07-01",
  "answer": "...",
  "claims": [{
    "claim_id": "claim_1",
    "text": "...",
    "citation_ids": ["citation_1"],
    "support_status": "entailed"
  }],
  "citations": [{
    "citation_id": "citation_1",
    "node_id": "...",
    "lineage_id": "...",
    "level": "diem",
    "article": "5",
    "clause": "2",
    "point": "a",
    "quote": "...",
    "effective_from": "2026-07-01",
    "effective_to": null,
    "supports_claim_ids": ["claim_1"],
    "entailment_score": 0.94
  }]
}
```

Strict validation order:

1. Node tồn tại trong Neo4j.
2. Visibility hợp lệ.
3. Node hiệu lực tại `as_of`.
4. Checksum khớp.
5. Quote là substring canonical.
6. Citation đúng topic/claim.
7. NLI claim–citation là entailed.
8. Claim số tiền, thời hạn, tỷ lệ hoặc chế tài không supported → hard fail.

`preloaded_sources` không còn được coi là canonical. Candidate ID luôn phải hydrate lại từ Neo4j.

### L4B implementation status - 2026-07-20

PR-L4.2/L4.3 is complete in code: exact physical-node canonical validation, checksum/date/quote guards, per-edge NLI, material-claim coverage, strict refusal and three-flag QA dispatch are implemented. T11-T15 fixtures pass. No flags were enabled and production QA remains on v1 pending L4C and rollout gates.
### L4C — Frontend

Sửa:

```text
Frontend/packages/ui-legal/src/components/CitationCard.tsx
Frontend/packages/ui-legal/src/components/KhoanViewer.tsx
Frontend/apps/web/src/admin/features/qa/QAAdmin.tsx
Citizen QA components
```

Hiển thị Điểm, khoảng hiệu lực, `as_of`, timeline và trạng thái hỗ trợ claim. Giữ `khoan_id` alias một release nhưng UI mới dùng `node_id`.

### L4C implementation status - 2026-07-20

PR-L4.4 is complete in code. Citizen/Admin/floating chat normalize both QA contracts; CitationCard renders leaf coordinates, canonical validation, effective interval, `as_of` and claim support; an accessible shared dialog reads public/admin temporal timelines and compares adjacent versions. Three frontend contract tests, the production build, 66 focused backend tests and 219 full backend tests pass. All v2 flags remain off and production QA remains on v1 pending Go/No-Go 2.
**Exit gate L4**

- Fabricated node, wrong date, wrong quote và unsupported claim đều bị từ chối.
- Citizen không trả câu pháp lý `unverified`.
- 100% citation fixture được hydrate từ Neo4j.
- Frontend vẫn đọc được response v1 khi feature flag v2 tắt.

## Phase L5 — Amendment engine và Admin review

**Thời lượng:** 6–8 ngày  
**Owner:** BE1 + BE3 + DB + FE  
**Phụ thuộc:** L3; có thể song song cuối L4

Tạo:

```text
Backend/app/pipelines/legal/amendment_parser.py
Backend/app/pipelines/legal/amendment_matcher.py
Backend/app/pipelines/legal/change_classifier.py
Backend/app/services/amendment_commit_service.py
Data/schema/postgres/011_amendment_reviews.sql
Frontend/apps/web/src/admin/features/amendment-review/
```

Matching order:

1. Dẫn chiếu Điều/Khoản/Điểm tường minh.
2. Cùng số và tiêu đề trong văn bản logic.
3. Cùng vị trí + lexical/entity similarity.
4. Embedding + cross-reference overlap cho phần còn lại.
5. Không đoán khi nhiều target có điểm gần nhau.

Change type:

```text
UNCHANGED | REWORDED | TIGHTENED | LOOSENED
ADDED | REMOVED | SPLIT | MERGED | UNCERTAIN
```

Review thresholds ban đầu:

```text
>= 0.90 + không split/merge + pairing precision gate đạt  → eligible auto-approve
0.70–0.90                                              → human review
< 0.70 hoặc split/merge/uncertain                       → mandatory review
```

PostgreSQL lưu batch/candidate, score breakdown, old/new IDs, proposed interval, reviewer, audit. Neo4j chỉ được thay đổi qua `amendment_commit_service` sau approve.

Commit transaction:

1. Lock/re-read old version.
2. Kiểm tra checksum và interval chưa đổi.
3. Tạo new immutable node.
4. Set `old.effective_to = new.effective_from`.
5. Tạo `SUPERSEDED_BY` và `AMENDED_BY`.
6. Ghi audit/revision.
7. Idempotency key bảo đảm retry không tạo bản thứ hai.

### L5.1 implementation status - 2026-07-20

PR-L5.1 is complete in preview-only mode. Explicit Vietnamese targets and phrase replacements are parsed; immutable old/new candidate IDs are hydrated canonically from Neo4j; explainable one-to-one matching and conservative change classification are exposed through an Admin-only preview API. Every result has `commit_allowed=false` and `auto_approve_eligible=false`. Ambiguous structure, invalid dates, cross-document candidates and canonical phrase mismatches fail closed or require mandatory review. No review persistence, interval closure or graph edge write is included; those remain L5.2/L5.3.
**Exit gate L5**

- Auto-pair precision trên gold `>= 95%`; nếu chưa đạt, tắt auto-approve.
- Split/merge/uncertain không auto-commit.
- Commit lỗi không để graph ở trạng thái nửa chừng.
- UI cho phép sửa cặp, ngày và change type trước approve.

## Phase L6 — Temporal misconception và risk score

**Thời lượng:** 5–6 ngày  
**Owner:** BE2 + DB + FE  
**Phụ thuộc:** L3 + L4; dùng output L5 khi có

Tạo `Misconception` và quan hệ:

```text
(YKien)-[:INSTANCE_OF]->(Misconception)
(Misconception)-[:CONTRADICTS]->(LegalProvision hiện hành)
(Misconception)-[:BASED_ON_OUTDATED_VERSION]->(LegalProvision cũ)
(AlertMeta)-[:CANH_BAO_VE]->(Misconception)
```

Verdict:

```text
SUPPORTED
CONTRADICTED
PARTIALLY_INCORRECT
OUTDATED_BUT_PREVIOUSLY_TRUE
UNVERIFIABLE
NEEDS_REVIEW
```

Algorithm lỗi thời:

1. Đối chiếu claim với luật tại `published_at`.
2. Đối chiếu lại với luật tại thời điểm hiện tại.
3. Nếu bản cũ entailed và bản hiện hành contradicted → `OUTDATED_BUT_PREVIOUSLY_TRUE`.
4. Lưu cả old/new provision ID, interval và NLI evidence.
5. Nếu thiếu một trong hai căn cứ → `UNVERIFIABLE` hoặc `NEEDS_REVIEW`.

Risk score v2 lưu breakdown:

```text
legal_impact
source_reach
contradiction_confidence
velocity
source_diversity
recent_law_change
engagement
provenance_penalty
```

Phase này nối trực tiếp vào pipeline news-first đã có; không xây một orchestration thứ hai.

**Exit gate L6**

- Claim từng đúng tạo đủ old/new edge và verdict.
- Claim chưa từng có căn cứ không bị gắn `previously_true`.
- Alert giải thích được từng thành phần risk score.
- Raw alert chưa review không xuất hiện ở Citizen.

## Phase L7 — Evaluation, CI, rollout và demo

**Thời lượng:** 4–6 ngày; chuẩn bị gold song song từ L0  
**Owner:** Cả nhóm  
**Phụ thuộc:** L1–L6

Cấu trúc:

```text
eval/
  parser/
  retrieval/
  temporal/
  citation/
  amendment/
  misinformation/
  safety/
  reports/
```

Metrics và release gate:

| Module | Metric | Gate |
|---|---|---:|
| Parser | Recall Điều/Khoản/Điểm | >= 98% |
| Temporal | Exact active-node accuracy | 100% fixture; >= 95% gold |
| Citation | Node/date/quote validity | 100% |
| Retrieval | Recall@5 | >= 85% |
| QA | Citation exact-node accuracy | >= 85% |
| Faithfulness | Claim–citation entailment precision | >= 90% |
| Amendment | Auto-approved pairing precision | >= 95% |
| Outdated verdict | F1 | >= 80% |
| Safety | Fabricated/no-basis/injection refusal | 100% fixture |
| System | P95 QA | đo baseline, không regression >20% |

CI jobs:

```text
unit
neo4j-temporal-integration
postgres-amendment-integration
qdrant-shadow-read
frontend-build
acceptance-T01-T20
eval-smoke
schema-invariant-check
```

Ba demo khóa:

1. Cùng câu hỏi ngày `2026-06-30` và `2026-07-01` trả hai node khác nhau.
2. Bài báo dùng ngưỡng cũ được gắn `OUTDATED_BUT_PREVIOUSLY_TRUE` và chỉ ra hai phiên bản.
3. Câu hỏi không có căn cứ hoặc citation giả bị từ chối.

## 6. Acceptance catalog

| ID | Tình huống | Kết quả bắt buộc |
|---|---|---|
| T01 | Parser gặp Khoản có Điểm a/b | Giữ đủ hai Điểm và nguyên văn |
| T02 | Khoản có Điểm tại ngày hỏi | Chỉ trả Điểm hợp lệ |
| T03 | Khoản không có Điểm | Trả Khoản |
| T04 | Điều không có Khoản | Trả Điều |
| T05 | Chỉ Điểm a được sửa | Điểm b không đổi interval/version |
| T06 | V1 → V2 → V3 | Timeline đúng, không cycle |
| T07 | Future effective | Không xuất hiện sớm |
| T08 | Repealed | Không active sau `effective_to` |
| T09 | Re-ingest cùng checksum | Không nhân đôi |
| T10 | Cùng ID nhưng khác text | Conflict, không overwrite |
| T11 | Qdrant preview bị sửa | Citation vẫn dùng Neo4j |
| T12 | Node giả | Refuse |
| T13 | Node đúng nhưng sai ngày | Refuse |
| T14 | Quote không exact | Refuse |
| T15 | Quote đúng nhưng không support claim | Refuse claim/câu trả lời |
| T16 | Amendment confidence cao | Commit atomically khi gate đạt |
| T17 | Split/merge/uncertain | Review bắt buộc |
| T18 | Claim từng đúng | `OUTDATED_BUT_PREVIOUSLY_TRUE` |
| T19 | Claim chưa từng đúng | Không gắn previously true |
| T20 | Raw alert chưa review | Citizen không đọc được |

## 7. Feature flags và rollout

Flags cần thêm, mặc định:

```text
LEGAL_PROVISION_V2_WRITE=false
LEGAL_PROVISION_V2_READ=false
TEMPORAL_LAW_V2=false
QA_CITATION_V2=false
QA_STRICT_GROUNDING_V2=true
AMENDMENT_PREVIEW_V2=false
AMENDMENT_COMMIT_V2=false
MISCONCEPTION_TEMPORAL_V2=false
```

Rollout:

1. Snapshot Neo4j/PostgreSQL/Qdrant.
2. Apply schema additive.
3. Bật v2 write cho một tập văn bản canary.
4. Chạy migration dry-run và lưu report.
5. Re-ingest raw source để phục hồi Điểm bị mất.
6. Dual-write Qdrant v1/v2.
7. Shadow-read và so kết quả/latency.
8. Bật Temporal v2 cho Admin trước.
9. Bật Citation v2 cho Citizen khi gate đạt.
10. Bật amendment commit và misconception temporal riêng rẽ.
11. Giữ v1 ít nhất một release ổn định.

Rollback chỉ tắt read flags. Không xóa dữ liệu v2 hoặc thay đổi khóa cũ trong cùng release.

## 8. Lịch thực hiện với đội 5 người

| Tuần | DB | BE1 | BE2 | BE3 | FE |
|---|---|---|---|---|---|
| 1 | Ontology, index, fixture | Parser + immutable writer | Qdrant v2 prep | Contract + acceptance harness | Citation contract prep |
| 2 | Migration/report | Reindex + amendment parser | Retrieval baseline | Temporal service + API | Timeline/Citation skeleton |
| 3 | Review tables | Matcher/classifier | Hybrid retrieval + gold | QA Citation v2 | Citation v2 + timeline |
| 4 | Integration DB | Amendment commit | Temporal misconception/risk | Strict refusal + CI | Amendment review UI |
| 5 | Backup/canary | Error analysis | Eval tuning | Rollout/demo | Demo/accessibility |

Ước lượng: 30–40 person-days, khoảng 4–5 tuần với 5 người nếu raw legal source sẵn có. Thiếu raw source hoặc gold labeling sẽ kéo dài critical path.

## 9. Thứ tự PR đề xuất

```text
PR-L0.1  Domain contracts + ontology v2 + fixture
PR-L1.1  Parser preserves Điều/Khoản/Điểm
PR-L1.2  Immutable Neo4j writer + conflict guard
PR-L2.1  Qdrant legal_provision dual-write
PR-L2.2  Migration/reindex dry-run + reports
PR-L3.1  Temporal repository + law_as_of
PR-L3.2  Timeline/as-of APIs + QA temporal integration
PR-L4.1  Hybrid retrieval service + ablation harness
PR-L4.2  Citation Contract v2 + canonical validator
PR-L4.3  Claim-level entailment + strict refusal
PR-L4.4  Citation/timeline frontend
PR-L5.1  Amendment parser/matcher/classifier
PR-L5.2  Review persistence + APIs
PR-L5.3  Transactional commit + Admin UI
PR-L6.1  Misconception schema + clustering
PR-L6.2  Outdated verdict + explainable risk
PR-L7.1  Full evaluation + CI gates + demo fixtures
```

Mỗi PR phải tự pass test hiện hữu, không yêu cầu bật read v2, và có rollback bằng flag hoặc không thay đổi behavior v1.

## 10. Việc triển khai ngay tiếp theo

Lát cắt đầu tiên chỉ gồm `PR-L0.1` và `PR-L1.1`:

1. Tạo `LegalProvisionVersion` và `CitationContractV2`.
2. Nâng ontology/index theo hướng additive.
3. Tạo fixture partial amendment V1/V2/V3.
4. Sửa `_build_tree()` để giữ Điểm và checksum.
5. Viết test parser round-trip và deepest-leaf expected IDs.

Không sửa QA production hoặc chạy migration thật trong lát cắt này. Đây là điểm bắt đầu nhỏ nhất nhưng mở khóa toàn bộ temporal core.

## 11. Definition of Done toàn roadmap

Roadmap chỉ được đánh dấu hoàn thành khi:

- T01–T20 pass trên CI với Neo4j/PostgreSQL/Qdrant thật.
- Parser không làm mất Điểm.
- QA không còn temporal Cypher cấp văn bản riêng.
- Qdrant không thể trở thành canonical citation source.
- Citizen không trả legal answer thiếu citation v2 hợp lệ.
- Amendment commit có review, audit, idempotency và rollback.
- Misconception phân biệt được sai hiện tại với từng đúng trong quá khứ.
- Evaluation report công bố baseline, metric không đạt và error analysis.
- Ba demo khóa chạy end-to-end trên cùng fixture cố định.

## 12. Risk register và điểm Go/No-Go

| Rủi ro | Mức | Cách giảm thiểu | Gate chịu trách nhiệm |
|---|---|---|---|
| Raw source cũ thiếu Điểm | Cao | Migration chỉ report; re-ingest từ MinIO/raw; không dựng text bằng suy đoán | DB + BE1 trước L2 apply |
| Ngày hiệu lực thiếu hoặc mâu thuẫn | Cao | `needs_review`; không tạo active interval tự động | DB/pháp chế trước L3 read |
| Ghép sai amendment | Cao | Human review; auto-approve chỉ khi precision >=95% | BE1 + pháp chế trước L5 auto |
| Qdrant/Neo4j lệch revision | Cao | Shadow compare, checksum, canonical hydration | BE2 + DB trước L4 Citizen |
| Citation v2 làm tăng latency | Trung bình | Batch hydrate, cache theo revision, đo P95 | BE3 trước Citizen rollout |
| API v2 làm vỡ frontend cũ | Trung bình | Alias `khoan_id`, response adapter, feature flag | BE3 + FE trước L4 enable |
| Gold set không độc lập | Cao | Label thủ công, tách train/tune/test, lưu guideline | Cả nhóm trước công bố metric |
| Graph tăng kích thước | Trung bình | Interval/lineage index, retention chỉ cho cache không xóa history | DB theo dõi từ L2 |
| Social verdict bị hiểu là phán quyết | Cao | Giữ nhãn “cần xác minh”, human review, provenance đầy đủ | BE2 + FE trước L6 publish |

### Go/No-Go 1 — Cho phép migration apply

Chỉ Go khi snapshot thành công, dry-run không có ID collision chưa xử lý, raw-source coverage được báo cáo và script chạy idempotent trên staging.

### Go/No-Go 2 — Bật Temporal/Citation v2 cho Citizen

Chỉ Go khi T01–T15 pass, citation validity đạt 100% trên fixture, fabricated/no-basis refusal đạt 100%, và P95 không regression quá 20% so với baseline đã ghi.

### Go/No-Go 3 — Bật amendment auto-approve

Chỉ Go khi pairing precision độc lập đạt ít nhất 95%. Nếu không đạt, engine vẫn được release ở chế độ preview + human review, còn auto-approve giữ tắt.

### Go/No-Go 4 — Bật temporal misconception ra Citizen

Chỉ Go khi outdated-verdict F1 đạt mục tiêu, old/new citations đều hợp lệ, và Publish Gate bảo đảm raw alert chưa review không được công khai.
