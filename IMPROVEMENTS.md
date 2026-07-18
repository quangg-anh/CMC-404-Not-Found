::: wrap
::: top
::: kicker
Danh mục hợp nhất · ưu tiên cho chấm điểm bằng Claude Code
:::

# Những vấn đề cần cải thiện trước hạn 48h

Hợp nhất từ **2 rà soát độc lập** (săn lỗi tiềm ẩn backend + độ sẵn sàng
khi bị AI chấm), **đã tự kiểm chứng lại từng claim** --- loại bỏ báo
động sai, hạ mức các claim thổi phồng. Bối cảnh: ban tổ chức dùng Claude
Code (AI reviewer) chấm mã nguồn, nên trọng tâm là **lỗi tiềm ẩn** và
**khả năng tái lập**.
:::

::: {.card .amber}
### Đã loại/chỉnh 3 claim sai trong quá trình verify (minh bạch)

-   **SAI --- đã loại:** \"thiếu `python-multipart` trong
    requirements\". Thực tế **có** ở `requirements.txt:16`. Agent nhầm
    do sandbox chưa cài.
-   **THỔI PHỒNG --- đã hạ mức:** \"so sánh ngày bằng chuỗi làm RAG mất
    văn bản đúng hiệu lực\" → thực ra seed lưu `date('2024-03-01')` nên
    so sánh chuỗi **đúng trên seed**; chỉ vỡ nếu ingest lưu dạng
    datetime có giờ → xếp **P2 lỗi tiềm ẩn**, không phải P0 vỡ demo.
-   **SAI KHUNG --- đã chỉnh:** \"backup LFS chỉ là placeholder 134
    byte, không có data thật\". 134 byte là **con trỏ LFS** (bản chất
    LFS), pointer khai `size 358610855` + oid hợp lệ → **có object 358
    MB thật trong LFS**. Vấn đề đúng là: ai clone **không cài git-lfs**
    chỉ thấy pointer.
:::

::: legend
[P0]{.pri .p0} chặn demo / AI-reviewer bắt ngay [P1]{.pri .p1} tái lập &
hợp đồng dữ liệu [P2]{.pri .p2} vệ sinh & lỗi tiềm ẩn
:::

## [P0]{.pri .p0}  Phải sửa trước tiên

::: {.item .p0b}
### [P0-1]{.n} Test suite ĐỎ khi chạy đúng như README [\~20\']{.cost}

**Nơi:** `Backend/pytest.ini` / `tests/conftest.py` · **AI-reviewer bắt
ngay:** README bảo `pytest -vv`, làm đúng vậy → **14 failed, 54
passed**.

Dev token bị tắt mặc định (siết bảo mật, đúng) nhưng conftest vẫn gửi
`test-admin-*` → 403 trên mọi endpoint admin → **8 test đổ**. Bật
`ENABLE_DEV_TOKENS=1` còn lại **6 test**, phân loại chính xác (đã chạy
xác nhận):

-   **3 test harness** --- `test_be2_core`: `test_embedding_validation`,
    `test_openai_compatible_embedding_uses_injected_http`,
    `test_entity_link_invariants_dry_run`. **Không phải cần server
    sống** --- mà `FakeResponse` trong `conftest.py` thiếu thuộc tính
    `status_code` mà embedder mới cần (`embedder.py:75`). Sửa fixture là
    xong.
-   **3 test hành vi** ---
    `test_be3_phase_a::test_rag_qa_engine_citation_validation_and_fail_closed`,
    `test_be3_phase_b::test_admin_social_ingest_and_link_preview`,
    `test_be3_phase_b::test_admin_review_queue_and_dashboard_summary`.
    Cần đọc từng test đối chiếu code --- có thể là test cũ chưa cập nhật
    sau refactor.

::: fix
**Sửa:** (1) thêm `ENABLE_DEV_TOKENS=1` +
`AUTH_TOKEN_SECRET=…(≥32 ký tự)` vào `pytest.ini` khối `env` → xanh
8/14. (2) Bổ sung `status_code` vào `FakeResponse` trong conftest → xanh
thêm 3. (3) Rà 3 test hành vi còn lại. [nguồn: rà soát lần 5 · đã chạy
pytest + đọc mã xác nhận]{.src}
:::
:::

::: {.item .p0b}
### [P0-2]{.n} `social_facade.ingest_post` nuốt lỗi INSERT → trả \"queued\" GIẢ [\~15\']{.cost}

