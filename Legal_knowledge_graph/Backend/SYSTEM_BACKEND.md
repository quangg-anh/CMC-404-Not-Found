# Backend — Tư Duy Hệ Thống & Logic Xây Dựng

> Nguồn chân lý: `base_core.md`  
> Phân công 3 BE: `TEAM_ASSIGNMENT.md` · `ROLE_BE1_LEGAL_PIPELINE.md` · `ROLE_BE2_SOCIAL_INTEL.md` · `ROLE_BE3_API_QA_SERVICES.md`  
> Data contract: `Data/SYSTEM_DATA.md`  
> Vai trò: **một lõi backend** phục vụ **hai phân hệ** — Admin (CQNN) và Citizen (người dân)  
> Nguyên tắc: citation-first, không hallucination, misinfo = mức đối chiếu (không phán tuyệt đối), Citizen chỉ đọc dữ liệu đã `published`

---

## 1. Mục tiêu backend (bất biến)

1. **Traceability** — mọi Q&A và mọi tin tóm tắt phải trỏ được về `Dieu/Khoan/Diem` nguyên văn.
2. **Version awareness** — mọi quy định biết VB gốc và quan hệ `thay_the/sua_doi`.
3. **Cross-domain linking** — bài MXH chỉ gắn quy định qua topic → candidate → re-rank.
4. **Risk-bounded labeling** — chỉ `khop | mau_thuan | khong_ro`, kèm confidence.
5. **Portal isolation** — Admin ghi/duyệt; Citizen chỉ API read trên tài nguyên `published`.
6. **Human publish gate** — `BaiTomTat` và bản đính chính dùng ra ngoài phải qua duyệt Admin.

---

## 2. Hai mặt API trên một lõi

```
┌─────────────────────────────────────────────────────────────┐
│  API Gateway / FastAPI                                       │
│  Auth (RBAC) · Rate limit · Envelope · Tenant/org (optional) │
├──────────────────────┬──────────────────────────────────────┤
│  /admin/*            │  /citizen/*  (hoặc scope read public) │
│  ingest, jobs,       │  news published, QA citizen,          │
│  diff, graph, mxh,   │  van-ban công khai (subset)           │
│  alerts, suggest,    │                                       │
│  publish, review     │                                       │
├──────────────────────┴──────────────────────────────────────┤
│  Application Services                                        │
│  QA · Diff · Link · Alert · GraphQuery                       │
│  ContentBrief · ResponseSuggest · PublishGate                │
├─────────────────────────────────────────────────────────────┤
│  Domain Pipelines                                            │
│  LegalIngest · Parse · Extract · VersionDiff                 │
│  SocialIngest · Topic · EntityLink · ClaimCheck              │
│  BriefGenerate · SuggestGenerate                             │
├─────────────────────────────────────────────────────────────┤
│  Intelligence · Persistence                                  │
│  Embedding · LLM Router (9R-Shield) · NLI · Rerank · Cache   │
│  Neo4j · Vector · Postgres · Redis · Object store            │
└─────────────────────────────────────────────────────────────┘
```

**Quy tắc:** pipeline không gọi UI; LLM chỉ qua router; Citizen route không trả BaiDang thô / alert nội bộ / bản `draft`.

### 2.1 Vai trò (RBAC)

| Role | Quyền chính |
|---|---|
| `admin_phap_che` | ingest luật, xem/sửa review parse-extract, diff, graph, QA nội bộ |
| `admin_truyen_thong` | MXH, alerts, đề xuất đính chính, duyệt/xuất bản tin tóm tắt |
| `admin_ops` | jobs, lineage, config nguồn, evaluation |
| `citizen` | đọc news `published`, QA citizen, xem VB/Khoản công khai |
| `anonymous` (optional) | subset citizen read-only nếu chính sách cho phép |

---

## 3. Ontology vận hành

### 3.1 Node

