# Frontend — Tư Duy Hệ Thống & Logic Xây Dựng

> Nguồn chân lý: `base_core.md` + `Backend/SYSTEM_BACKEND.md`  
> Phân công FE: `TEAM_ASSIGNMENT.md` · `ROLE_FRONTEND.md`  
> Vai trò: **hai phân hệ giao diện** dùng chung design primitives (citation, Khoản, risk labels)  
> Nguyên tắc: evidence trước opinion; wording rủi ro bị khóa; Citizen chỉ thấy nội dung đã publish

---

## 1. Hai phân hệ frontend

| Phân hệ | Tên sản phẩm | Người dùng | Mục tiêu cảm nhận |
|---|---|---|---|
| **1** | **Admin Dashboard** — trung tâm chỉ huy CQNN | Pháp chế, giám sát TT, ops dữ liệu | Kiểm soát, đối chiếu, cảnh báo, duyệt phát hành |
| **2** | **Citizen Portal** — cổng người dân | Người dân | Dễ hiểu, tin cậy, hỏi nhanh có căn cứ |

Triển khai đề xuất: **2 app** (hoặc 2 zone rõ trong monorepo) — `apps/admin` và `apps/citizen` — chia sẻ `packages/ui-legal` (CitationCard, KhoanViewer, RiskBadge…).

Frontend **không** suy diễn pháp lý; mọi khẳng định phải mở được citation/graph path từ API.

---

## 2. Persona & màn hình

### 2.1 Admin

| Persona | Nhu cầu | Màn hình |
|---|---|---|
| Chuyên viên pháp chế | Số hóa VB, diff, hỏi nội bộ, xem KG | Văn bản, Diff, Graph, QA Admin |
| Giám sát truyền thông | Radar MXH, alerts, gợi ý đính chính, duyệt tin | MXH, Alerts, Suggestions, Briefs |
| Quản trị dữ liệu | Pipeline, review, publish gate | Jobs, Review |

### 2.2 Citizen

| Persona | Nhu cầu | Màn hình |
|---|---|---|
| Người dân | Hiểu luật mới nhanh, hỏi tình huống đời thường | Home tin tóm tắt, News, Chatbot QA, tra cứu VB công khai |

---

## 3. Nguyên tắc trải nghiệm (invariants)

1. **Evidence over answer** — trả lời / tin tóm tắt luôn kèm citation mở được nguyên văn.
2. **Fail visibly** — refuse hiện rõ “không đủ căn cứ”, không wording mượt che thiếu evidence.
3. **Risk language khóa** — chỉ `Khớp / Có dấu hiệu mâu thuẫn — cần kiểm chứng / Chưa đủ căn cứ`.
4. **One job per view** — Admin không nhồi MXH vào màn Diff; Citizen không lộ alerts nội bộ.
5. **Publish honesty** — badge `Nháp / Chờ duyệt / Đã đăng / Lưu trữ` chỉ hiện ở Admin; Citizen chỉ thấy đã đăng.
6. **Suggest ≠ đăng** — màn đề xuất đính chính là công cụ nội bộ; CTA là “Sao chép / Xuất”, không “Đăng MXH”.

---

## 4. Kiến trúc frontend

```
┌──────────────────────────┐     ┌──────────────────────────┐
│ apps/admin               │     │ apps/citizen             │
│ Shell: nav + alert badge │     │ Shell: brand + hỏi nhanh │
│ Auth RBAC admin_*        │     │ Auth citizen/anonymous   │
└────────────┬─────────────┘     └────────────┬─────────────┘
             │                                │
             └────────────┬───────────────────┘
                          ▼
             packages/ui-legal + api-client
             CitationCard · KhoanViewer · RiskBadge
             DiffHunk · GraphCanvas · RefuseState
```

**Stack MVP:** React + TypeScript + Vite (2 apps). Prototype nội bộ có thể Streamlit cho Admin, nhưng production nên SPA.

---

