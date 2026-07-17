# FE — Dual Portal Frontend (1 người)

> Phân công tổng: `TEAM_ASSIGNMENT.md`  
> Contract UI: `Frontend/SYSTEM_FRONTEND.md`  
> Map API bắt buộc: `Frontend/SYSTEM_FRONTEND.md` **§8.1** ↔ OpenAPI do **BE3** phát hành

---

## 1. Sứ mệnh

Xây **2 ứng dụng**:

1. **Admin Dashboard** — trung tâm chỉ huy CQNN  
2. **Citizen Portal** — cổng người dân  

Chia sẻ `packages/ui-legal` + `packages/api-client`.  
FE **không** gọi LLM, Neo4j, hay tự suy diễn pháp lý — chỉ trình bày evidence từ API.

---

## 2. Hệ thống / thư viện BẮT BUỘC

| Hệ thống | Chi tiết |
|---|---|
| **Node.js 20 LTS** | Runtime toolchain |
| **pnpm** hoặc npm workspaces | Monorepo `apps/*` + `packages/*` |
| **Vite 5** | Build Admin + Citizen |
| **React 18 + TypeScript 5** | UI |
| **React Router 6/7** | IA theo SYSTEM_FRONTEND |
| **TanStack Query** | Fetch, cache, polling jobs/alerts |
| **Zod** | Parse response theo envelope BE |
| **vis-network** / Cytoscape.js | `GraphCanvas` |
| **CSS Modules** hoặc Tailwind (team chọn 1) | Styling — tránh overbuild |
| **Vitest + Testing Library** | Unit component citation/refuse |
| **Playwright** (smoke) | Login admin, ask citizen, citation visible |
| **ESLint + Prettier** | Chuẩn code |

**Không bắt buộc MVP:** Next.js, Redux, micro-frontend phức tạp.

---

## 3. Cấu trúc code

```
Frontend/
  ROLE_FRONTEND.md
  SYSTEM_FRONTEND.md
  apps/
    admin/          # port 5173
    citizen/        # port 5174
  packages/
    ui-legal/       # CitationCard, KhoanViewer, RiskBadge, ...
    api-client/     # typed fetch admin/citizen, request_id
```

---

## 4. Việc cụ thể theo Phase

### Phase A — MVP

- [ ] Scaffold monorepo 2 apps + shared packages  
- [ ] Auth lưu token; gắn header; phân `admin_*` vs `citizen`  
- [ ] **Admin:** `/admin`, `/admin/ingest`, `/admin/van-ban`, `/admin/khoan/:id`, `/admin/diff`, `/admin/qa`, `/admin/jobs`  
- [ ] **Citizen:** `/`, `/ask` + CitationCard + RefuseState  
- [ ] Envelope error toast hiện `request_id`  
- [ ] Map đúng §8.1 — không bịa path  

### Phase B

- [ ] MXH topics/posts + `LinkPreviewPanel`  
- [ ] Alerts list/detail + PATCH triage  
- [ ] Graph explorer (`GraphCanvas`) — chỉ render edge từ API  
- [ ] Review queue  

### Phase C

- [ ] Briefs editor + publish/archive + `media_type`  
- [ ] Suggestions editor (CTA copy/export — **không** nút Đăng MXH)  
- [ ] Citizen `/news`, van-ban + `FileAttachList` download  
- [ ] `GraphPathBreadcrumb` trên QA nếu có `graph_paths`  
- [ ] Command Center dùng `GET /admin/dashboard/summary`  

---

## 5. Component bắt buộc (owner FE)

| Shared | Admin-only | Citizen-only |
|---|---|---|
| CitationCard | GraphCanvas | NewsCard / NewsArticle |
| KhoanViewer | AlertRow | AskComposer |
| RiskBadge | SuggestionEditor | SimpleVanBanTree |
| RefuseState | BriefEditor | — |
| GraphPathBreadcrumb | JobStepper | — |
| FileAttachList | IngestForm, LinkPreviewPanel, CommandCenterWidgets | — |
| PublishStatusBadge | — | — |

**Wording khóa (copy đúng):**

| Label BE | UI |
|---|---|
| `khop` | Khớp với quy định đã liên kết |
| `mau_thuan` | Có dấu hiệu mâu thuẫn — cần kiểm chứng |
| `khong_ro` | Chưa đủ căn cứ để kết luận |
| refuse | Không đủ căn cứ trong kho dữ liệu hiện có |

---

## 6. Contract với BE3 / DB

| Đối tác | FE cần | FE không làm |
|---|---|---|
| **BE3** | OpenAPI ổn định; CORS; file signed URL | Đổi schema DB |
| **BE1/BE2** | — (gián tiếp qua API) | Gọi worker/LLM |
| **DB** | Hiểu `visibility`, status enum để hiển thị badge | Viết Cypher |

Khi BE3 đổi path: FE cập nhật §8.1 **cùng PR** hoặc block merge.

---

## 7. Quy tắc UX cứng

1. Citation luôn visible cạnh answer / news.  
2. Refuse hiện rõ — không “hallucinate UI”.  
3. Citizen không có lối vào alerts/MXH thô/jobs.  
4. Suggest ≠ đăng MXH.  
5. Một màn một nhiệm vụ (không nhồi MXH vào Diff).  

---

## 8. Tiêu chí Done FE

- Mọi route §5 SYSTEM_FRONTEND có màn tương ứng theo Phase.  
- Smoke: Citizen hỏi → thấy citation → mở được nguyên văn Khoản.  
- Admin publish brief thiếu citation → UI báo lỗi từ API.  
- Graph không cho user vẽ thêm cạnh.  
- Responsive đọc được trên desktop + mobile Citizen.