| Node | Khóa chính gợi ý | Thuộc tính tối thiểu |
|---|---|---|
| `VanBanPhapLuat` | `so_hieu` + `ngay_ban_hanh` | ten, loai_vb, co_quan, ngay_hieu_luc, trang_thai, `visibility`, `file_ids[]` (PDF/DOCX gốc) |
| `Dieu` / `Khoan` / `Diem` | phân cấp theo VB | noi_dung, embedding_id (Khoản) |
| `ChuThe`, `NghiaVu`, `QuyenLoi`, `HanhViCam`, `ThoiHan`, `CheTai` | uuid | mo_ta, nguon_khoan_id |
| `BaiDang` | platform + external_id | noi_dung, tac_gia_hash, url, thoi_gian |
| `ChuDe` | slug | ten, embedding |
| `YKien` | bai_dang_id + claim_hash | claim_text, stance, confidence |
| `AlertMeta` | uuid | chu_de, khoan_ids[], severity, volume, `status: open\|triaged\|closed`, created_at |
| `BaiTomTat` | uuid | tieu_de, noi_dung_binh_dan, media_type (`text\|image\|audio\|video`), `status: draft\|review\|published\|archived`, citations[] |
| `DeXuatDinhChinh` | uuid | draft_text, alert_ids[], khoan_ids[], `status: draft\|ready\|exported`, created_by |
| `VanBanFile` | uuid | van_ban_id, filename, mime, storage_key, checksum |

### 3.2 Relation

```
VanBanPhapLuat -[:CO_DIEU]-> Dieu
Dieu -[:CO_KHOAN]-> Khoan
Khoan -[:CO_DIEM]-> Diem
Khoan -[:QUY_DINH]-> NghiaVu|QuyenLoi|HanhViCam|ThoiHan|CheTai
* -[:AP_DUNG_CHO]-> ChuThe
VanBanPhapLuat -[:THAY_THE|SUA_DOI]-> VanBanPhapLuat
BaiDang -[:THAO_LUAN_VE]-> ChuDe
ChuDe -[:LIEN_QUAN]-> Khoan|Dieu|VanBanPhapLuat
BaiDang -[:GAN_CO_CAN_KIEM_CHUNG {score, method}]-> Khoan
YKien -[:DOI_CHIEU {label: khop|mau_thuan|khong_ro, score}]-> Khoan
BaiTomTat -[:TOM_TAT_TU]-> Khoan|Dieu|VanBanPhapLuat
DeXuatDinhChinh -[:DE_XUAT_CHO]-> AlertMeta|YKien
DeXuatDinhChinh -[:CAN_CU]-> Khoan
VanBanPhapLuat -[:CO_FILE]-> VanBanFile
BaiTomTat -[:PUBLISHED_AS {at, by}]-> (audit Postgres cũng lưu)
```

**Invariant:** không cạnh `BaiDang → Khoan` dưới threshold / chưa qua `ChuDe` (MVP).  
**Invariant publish:** Citizen chỉ thấy `BaiTomTat.status=published` và VB `visibility=public`.

---

## 4. Luồng dữ liệu

### 4.1 Legal pipeline (Admin — module 1, 2, 4)

```
PDF/HTML → ObjectStore → Parser Điều–Khoản–Điểm
  → NER/RE schema-locked → VersionDiff
  → Neo4j + Vector → Postgres lineage
  → (optional) ContentBrief draft từ Khoản mới / diff nổi bật
```

### 4.2 Social pipeline (Admin — module 3, 5, 6)

```
MXH ingest (ToS) → normalize → Topic → Link Khoản → Claim NLI
  → label khop|mau_thuan|khong_ro
  → Alert nếu mau_thuan + confidence cao + volume
  → ResponseSuggest draft (không tự đăng)
```

### 4.3 QA pipeline (module 7 — cả hai phân hệ)

```
Câu hỏi → semantic cache → hybrid retrieve (vector + graph)
  → LLM + citation validator (quote ∈ nguồn)
  → fail-closed nếu thiếu evidence
```

Khác biệt Admin vs Citizen (cùng engine, khác policy):

