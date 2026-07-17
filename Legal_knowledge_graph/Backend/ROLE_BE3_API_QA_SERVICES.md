# BE3 — API, QA & Orchestration (Người Backend 3/3)

> Phân công tổng: `TEAM_ASSIGNMENT.md`  
> Contract API: `Backend/SYSTEM_BACKEND.md` §6 · Map FE: `Frontend/SYSTEM_FRONTEND.md` §8.1  
> Module sở hữu: **7 (RAG QA), 8 (Graph query API)** + **toàn bộ HTTP API, Auth, Jobs, PublishGate**

---

## 1. Sứ mệnh

Là **cửa duy nhất** ra ngoài cho Frontend:

- FastAPI `/admin/*` và `/citizen/*`
- RAG QA fail-closed + citation validator
- Auth RBAC, rate limit, envelope chuẩn
- Job status / dashboard summary
- PublishGate cho Brief
- Graph neighborhood API (Cypher đọc Neo4j)

BE3 **không** làm: parser/NER (BE1), train/embed/NLI core (BE2) — chỉ **gọi** service của họ.

---

## 2. Hệ thống / thư viện BẮT BUỘC

| Hệ thống | Chi tiết dùng |
|---|---|
| **FastAPI** + Uvicorn | App entry `app/main.py` |
| **Pydantic v2** | Request/response envelope |
| **SQLAlchemy 2** hoặc Tortoise | Postgres users, jobs, audit, briefs meta |
| **neo4j** async/sync driver | Đọc graph + nguyên văn Khoản cho QA |
| **qdrant-client** | Retrieve top-k Khoản |
| **Redis** | Cache QA + broker |
| **GPTCache** (optional) | Semantic cache câu hỏi |
| **python-jose / Authlib** hoặc session JWT | RBAC roles |
| **Arq/Celery API** | Enqueue job, đọc trạng thái |
| **OpenAPI** auto | Contract cho FE (`/openapi.json`) |
| **pytest + httpx.AsyncClient** | API tests |
| Prometheus metrics (optional) | citation_validity, qa_refuse_rate |

---

## 3. Phạm vi code

```
Backend/app/
  main.py
  api/
    admin/          # toàn bộ router admin
    citizen/        # toàn bộ router citizen
    deps.py         # auth, rbac
  services/
    qa_service.py
    citation_validator.py
    graph_query.py
    publish_gate.py
    diff_facade.py      # gọi BE1 worker
    social_facade.py    # gọi BE2
    brief_service.py
    suggest_service.py
    dashboard_service.py
  core/
    config.py
    security.py
    logging.py
    envelope.py
```

---

## 4. Envelope & Auth (chuẩn)

```json
{
  "ok": true,
  "data": {},
  "meta": { "request_id": "...", "latency_ms": 0 },
  "warnings": []
}
```

Roles: `admin_phap_che` | `admin_truyen_thong` | `admin_ops` | `citizen` | `anonymous?`

Citizen **cấm** truy cập `/admin/*`. Filter: chỉ `visibility=public`, `BaiTomTat.status=published`.

---

## 5. Danh sách API BE3 phải implement (đồng bộ FE)

### Admin lõi

| Method | Path |
|---|---|
| POST | `/admin/ingest/legal` |
| GET | `/admin/legal/van-ban` |
| GET | `/admin/legal/van-ban/{id}` |
| GET | `/admin/legal/van-ban/{id}/files` |
| GET | `/admin/legal/files/{file_id}` |
| GET | `/admin/legal/khoan/{id}` |
| POST | `/admin/legal/diff` |
| POST | `/admin/qa/ask` |
| GET | `/admin/jobs` |
| GET | `/admin/jobs/{id}` |
| GET | `/admin/graph/neighborhood` |
| GET | `/admin/dashboard/summary` |

### Admin MXH & truyền thông

