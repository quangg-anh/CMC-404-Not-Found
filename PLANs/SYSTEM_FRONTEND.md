# Frontend — Tư Duy Hệ Thống & Logic Xây Dựng

> Nguồn chân lý: `base_core.md` + `Backend/SYSTEM_BACKEND.md`  
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
5. **Publish honesty** — badge `Nháp / Chờ duyệt / Đã đăng` chỉ hiện ở Admin; Citizen chỉ thấy đã đăng.
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
/admin                      → Command center: alert mới + job sức khỏe + lối tắt
/admin/qa                   → QA nội bộ + citations
/admin/van-ban              → Danh sách VB
/admin/van-ban/:id          → Cây Điều–Khoản–Điểm + entities
/admin/khoan/:id            → Chi tiết Khoản + bài liên quan (nếu có)
/admin/diff                 → Versioning / highlight khác biệt
/admin/graph                → Knowledge Graph Explorer
/admin/mxh                  → Radar dư luận theo ChuDe
/admin/mxh/topics/:slug     → Bài + liên kết Khoản + nhãn đối chiếu
/admin/alerts               → Cảnh báo ưu tiên triage
/admin/suggestions          → Đề xuất đính chính / hướng dẫn
/admin/suggestions/:id      → Soạn thảo gợi ý + căn cứ Khoản
/admin/briefs               → Tin tóm tắt (draft → publish)
/admin/briefs/:id/edit      → Biên tập bite-sized + citations
/admin/jobs                 → Pipeline ingest
/admin/review               → needs_review (parse/extract/link/brief)
```

### 5.2 Citizen Portal (`/` hoặc `/portal`)

```
/                           → Home: tin nổi bật + ô hỏi trợ lý
/news                       → Danh sách bite-sized legal news
/news/:id                   → Đọc tin + citations + CTA “Hỏi thêm”
/ask                        → Chatbot Q&A (citation-first)
/van-ban                    → VB công khai đã publish visibility
/van-ban/:id                → Đọc cấu trúc đơn giản (ít kỹ thuật hơn Admin)
/khoan/:id                  → Nguyên văn Khoản + giải thích ngắn nếu có brief liên quan
```

**Cấm trên Citizen:** `/alerts`, `/mxh` thô, `/jobs`, `/review`, `/suggestions`, bản `draft`.

---

## 6. Luồng người dùng then chốt

### 6.1 Admin — Legal Parser & số hóa

```
Ingest VB → theo dõi Jobs
  → mở VanBan tree Điều/Khoản/Điểm
  → EntityChips (chủ thể, mức phạt, thời hạn…)
  → needs_review → Review queue
```

### 6.2 Admin — Versioning

```
Chọn VB/Khoản A & B → Diff
  → hunk thêm/xóa/sửa (vd. mức phạt 2tr → 5tr)
  → flag method: dẫn chiếu tường minh | similarity
  → CTA: tạo Brief từ các hunk nổi bật
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
MXH theo ChuDe → Post list + RiskBadge
  → filter mau_thuan + confidence cao
  → Alerts triage
  → “Tạo đề xuất đính chính” → Suggestions
```

### 6.5 Admin — Đề xuất đính chính (module 9b)

```
Suggestion detail:
  [Tóm tắt hiểu lầm phổ biến]
  [Khoản đối chiếu + RiskBadge]
  [Draft hướng dẫn / đính chính — editable]
  [Disclaimer nội bộ]
  CTA: Lưu · Sao chép · Xuất PDF/Markdown
```

### 6.6 Admin — Bite-sized news & Publish (module 9a)

```
Generate brief từ VB/Khoản/diff
  → editor ngôn ngữ bình dân
  → CitationList bắt buộc
  → PublishGate: chặn nếu thiếu citation hợp lệ
  → published → xuất hiện Citizen /news
```

### 6.7 Citizen — Tin tóm tắt

```
Home/News → đọc bài dễ hiểu
  → mở citation → Khoản nguyên văn
  → “Hỏi về nội dung này” → prefill /ask
```

### 6.8 Citizen — Trợ lý ảo Q&A

```
Hỏi ngôn ngữ đời thường
  → POST /citizen/qa/ask
  → Answer + Citations (bắt buộc hiển thị)
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
| `RefuseState` | thiếu căn cứ |
| `PublishStatusBadge` | draft / review / published (Admin only) |