| | Admin QA | Citizen QA |
|---|---|---|
| Context | có thể gồm bản nháp / nội bộ nếu role cho phép | chỉ Khoản/VB `public` + tin đã publish làm gợi ý |
| Rate limit | cao hơn, có audit | chặt hơn, chống abuse |
| Wording | kỹ thuật hơn được phép | ưu tiên ngôn ngữ dễ hiểu, vẫn kèm citation |

### 4.4 Content brief + publish (module 9a)

```
Trigger: VB mới indexed / diff quan trọng / Admin chủ động
  → BriefGenerate từ Khoản đã extract (schema: title, bullets, citations)
  → Citation validator (giống QA)
  → status=draft → Admin review → published
  → Citizen News API đọc published
```

### 4.5 Response suggestion (module 9b)

```
Alert cluster (cùng ChuDe + cùng Khoản + mau_thuan)
  → SuggestGenerate: điểm hiểu lầm, căn cứ Khoản, draft đính chính/hướng dẫn
  → Admin chỉnh sửa → export (copy) — hệ thống không auto-post MXH
```

### 4.6 Graph query (module 8)

```
Node seed (VB|Khoản|ChuThe|ChuDe) → Cypher neighborhood có giới hạn depth
  → trả nodes/edges thật từ Neo4j (không LLM sinh cạnh)
```

---

## 5. Module kỹ thuật & trách nhiệm

| Module | Input | Output | Fail mode |
|---|---|---|---|
| `legal_crawler` | URL/danh mục VB | raw + checksum | retry + DLQ |
| `legal_parser` | raw text | tree Điều–Khoản–Điểm | fallback LLM, `needs_review` |
| `legal_extractor` | Khoản | entities + relations JSON | `extract_error` |
| `version_diff` | cặp VB/Khoản | diff cấu trúc | partial + manual queue |
| `social_ingest` | API payload | BaiDang | drop thiếu id/time |
| `topic_classifier` | BaiDang | ChuDe + score | `unknown` |
| `entity_linker` | BaiDang + ChuDe | link Khoản | không link dưới threshold |
| `claim_checker` | claim + Khoản | khop/mau_thuan/khong_ro | mặc định `khong_ro` |
| `qa_engine` | question + audience | answer + citations | refuse |
| `graph_query` | seed + depth | subgraph | empty neighborhood |
| `content_brief` | Khoản/VB/diff | BaiTomTat draft + citations | draft invalid → review |
| `response_suggest` | alert cluster | DeXuatDinhChinh draft | không đủ căn cứ → không tạo |
| `publish_gate` | resource + actor | status transition + audit | reject nếu thiếu citation |
| `job_orchestrator` | events | pipeline status | idempotent retry |

---

## 6. API contract

Envelope:

```json
{
  "ok": true,
  "data": {},
  "meta": { "request_id": "...", "latency_ms": 0 },
  "warnings": []
}
```

### 6.1 Admin — lõi (MVP)

| Method | Path | Mục đích |
|---|---|---|
| `POST` | `/admin/ingest/legal` | đẩy VB (+ file) vào pipeline |
| `GET` | `/admin/legal/van-ban` | danh sách VB (filter status/visibility) |
| `GET` | `/admin/legal/van-ban/{id}` | cây Điều/Khoản + entities + `file_ids` |
| `GET` | `/admin/legal/van-ban/{id}/files` | danh sách file đính kèm VB |
| `GET` | `/admin/legal/files/{file_id}` | metadata / download URL file gốc |
| `GET` | `/admin/legal/khoan/{id}` | chi tiết Khoản |
| `POST` | `/admin/legal/diff` | so sánh VB/Khoản |
| `POST` | `/admin/qa/ask` | QA nội bộ (`audience=admin`, có `graph_paths`) |
| `GET` | `/admin/jobs` | danh sách job + summary sức khỏe pipeline |
| `GET` | `/admin/jobs/{id}` | chi tiết / stepper một job |
| `GET` | `/admin/graph/neighborhood` | subgraph theo seed |
| `GET` | `/admin/dashboard/summary` | alert count + job health cho Command Center |