## 5. Information architecture

### 5.1 Admin Dashboard (`/admin`)

```
/admin                      → Command center: GET /admin/dashboard/summary
/admin/ingest               → Form đẩy VB + file → POST /admin/ingest/legal
/admin/qa                   → POST /admin/qa/ask (+ hiện graph_paths nếu có)
/admin/van-ban              → GET /admin/legal/van-ban
/admin/van-ban/:id          → GET /admin/legal/van-ban/{id} + files
/admin/khoan/:id            → GET /admin/legal/khoan/{id}
/admin/diff                 → POST /admin/legal/diff
/admin/graph                → GET /admin/graph/neighborhood
/admin/mxh                  → GET /admin/social/topics
/admin/mxh/topics/:slug     → GET /admin/social/posts (+ POST /admin/link/preview trong drawer)
/admin/alerts               → GET /admin/alerts
/admin/alerts/:id           → GET/PATCH /admin/alerts/{id}
/admin/suggestions          → GET /admin/suggestions
/admin/suggestions/:id      → GET/PATCH /admin/suggestions/{id}
/admin/briefs               → GET /admin/briefs (?status= incl. archived)
/admin/briefs/:id/edit      → GET/PATCH /admin/briefs/{id} · POST publish|archive
/admin/jobs                 → GET /admin/jobs (list + summary)
/admin/jobs/:id             → GET /admin/jobs/{id}
/admin/review               → GET /admin/review
```

### 5.2 Citizen Portal (`/` hoặc `/portal`)

```
/                           → Home: tin nổi bật (GET /citizen/news) + ô hỏi trợ lý
/news                       → GET /citizen/news (lọc media_type nếu cần)
/news/:id                   → GET /citizen/news/{id} + citations + CTA “Hỏi thêm”
/ask                        → POST /citizen/qa/ask (Answer + Citations + graph_paths optional)
/van-ban                    → GET /citizen/legal/van-ban (tên, số hiệu, tóm tắt)
/van-ban/:id                → GET /citizen/legal/van-ban/{id} + files đính kèm
/van-ban/:id/files/:fileId  → GET /citizen/legal/files/{file_id} (tải file điều luật)
/khoan/:id                  → GET /citizen/legal/khoan/{id} (+ brief liên quan nếu có)
```

**Cấm trên Citizen:** `/alerts`, `/mxh` thô, `/jobs`, `/review`, `/suggestions`, bản `draft`/`review`/`archived` của brief.

---

## 6. Luồng người dùng then chốt

### 6.1 Admin — Legal Parser & số hóa

```
/admin/ingest → POST /admin/ingest/legal (VB + file)
  → /admin/jobs theo dõi GET /admin/jobs
  → mở VanBan tree Điều/Khoản/Điểm
  → EntityChips + danh sách file đính kèm
  → needs_review → Review queue
```

### 6.2 Admin — Versioning

```
Chọn VB/Khoản A & B → POST /admin/legal/diff
  → hunk thêm/xóa/sửa (vd. mức phạt 2tr → 5tr)
  → flag method: dẫn chiếu tường minh | similarity
  → CTA: POST /admin/briefs/generate từ hunk nổi bật
```

### 6.3 Admin — Knowledge Graph Explorer

```
Chọn seed (VB | Khoản | ChuThe | ChuDe)
  → GET /admin/graph/neighborhood
  → GraphCanvas: zoom/filter loại node
  → click node → drawer chi tiết (KhoanViewer / meta)
```

Không cho user “vẽ” quan hệ mới trên UI explorer (tránh cạnh ảo).

### 6.4 Admin — Social radar & Alerts

```
GET /admin/social/topics → Post list + RiskBadge
  → trong drawer bài: POST /admin/link/preview (dry-run)
  → filter mau_thuan + confidence cao
  → GET /admin/alerts triage · PATCH trạng thái
  → “Tạo đề xuất đính chính” → POST /admin/suggestions/generate
```