| Method | Path |
|---|---|
| POST | `/admin/ingest/social` |
| GET | `/admin/social/topics` |
| GET | `/admin/social/posts` |
| POST | `/admin/link/preview` |
| GET | `/admin/alerts` |
| GET | `/admin/alerts/{id}` |
| PATCH | `/admin/alerts/{id}` |
| POST | `/admin/briefs/generate` |
| GET | `/admin/briefs` |
| GET | `/admin/briefs/{id}` |
| PATCH | `/admin/briefs/{id}` |
| POST | `/admin/briefs/{id}/publish` |
| POST | `/admin/briefs/{id}/archive` |
| POST | `/admin/suggestions/generate` |
| GET | `/admin/suggestions` |
| GET | `/admin/suggestions/{id}` |
| PATCH | `/admin/suggestions/{id}` |
| GET | `/admin/review` |

### Citizen

| Method | Path |
|---|---|
| GET | `/citizen/news` |
| GET | `/citizen/news/{id}` |
| POST | `/citizen/qa/ask` |
| GET | `/citizen/legal/van-ban` |
| GET | `/citizen/legal/van-ban/{id}` |
| GET | `/citizen/legal/van-ban/{id}/files` |
| GET | `/citizen/legal/files/{file_id}` |
| GET | `/citizen/legal/khoan/{id}` |

Đổi path → **bắt buộc** PR kèm cập nhật `Frontend/SYSTEM_FRONTEND.md` §8.1.

---

## 6. QA Engine (module 7) — trách nhiệm BE3

```
ask → semantic cache?
  → retrieve Qdrant top-k Khoản
  → expand Neo4j (ChuThe, THAY_THE, ChuDe)
  → pack context nguyên văn
  → llm_complete(task=qa) qua BE2 router
  → citation_validator: mọi quote ∈ nguồn
  → fail-closed nếu không đủ căn cứ
  → trả answer + citations + graph_paths + confidence + audience
```

Admin QA có thể rộng hơn context; Citizen QA chỉ public nodes.

---

## 7. PublishGate

- Brief chỉ `published` khi: status `review` hoặc `draft` đã đủ citations hợp lệ + actor có role `admin_truyen_thong` (hoặc ops).  
- Ghi audit Postgres (`published_at`, `by`, `brief_id`).  
- Archive tách endpoint.  
- Suggest: chỉ cho phép `draft → ready → exported` — **không** publish ra Citizen.

---

## 8. Việc theo Phase

### Phase A

- [ ] FastAPI skeleton + CORS + envelope + JWT/RBAC
- [ ] Wire ingest/jobs/van-ban/khoan/diff/qa admin
- [ ] Citizen QA skeleton (filter public)
- [ ] OpenAPI xuất được cho FE
- [ ] Citation validator + refuse path có test

### Phase B

- [ ] Social/alerts/graph/review/dashboard/summary
- [ ] Signed URL download files
- [ ] Rate limit citizen QA

### Phase C

- [ ] Briefs + PublishGate + suggestions CRUD
- [ ] Citizen news + van-ban files
- [ ] Metrics citation_validity %, refuse rate

---

## 9. Contract với người khác

| Đối tác | BE3 đưa | BE3 nhận |
|---|---|---|
| **FE** | OpenAPI ổn định, `request_id` | Bug report map §8.1 |
| **BE1** | Enqueue legal jobs, đọc kết quả | Pipeline + domain objects |
| **BE2** | Gọi embed/llm/nli/social/content jobs | Intelligence API nội bộ |
| **DB** | Migration chạy theo version | Connection string, schema version |

---

## 10. Tiêu chí Done BE3

- 100% path trong bảng §5 có handler + test smoke.  
- QA không trả citation bịa (test gold).  
- Citizen token không đọc được `/admin/alerts` (test bảo mật).  
- Publish thiếu citation → 4xx + message rõ.  
- `GET /admin/dashboard/summary` đủ data cho Command Center FE.