**Nơi:** `app/services/social_facade.py:43-44` · **Loại:** false-success
(đã verify đọc mã).

Sau `INSERT INTO jobs` là `except Exception: pass`, rồi vẫn
`return {"status":"queued", "job_id":...}`. Nếu Postgres lỗi → client
nhận 200 + job_id nhưng **không có bản ghi job nào** → job không chạy,
không truy vết. Đúng mẫu lỗi mà `brief_service` đã sửa nhưng file này
chưa.

::: fix
**Sửa:** `logger.exception(...)` + `raise BE2Error(...)` như
`triage_alert` cùng file đã làm. [nguồn: Agent A · đã verify dòng
43-44]{.src}
:::
:::

::: {.item .p0b}
### [P0-3]{.n} README mâu thuẫn Ollama ↔ .env \"OpenAI only\" [\~15\']{.cost}

**Nơi:** `README.md:79` vs `Backend/.env.example` · **AI-reviewer bắt
trong 30 giây.**

README bảo cài **Ollama** + `ollama pull bge-m3`. Nhưng `.env.example`
ghi **\"OpenAI-compatible ONLY (no Ollama)\"**, host
`https://9router.wangganh.id.vn/v1`. Người chấm làm theo README (cài
Ollama) sẽ chạy sai hoàn toàn.

::: fix
**Sửa:** viết lại mục cài đặt README theo đúng OpenAI-compatible: hướng
dẫn điền `BE2_OPENAI_BASE_URL`/`BE2_OPENAI_API_KEY`. [nguồn: Agent B ·
đã verify cả 2 file]{.src}
:::
:::

::: {.item .p0b}
### [P0-4]{.n} Lệch số chiều embedding: 1024 (Data) vs 1536 (Backend) [\~15\']{.cost}

**Nơi:** `Data/.env.example` `EMBEDDING_DIM=1024` vs
`Backend/.env.example` `BE2_EMBEDDING_DIMENSION=1536` · **Loại:** ingest
chết.

Qdrant tạo collection theo Data (1024) mà backend sinh vector 1536 →
**upsert Qdrant lỗi dimension**, toàn bộ ingest/RAG hỏng. Đây là loại
lỗi chỉ lộ khi chạy thật với hạ tầng --- dễ lọt.

::: fix
**Sửa:** thống nhất MỘT con số theo model thật đang dùng (bge-m3=1024
hay text-embedding-3-small=1536), sửa cả 2 file + `collections.json` +
`system_config.embedding_dim`. [nguồn: Agent B · đã verify]{.src}
:::
:::

::: {.item .p0b}
### [P0-5]{.n} Phụ thuộc API key AI ngoài --- hết hạn là sản phẩm \"chết\" [tùy]{.cost}

**Nơi:** `BE2_OPENAI_API_KEY=change_me_9router_api_key` · **Rủi ro:**
QA/ingest/embedding chết khi chấm.

Nếu key không sống trong thời gian chấm, mọi tính năng AI ngừng → mất
điểm deployment + hoàn thiện. Người chấm không có key thì demo trắng.

::: fix
**Sửa:** đảm bảo key sống suốt cửa sổ chấm; HOẶC ghi rõ trong README
cách thay bằng OpenAI thật; HOẶC quay sẵn video demo để có bằng chứng
chạy khi live hỏng. [nguồn: Agent B]{.src}
:::
:::

## [P1]{.pri .p1}  Tái lập & hợp đồng dữ liệu

::: {.item .p1b}
### [P1-1]{.n} Không có `run.sh`/Dockerfile --- hội đồng Linux không chạy được [1--2h]{.cost}

**Nơi:** chỉ có `run.ps1` (Windows-only: `taskkill`,
`Get-NetTCPConnection`, `.venv/Scripts`). Không Dockerfile
Backend/Frontend, không compose app.

::: fix
**Sửa (tối thiểu):** viết `run.sh` tương đương ---
`uvicorn be2_service:app :8002`, `uvicorn app.main:app :8000`, 2 arq
worker, `npm run dev` admin+citizen. **Lý tưởng:** 2 Dockerfile +
`docker-compose.app.yml` để \"one command up\". [nguồn: Agent B · đã
verify không tồn tại]{.src}
:::
:::