### 6.5 Admin — Đề xuất đính chính (module 9b)

```
GET /admin/suggestions/:id
  [Tóm tắt hiểu lầm phổ biến]
  [Khoản đối chiếu + RiskBadge]
  [Draft hướng dẫn / đính chính — editable → PATCH]
  [Disclaimer nội bộ]
  CTA: Lưu · Sao chép · Xuất PDF/Markdown (status → exported)
```

### 6.6 Admin — Bite-sized news & Publish (module 9a)

```
POST /admin/briefs/generate từ VB/Khoản/diff
  → GET/PATCH /admin/briefs/{id} (media_type text|image|audio|video)
  → CitationList bắt buộc
  → POST .../publish (PublishGate) hoặc POST .../archive
  → published → Citizen GET /citizen/news
```

### 6.7 Citizen — Tin tóm tắt

```
GET /citizen/news → đọc bài (theo media_type)
  → mở citation → Khoản nguyên văn
  → “Hỏi về nội dung này” → prefill /ask
```

### 6.8 Citizen — Tra cứu VB + file

```
GET /citizen/legal/van-ban → tên, số hiệu, tóm tắt
  → GET .../van-ban/{id} cấu trúc đơn giản
  → GET .../files · GET /citizen/legal/files/{file_id} tải file gốc
```

### 6.9 Citizen — Trợ lý ảo Q&A

```
Hỏi ngôn ngữ đời thường
  → POST /citizen/qa/ask
  → Answer + Citations (bắt buộc) + GraphPathBreadcrumb nếu có graph_paths
  → refuse → RefuseState thân thiện + gợi ý tin/VB liên quan
```

**UI rule Citizen:** không cho chia sẻ/copy answer nếu không có ≥ 1 citation (hoặc gắn watermark “chưa có căn cứ”).

---

## 7. Component hệ thống

### 7.1 Shared (`packages/ui-legal`)

| Component | Việc phải làm |
|---|---|
| `CitationCard` | quote + số hiệu + Điều/Khoản + deep-link |
| `KhoanViewer` | nguyên văn, highlight quote, hiệu lực |
| `EntityChips` | chủ thể / nghĩa vụ / quyền / cấm / thời hạn / chế tài |
| `DiffHunkList` | thêm/xóa/sửa + method |
| `RiskBadge` | khop / mau_thuan / khong_ro + confidence |
| `GraphPathBreadcrumb` | render `graph_paths` từ QA response (collapse mặc định) |
| `RefuseState` | thiếu căn cứ |
| `PublishStatusBadge` | draft / review / published / archived (Admin only) |
| `FileAttachList` | tên file VB + nút tải (`files` API) |

### 7.2 Admin-only

| Component | Việc phải làm |
|---|---|
| `GraphCanvas` | neighborhood Neo4j, filter loại node |
| `AlertRow` | bài + claim + Khoản + mức rủi ro |
| `SuggestionEditor` | draft đính chính + evidence · PATCH status |
| `BriefEditor` | tin bình dân + media_type + citations + publish/archive |
| `JobStepper` | pipeline stages từ `GET /admin/jobs/{id}` |
| `CommandCenterWidgets` | data từ `GET /admin/dashboard/summary` |
| `IngestForm` | upload VB + file → `POST /admin/ingest/legal` |
| `LinkPreviewPanel` | gọi `POST /admin/link/preview` trong MXH drawer |

### 7.3 Citizen-only

| Component | Việc phải làm |
|---|---|
| `NewsCard` | tiêu đề + 1 câu dẫn + badge `media_type` |
| `NewsArticle` | nội dung bite-sized + citations (+ media nếu có) |
| `AskComposer` | chat input + example prompts đời thường |
| `SimpleVanBanTree` | cây VB rút gọn + `FileAttachList` công khai |

### 7.4 Trạng thái UI chuẩn

`loading | empty | success | partial | refuse | error`  
QA, link MXH, brief publish phải có `partial/refuse` — tín hiệu chất lượng, không giấu.