### 6.2 Admin — mở rộng MXH & truyền thông

| Method | Path | Mục đích |
|---|---|---|
| `POST` | `/admin/ingest/social` | nhận bài / webhook |
| `GET` | `/admin/social/topics` | chủ đề + volume |
| `GET` | `/admin/social/posts` | lọc bài + nhãn đối chiếu |
| `POST` | `/admin/link/preview` | dry-run link bài↔Khoản (dùng trong MXH drawer) |
| `GET` | `/admin/alerts` | hàng đợi cảnh báo |
| `GET` | `/admin/alerts/{id}` | chi tiết một alert |
| `PATCH` | `/admin/alerts/{id}` | triage (`open\|triaged\|closed`) |
| `POST` | `/admin/briefs/generate` | sinh tin tóm tắt draft |
| `GET` | `/admin/briefs` | list theo `status` (kể cả `archived`) |
| `GET` | `/admin/briefs/{id}` | chi tiết brief để edit |
| `PATCH` | `/admin/briefs/{id}` | cập nhật nội dung / media_type / citations |
| `POST` | `/admin/briefs/{id}/publish` | PublishGate → `published` |
| `POST` | `/admin/briefs/{id}/archive` | chuyển `archived` |
| `POST` | `/admin/suggestions/generate` | gợi ý đính chính từ alert cluster |
| `GET` | `/admin/suggestions` | danh sách đề xuất |
| `GET` | `/admin/suggestions/{id}` | chi tiết + evidence Khoản |
| `PATCH` | `/admin/suggestions/{id}` | chỉnh draft / đánh dấu `ready\|exported` |
| `GET` | `/admin/review` | hàng đợi needs_review |