::: {.item .p1b}
### [P1-2]{.n} `triage_alert` trả status ngoài enum → FE lệch trạng thái [\~10\']{.cost}

**Nơi:** `app/services/social_facade.py:287,351` · **Loại:** contract
mismatch (đã verify).

Trả về client `new_status="investigating"` --- giá trị KHÔNG có trong
enum `alert_status={open,triaged,closed}`. DB ghi đúng `triaged/closed`.
Lần refresh sau đọc DB thấy `triaged` → UI nhảy trạng thái, filter lệch.

::: fix
**Sửa:** trả về `db_status` (giá trị enum thật) hoặc map nhất quán một
chiều. [nguồn: Agent A · đã verify dòng 287/351]{.src}
:::
:::

::: {.item .p1b}
### [P1-3]{.n} Nhánh fail-closed của QA thiếu key `as_of`/`notices` [\~20\']{.cost}

**Nơi:** `app/services/qa_service.py` (nhánh refuse vs nhánh thành công)
· `citizen/qa.py` trả thẳng dict, không `response_model`.

Nhánh thành công có `as_of`,`notices`; nhánh refuse và
`_extractive_answer` thiếu → FE đọc `res.as_of`/`res.notices` bị
`undefined` tùy nhánh → render lỗi/thiếu.

::: fix
**Sửa:** chuẩn hóa cùng bộ key ở MỌI nhánh `return` (kể cả refuse).
[nguồn: Agent A · phân tích tĩnh]{.src}
:::
:::

::: {.item .p1b}
### [P1-4]{.n} `react-force-graph-2d` chưa cài → màn Graph vỡ nếu quên `npm install` [\~30\']{.cost}

**Nơi:** `GraphPage.tsx:2` import, khai ở `package.json:17` · **Rủi
ro:** màn KG visualization (điểm nhấn) trắng.

::: fix
**Sửa:** chạy fresh `npm install`, `npx tsc -b` tới khi sạch, kiểm màn
`/admin` Graph không trắng. Đảm bảo `run.ps1 -Install`/README nhắc bước
này cho fresh clone. [nguồn: Agent B · đã verify import + khai
báo]{.src}
:::
:::

::: {.item .p1b}
### [P1-5]{.n} Backup LFS: fresh clone thiếu git-lfs chỉ thấy pointer [\~10\']{.cost}

**Nơi:** `.gitattributes` route `Data/backups/**` → LFS; pointer khai
358 MB thật.

Object 358 MB CÓ trong LFS (bằng chứng nhóm đã chạy end-to-end), nhưng
người chấm clone **không cài git-lfs** chỉ nhận file 134 byte → không có
dump để khôi phục.

::: fix
**Sửa:** ghi rõ trong README \"cần `git lfs install && git lfs pull` để
lấy backup\"; HOẶC bỏ LFS cho backup nếu không cần thiết cho việc chấm
(dữ liệu đã dựng lại được từ seed). [nguồn: Agent B (đã chỉnh khung) ·
verify pointer size]{.src}
:::
:::

::: {.item .p1b}
### [P1-6]{.n} `except Exception` phình đều: 53 → 72 → 82 → 107 [1--2h]{.cost}

**Nơi:** toàn `app/` · **AI-reviewer chấm nặng error-swallowing.**

Nợ kỹ thuật DUY NHẤT to lên qua mọi lần cập nhật. Nhiều chỗ nuốt lỗi rồi
trả thành công giả (P0-2 là một ví dụ). Một AI reviewer quét mã sẽ đánh
dấu hàng loạt.

::: fix
**Sửa (ưu tiên):** rà các `except Exception: pass` trong
`brief_service`, `social_facade`, `diff_facade` --- ít nhất
`logger.exception` thay vì nuốt câm, và không trả dict \"thành công\"
sau khi thao tác ghi thất bại. [nguồn: rà soát xuyên suốt · đếm sống
107]{.src}
:::
:::

## [P2]{.pri .p2}  Vệ sinh & lỗi tiềm ẩn