### 7.2 Admin-only

| Component | Việc phải làm |
|---|---|
| `GraphCanvas` | neighborhood Neo4j, filter loại node |
| `AlertRow` | bài + claim + Khoản + mức rủi ro |
| `SuggestionEditor` | draft đính chính + evidence |
| `BriefEditor` | tin bình dân + citations + publish CTA |
| `JobStepper` | pipeline stages |
| `CommandCenterWidgets` | alert count, job health, shortcuts |

### 7.3 Citizen-only

| Component | Việc phải làm |
|---|---|
| `NewsCard` | tiêu đề dễ đọc + 1 câu dẫn + link đọc tiếp |
| `NewsArticle` | nội dung bite-sized + citations stack |
| `AskComposer` | chat input + example prompts đời thường |
| `SimpleVanBanTree` | cây VB rút gọn, copy thân thiện hơn Admin |

### 7.4 Trạng thái UI chuẩn

`loading | empty | success | partial | refuse | error`  
QA, link MXH, brief publish phải có `partial/refuse` — tín hiệu chất lượng, không giấu.

---

## 8. Contract wording với backend

| Backend label | UI copy (cả hai phân hệ) |
|---|---|
| `khop` | Khớp với quy định đã liên kết |
| `mau_thuan` | Có dấu hiệu mâu thuẫn — cần kiểm chứng |
| `khong_ro` | Chưa đủ căn cứ để kết luận |
| QA / brief refuse | Không đủ căn cứ trong kho dữ liệu hiện có |
| suggestion disclaimer | Gợi ý nội bộ — cần kiểm chứng trước khi phát hành |

Field Admin dùng: alerts, suggestions, briefs, jobs, graph, social posts.  
Field Citizen dùng: `news` published, QA citizen, van-ban/khoan public.

---

## 9. Bố cục màn ưu tiên

### 9.1 Admin Command Center

```
[ Alerts khẩn (mau_thuan) ]
[ Jobs đang chạy / lỗi ]
[ Lối tắt: Ingest · Diff · Graph · Briefs ]
```

Một composition “trung tâm chỉ huy” — không phải bảng thống kê dày đặc.

### 9.2 Admin Diff

```
[ A ] [ B ] [ Chạy ]
[ Hunk list + dual Khoản link ]
```

### 9.3 Admin Graph

```
[ Seed search ] [ Depth / filter ]
[ GraphCanvas | Node drawer ]
```

### 9.4 Citizen Home

```
[ Brand / tên cổng ]
[ Một câu hỗ trợ ]
[ Ô hỏi trợ lý ]
[ Tin tóm tắt nổi bật ]
```

Hero gọn: brand + 1 CTA hỏi + tin — không nhồi stats/alerts.

### 9.5 Citizen Ask

```
[ Chat thread ]
[ Mỗi turn: Answer + Citations ]
[ KhoanDrawer khi click citation ]
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

1. `apps/admin`: shell RBAC, Van bản, Diff, QA Admin, Jobs  
2. `apps/citizen`: shell, Ask + CitationCard (public filter)  
3. Shared `CitationCard` / `KhoanViewer` / `RefuseState`

### Phase B — Admin giám sát & graph

1. MXH + Alerts + RiskBadge  
2. Graph Explorer  
3. Review queue  

### Phase C — Truyền thông & Citizen hoàn chỉnh

1. BriefEditor + Publish flow  
2. Suggestions từ alerts  
3. Citizen News + SimpleVanBanTree  
4. Deep-link News ↔ Ask ↔ Khoản  

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

- Mọi câu trả lời chatbot hiện citation mở được nguyên văn.
- Chỉ thấy tin/VB đã published.
- Refuse/partial dễ hiểu, không lộ dữ liệu Admin.

---

## 14. Quyết định then chốt

1. **Hai phân hệ UI rõ ràng** — Admin chỉ huy, Citizen tiêu thụ.  
2. **Citation là primitive** dùng chung.  
3. **Khoản là đơn vị đọc mặc định.**  
4. **Wording rủi ro bị khóa** — không copy “xuyên tạc/sai luật” tuyệt đối trên UI.  
5. **PublishGate hiện diện trên UX Admin** trước khi nội dung ra Citizen.  
6. **Frontend trình bày evidence**, không suy luận thay backend.