---

## 8. Contract API & wording với backend

### 8.1 Mapping route UI → API (bắt buộc đồng bộ)

| UI route | API |
|---|---|
| `/admin` | `GET /admin/dashboard/summary` |
| `/admin/ingest` | `POST /admin/ingest/legal` |
| `/admin/van-ban` | `GET /admin/legal/van-ban` |
| `/admin/van-ban/:id` | `GET /admin/legal/van-ban/{id}`, `.../files` |
| `/admin/khoan/:id` | `GET /admin/legal/khoan/{id}` |
| `/admin/diff` | `POST /admin/legal/diff` |
| `/admin/qa` | `POST /admin/qa/ask` |
| `/admin/graph` | `GET /admin/graph/neighborhood` |
| `/admin/mxh` | `GET /admin/social/topics` |
| `/admin/mxh/topics/:slug` | `GET /admin/social/posts`, `POST /admin/link/preview` |
| `/admin/alerts` | `GET /admin/alerts` |
| `/admin/alerts/:id` | `GET/PATCH /admin/alerts/{id}` |
| `/admin/suggestions` | `GET /admin/suggestions` |
| `/admin/suggestions/:id` | `GET/PATCH /admin/suggestions/{id}` · generate qua `POST .../generate` |
| `/admin/briefs` | `GET /admin/briefs` |
| `/admin/briefs/:id/edit` | `GET/PATCH /admin/briefs/{id}`, `POST .../publish\|archive` |
| `/admin/jobs` | `GET /admin/jobs` |
| `/admin/jobs/:id` | `GET /admin/jobs/{id}` |
| `/admin/review` | `GET /admin/review` |
| `/news` | `GET /citizen/news` |
| `/news/:id` | `GET /citizen/news/{id}` |
| `/ask` | `POST /citizen/qa/ask` |
| `/van-ban` | `GET /citizen/legal/van-ban` |
| `/van-ban/:id` | `GET /citizen/legal/van-ban/{id}`, `.../files` |
| `/van-ban/:id/files/:fileId` | `GET /citizen/legal/files/{file_id}` |
| `/khoan/:id` | `GET /citizen/legal/khoan/{id}` |

### 8.2 Field FE tin cậy từ BE

- QA: `answer`, `citations[]`, `confidence`, `graph_paths`, `audience`
- Khoản / VB: `noi_dung`, entities, relations, `file_ids` / files
- Diff: structured hunks + method
- Social: `chu_de`, `link_score`, `claim_label ∈ {khop,mau_thuan,khong_ro}`
- Alerts: `severity`, `status ∈ {open,triaged,closed}`
- Briefs: `media_type`, `status ∈ {draft,review,published,archived}`, citations
- Suggestions: `draft_correction`, `evidence_khoan_ids`, `status ∈ {draft,ready,exported}`, disclaimer
- Jobs: stage + `needs_review` + lineage id + summary health

### 8.3 Mapping nhãn hiển thị

| Backend label | UI copy (cả hai phân hệ) |
|---|---|
| `khop` | Khớp với quy định đã liên kết |
| `mau_thuan` | Có dấu hiệu mâu thuẫn — cần kiểm chứng |
| `khong_ro` | Chưa đủ căn cứ để kết luận |
| QA / brief refuse | Không đủ căn cứ trong kho dữ liệu hiện có |
| suggestion disclaimer | Gợi ý nội bộ — cần kiểm chứng trước khi phát hành |
| brief `draft` / `review` / `published` / `archived` | Nháp / Chờ duyệt / Đã đăng / Lưu trữ |

---

## 9. Bố cục màn ưu tiên

### 9.1 Admin Command Center

```
[ Alerts khẩn — từ dashboard/summary ]
[ Jobs đang chạy / lỗi — từ dashboard/summary ]
[ Lối tắt: Ingest · Diff · Graph · Briefs ]
```