### 6.3 Citizen (read / QA)

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/citizen/news` | tin `published` (phân trang; có `media_type`) |
| `GET` | `/citizen/news/{id}` | chi tiết + citations |
| `POST` | `/citizen/qa/ask` | chatbot có citation (`audience=citizen`, có `graph_paths`) |
| `GET` | `/citizen/legal/van-ban` | VB công khai (`visibility=public`) — tên, số hiệu, tóm tắt |
| `GET` | `/citizen/legal/van-ban/{id}` | cây VB public (đơn giản hóa) + danh sách file công khai |
| `GET` | `/citizen/legal/van-ban/{id}/files` | file điều luật đính kèm (public) |
| `GET` | `/citizen/legal/files/{file_id}` | download / signed URL file VB |
| `GET` | `/citizen/legal/khoan/{id}` | Khoản public + nguyên văn (+ brief liên quan nếu có) |

### 6.4 Response QA bắt buộc

```json
{
  "answer": "...",
  "citations": [
    {
      "khoan_id": "...",
      "quote": "nguyên văn khớp substring",
      "van_ban": "Số hiệu...",
      "dieu": "Điều x",
      "score": 0.91
    }
  ],
  "confidence": "high|medium|low",
  "graph_paths": ["Khoan→ChuThe", "VB→THAY_THE→VB"],
  "audience": "admin|citizen"
}
```

`citations` rỗng → refuse/partial.  
`BaiTomTat` trước `publish` cũng phải qua cùng citation validator.

### 6.5 Response suggestion (Admin)

```json
{
  "suggestion_id": "...",
  "misunderstanding_summary": "...",
  "evidence_khoan_ids": ["..."],
  "draft_correction": "...",
  "claim_labels": ["mau_thuan"],
  "status": "draft",
  "disclaimer": "Gợi ý nội bộ — cần kiểm chứng trước khi phát hành"
}
```

---

## 7. Stack & dịch vụ

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| API | FastAPI | async, schema, RBAC middleware |
| Queue | Redis + Arq/Celery | parse/extract/brief jobs |
| KG | Neo4j | quan hệ pháp lý + graph explorer |
| Vector | Qdrant hoặc pgvector | retrieve Khoản/bài |
| Meta DB | PostgreSQL | users, jobs, publish audit, briefs |
| Cache | Redis + GPTCache | QA lặp |
| LLM | Local Gemma + large qua 9R-Shield | chi phí/độ phức tạp |
| Embedding | `bge-m3` / vietnamese-sbert | tiếng Việt |
| Parse PDF | pdfplumber / PyMuPDF | VB hỗn hợp |

---

## 8. LLM Router (9R-Shield)

1. Parse lệch chuẩn nhẹ → local  
2. NER/RE phức tạp → large (schema-locked)  
3. Re-rank bài–Khoản → large  
4. QA / Brief / Suggest → large **chỉ** trên context đã retrieve  
5. Output JSON phải validate schema; fail → retry 1 lần hoặc review queue  

Brief & Suggest **không** được bịa số liệu phạt / đối tượng ngoài context Khoản.

---

## 9. Chất lượng & chống rủi ro

### 9.1 Anti-hallucination

- Prompt: chỉ dùng context cung cấp.
- Post-check citation substring.
- Graph chỉ từ Neo4j.
- Cache chỉ lưu output đã validate.

### 9.2 Misinfo ethics

- Label đóng: `khop | mau_thuan | khong_ro`.
- Không API field kiểu `is_fake=true` tuyệt đối.
- Suggest luôn kèm disclaimer nội bộ.

### 9.3 Portal & privacy

- Hash PII người đăng MXH.
- Citizen không access `/admin/*`.
- Tôn trọng ToS / rate limit nền tảng.

### 9.4 Observability

- Metrics: parse success, citation validity %, link precision@k, QA refuse rate, brief publish reject rate, alert→suggest latency.
- Audit: mọi publish, mọi ghi KG, mọi tạo suggest.

---

## 10. Lộ trình backend

### Phase A — Lõi

1. Legal ingest/parse/extract + diff + file đính kèm  
2. Neo4j + vector Khoản  
3. Admin QA + citation validator (+ `graph_paths`)  
4. Jobs list/detail + dashboard summary + RBAC  
5. Citizen QA skeleton (cùng engine, filter public) + list VB public  

### Phase B — Admin giám sát

1. Social ingest 1–2 chủ đề  
2. Link 2 tầng + claim labels + alerts CRUD  
3. Graph neighborhood API  
4. Review queue + link/preview  

### Phase C — Citizen hoàn chỉnh + truyền thông

1. ContentBrief CRUD + PublishGate + archive  
2. ResponseSuggest list/detail từ alert cluster  
3. Citizen News + VB public + download file  
4. Eval harness (QA/brief citation gold set)

---

## 11. Cấu trúc thư mục đề xuất

```
Backend/
  SYSTEM_BACKEND.md
  app/
    main.py
    api/
      admin/
      citizen/
    services/          # QA, Diff, Link, Alert, Graph, Brief, Suggest, Publish
    pipelines/
    domain/
    intelligence/
    db/
    workers/
    core/              # config, auth/rbac, logging
  tests/
  scripts/
```

---

## 12. Tiêu chí “backend đạt”

- Parse cây Điều–Khoản–Điểm đạt ngưỡng mẫu không cần review.
- Citation validity QA (và brief trước publish) ≥ ngưỡng cứng (ví dụ 95%).
- Không cạnh `BaiDang–Khoan` dưới threshold.
- Diff có dẫn chiếu hoặc giải thích similarity.
- Citizen không đọc được draft/alert/BaiDang thô.
- Mọi job replay được từ raw checksum (idempotent).

---

## 13. Quyết định then chốt

1. **Một backend, hai mặt API** — không nhân đôi pipeline.  
2. **Khoản = đơn vị retrieve/embed mặc định.**  
3. **QA & Brief fail-closed** trên citation.  
4. **Link MXH qua ChuDe trước.**  
5. **Misinfo = mức đối chiếu, không phải phán quyết.**  
6. **PublishGate bắt buộc** trước khi nội dung ra Citizen / đính chính ra ngoài.  
7. **Neo4j + nguyên văn = source of truth**; LLM không phải.