::: tblwrap
  \#      Vấn đề                                                                                                  Nơi                                                  Sửa
  ------- ------------------------------------------------------------------------------------------------------- ---------------------------------------------------- ------------------------------------------------------------------------------------------------------------------
  **1**   So sánh ngày bằng chuỗi (time-travel) --- **tiềm ẩn**, chỉ vỡ nếu `ngay_hieu_luc` lưu datetime có giờ   `qa_service.py` Cypher `toString(...) > $as_of`      Cast `date(vb.ngay_hieu_luc)` và `date($as_of)` thay vì so chuỗi. (Hiện đúng trên seed vì seed lưu `date()`.)
  **2**   `int/float(os.getenv())` crash nếu `.env` đặt biến RỖNG                                                 `config.py`, `be2_service.py:79`, `security.py:52`   Helper `int(os.getenv(k) or default)`. Quan trọng vì `.env.example` phát cho người chấm dễ dính.
  **3**   Nhánh chết `hasattr(v,"iso_format")` (typo, đúng là `isoformat`)                                        `social_facade.py:171`                               Xóa dòng 171-172 (dòng 173 đã xử lý đúng).
  **4**   Suy luận update mong manh `result.endswith("1")`                                                        `review.py:210`                                      `int(result.split()[-1]) > 0`.
  **5**   `confidence` mặc định \"high\" khi LLM bỏ trống                                                         `qa_service.py:1049`                                 Mặc định \"medium\" cho an toàn.
  **6**   Parse ISO không try --- crash nếu MXH trả RFC-822                                                       `pipelines/social/ingest.py:28`                      try/except quanh `fromisoformat`, fallback `now(utc)`.
  **7**   README: `pytest -vv` chưa nhắc `pip install -r requirements.txt` trong venv                             `README.md:125-129`                                  Ghi rõ bước cài deps + chạy test xanh trước khi công bố.
  **8**   Thiếu sơ đồ kiến trúc AI-pipeline + link video/slide trong README                                       `README.md`                                          Chèn 1 diagram (dữ liệu→OCR/parse→NER→KG→embed→RAG/NLI→alert) + link demo. Ăn điểm tiêu chí AI-native + nộp bài.
  **9**   Mô tả công nghệ lệch: README ghi \"Vis-network/Nivo\", thực dùng `react-force-graph-2d`                 `README.md`                                          Sửa cho khớp.
:::

## Checklist gọn để tick trước khi nộp

::: card
**Nhóm 1 --- để không bị AI-reviewer trừ điểm ngay (làm trước,
\~1.5h):**

-   Thêm `ENABLE_DEV_TOKENS=1` vào `pytest.ini` → `pytest -vv` xanh
    (P0-1)
-   Sửa README bỏ Ollama, dùng OpenAI-compatible (P0-3)
-   Thống nhất số chiều embedding 1024/1536 khắp nơi (P0-4)
-   Sửa `social_facade.ingest_post` không trả queued giả (P0-2)

**Nhóm 2 --- để hội đồng chạy được (làm tiếp, \~3h):**

-   Viết `run.sh` cho Linux (P1-1)
-   Đảm bảo API key AI sống / hướng dẫn thay (P0-5)
-   Fresh `npm install` + kiểm màn Graph (P1-4)
-   README: bước cài deps trước pytest + `git lfs pull` (P1-5, P2-7)

**Nhóm 3 --- nâng chất & đủ bộ nộp (nếu còn thời gian):**

-   Sơ đồ kiến trúc AI + link video/slide vào README (P2-8)
-   Rà `except Exception` ở brief/social/diff facade (P1-6)
-   Sửa `triage_alert` status + chuẩn hóa key QA fail-closed (P1-2,
    P1-3)
-   Dockerfile + compose app cho \"one-command up\" (P1-1 mở rộng)
:::

::: {.card .teal}
### Điểm mạnh nên GIỮ & làm nổi bật (đừng đụng vào)

-   **AI-native rõ ràng, có chiều sâu** (RAG citation-first, LLM router,
    NLI, 3 cơ chế KG-native) --- điểm cao nhất, đưa lên đầu slide +
    README.
-   **18/18 màn FE gọi API thật**, không còn màn mock --- mức hoàn thiện
    tốt.
-   **Auth vững** (bcrypt + token HMAC-signed chống giả mạo),
    fail-closed đúng, `.env.example` tài liệu hóa tốt.
-   **Đã chạy end-to-end thật** (dump 358 MB trong LFS) --- bằng chứng
    sản phẩm hoạt động, dùng cho video demo.
:::

Hợp nhất từ 2 rà soát độc lập + tự kiểm chứng từng claim · Mọi mục có
file:line để đối chiếu · Cập nhật cùng REPORT.html
:::