Một composition “trung tâm chỉ huy” — không phải bảng thống kê dày đặc.

### 9.2 Admin Diff

```
[ A ] [ B ] [ Chạy ]
[ Hunk list với dual Khoản link ]
```

### 9.3 Admin Graph

```
[ Seed search ] [ Depth / filter ]
[ GraphCanvas | Node drawer ]
```

### 9.4 Admin QA / Citizen Ask

```
[ Answer ]
[ Citations stack ]
[ GraphPathBreadcrumb — collapse nếu có graph_paths ]
[ KhoanDrawer khi click citation ]
```

### 9.5 Citizen Home

```
[ Brand / tên cổng ]
[ Một câu hỗ trợ ]
[ Ô hỏi trợ lý ]
[ Tin tóm tắt nổi bật ]
```

Hero gọn: brand + 1 CTA hỏi + tin — không nhồi stats/alerts.

### 9.6 Citizen Van bản

```
[ Tên + số hiệu + tóm tắt ]
[ SimpleVanBanTree ]
[ FileAttachList — tải file điều luật ]
```

---

## 10. State & data fetching

- Admin: React Query — jobs/alerts polling khi tab active; graph fetch theo seed.
- Citizen: cache news list; **không** cache QA thiếu citations.
- Gắn `request_id` trên error toast (đặc biệt Admin ops).
- Auth token scope tách `admin_*` vs `citizen`.

---

## 11. Lộ trình frontend

### Phase A — MVP

1. `apps/admin`: shell RBAC, Ingest, Van bản (list+detail+files), Diff, QA Admin (+ graph_paths), Jobs list/detail  
2. `apps/citizen`: shell, Ask + CitationCard + GraphPathBreadcrumb (public filter)  
3. Shared `CitationCard` / `KhoanViewer` / `RefuseState` / `FileAttachList`

### Phase B — Admin giám sát & graph

1. MXH + LinkPreviewPanel + Alerts triage  
2. Graph Explorer  
3. Review queue  

### Phase C — Truyền thông & Citizen hoàn chỉnh

1. BriefEditor (media_type + publish/archive)  
2. Suggestions list/detail từ alerts  
3. Citizen News + SimpleVanBanTree + download file VB  
4. Deep-link News ↔ Ask ↔ Khoản  
5. Command Center dùng `dashboard/summary` 

---

## 12. Cấu trúc thư mục đề xuất

```
Frontend/
  SYSTEM_FRONTEND.md
  apps/
    admin/
      src/app/ features/ ...
    citizen/
      src/app/ features/ ...
  packages/
    ui-legal/          # shared components
    api-client/        # types + admin/citizen clients
  tests/
```

---

## 13. Tiêu chí “frontend đạt”

**Admin**

- Diff highlight được thay đổi có căn cứ (dẫn chiếu hoặc similarity có flag).
- Graph chỉ render cạnh thật từ API.
- Alert → Suggestion ≤ 2 click; Suggest không có nút tự đăng MXH.
- Publish brief bị chặn nếu thiếu citation.

**Citizen**

- Mọi câu trả lời chatbot hiện citation mở được nguyên văn (và `graph_paths` nếu có).
- Chỉ thấy tin/VB đã published; tải được file điều luật công khai.
- Refuse/partial dễ hiểu, không lộ dữ liệu Admin.
- Mọi màn Citizen map đúng bảng route→API mục 8.1.

---

## 14. Quyết định then chốt

1. **Hai phân hệ UI rõ ràng** — Admin chỉ huy, Citizen tiêu thụ.  
2. **Citation là primitive** dùng chung.  
3. **Khoản là đơn vị đọc mặc định.**  
4. **Wording rủi ro bị khóa** — không copy “xuyên tạc/sai luật” tuyệt đối trên UI.  
5. **PublishGate hiện diện trên UX Admin** trước khi nội dung ra Citizen.  
6. **Frontend trình bày evidence**, không suy luận thay backend.
