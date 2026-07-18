::: wrap
::: top
# Rà soát mã nguồn & Ý tưởng đột phá Hệ thống Đồ thị Tri thức Pháp luật + Giám sát MXH

Repo `antondung/CMC-404-Not-Found` · commit `dfd24f9` · Cập nhật
17/07/2026 sau 11 commit mới · Rà soát lại toàn bộ + kiểm chứng thực tế:
**pytest 24/24 PASS**, **build FE xanh**
:::

::: toc
**Nội dung**

1.  [Kết luận điều hành](#tongquan)
2.  [Mức độ hoàn thiện --- cập nhật](#kientruc)
3.  [Danh mục lỗi còn lại](#loi)
4.  [Ý tưởng đột phá --- 3 mũi nhọn](#dotpha)
5.  [Gợi ý bổ sung & cách đo](#goiy)
6.  [Chiến lược trình bày & roadmap](#huongphattrien)
:::

## [1.]{.num}Kết luận điều hành {#tongquan}

::: {.card .green}
### CẬP NHẬT LẦN 5 (commit `772f248`) --- chạy end-to-end thật, vá đúng 2 finding cũ, nhưng test suite thành ĐỎ {#cập-nhật-lần-5-commit-772f248-chạy-end-to-end-thật-vá-đúng-2-finding-cũ-nhưng-test-suite-thành-đỏ style="margin-top:0"}

Lần hai mặt rõ rệt nhất. Đã pull + boot + chạy pytest thật để kiểm.

::: {.tblwrap style="margin-bottom:12px"}
  Hạng mục                          Trạng thái                  Bằng chứng đã kiểm
  --------------------------------- --------------------------- ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Chạy end-to-end thật**          [CÓ THẬT]{.tag .t-green}    `Data/backups/` có dump thật qua Git LFS: **Postgres 358 MB**, Neo4j dump, Qdrant snapshot (khoan/baidang/chude) ngày 18/07. Đúng nút thắt lần 4 nêu --- giờ đã có dữ liệu chứng minh.
  **Vá secret token mặc định**      [SỬA ĐÚNG]{.tag .t-green}   Finding lần 4 #2. Hết `"dev-...-change-me"`; tự sinh ephemeral secret, production **bắt buộc** secret thật (raise `SecurityConfigError`).
  **`parser.fallback_llm_parse`**   [SỬA]{.tag .t-green}        Hết `NotImplementedError`, đã cài thật (`parser.py:168`).
  **Dev token gated**               [SIẾT]{.tag .t-green}       `test-admin-*` giờ tắt mặc định, gated sau `ENABLE_DEV_TOKENS`. Bảo mật tốt hơn.
  **Test suite (theo README)**      [ĐỎ]{.tag .t-red}           Chạy `pytest -vv` đúng như README → **14 failed, 54 passed** (lần 4: 38 pass sạch). Xem card dưới.
:::

Thêm: README 142 dòng (lần đầu có), 7 file test mới, nhiều FE polish
(chrome, answer markdown, typing indicator), migration
`009_alert_provenance.sql`.
:::

::: {.card .red}
### Regression: test suite đỏ --- nguyên nhân là siết bảo mật quên đồng bộ harness

Đào gốc rễ: dev token bị tắt mặc định (tốt), **nhưng conftest không cập
nhật theo** → test vẫn gửi `Bearer test-admin-phap-che` và nhận **403
trên MỌI endpoint admin**. Đã kiểm sống: cả `test-admin-multi` cũng 403
(lần 4 là 200).

-   Chạy `ENABLE_DEV_TOKENS=1 AUTH_TOKEN_SECRET=…` → 14 fail giảm còn
    **6 fail, 62 pass**. Vậy **8 fail** thuần do dev-token gating.
-   **6 fail còn lại**: 3 test embedder không hermetic (cần embedding
    server sống), 3 test hành vi (RAG citation, social ingest,
    review/dashboard).
-   **Vấn đề thực tế:** README bảo chạy `pytest -vv`, làm đúng vậy thì
    thấy đỏ. Người chấm clone về sẽ gặp 14 fail ngay.

::: fix
**Cách sửa (rẻ, cấp):** thêm `ENABLE_DEV_TOKENS=1` vào `pytest.ini` (mục
`[pytest] env`) hoặc set trong `conftest.py`. Xong 8/14 fail. 6 fail còn
lại cần fixture embedder + rà 3 test hành vi.
:::

**Và `except Exception` tiếp tục phình: 82 → 107** --- nợ kỹ thuật duy
nhất to lên đều đặn qua mọi lần cập nhật.
:::

::: {.card .green style="display:none"}
### CẬP NHẬT LẦN 4 (commit `839efff`) --- đóng lỗ hổng xác thực tận gốc + dọn dead code + nối gần hết FE {#cập-nhật-lần-4-commit-839efff-đóng-lỗ-hổng-xác-thực-tận-gốc-dọn-dead-code-nối-gần-hết-fe style="margin-top:0"}

Đã boot app + khai thác giả mạo token, không tin commit message. Những
việc lớn ở lần này:

::: {.tblwrap style="margin-bottom:12px"}
  Hạng mục                                Trạng thái                      Bằng chứng khai thác/kiểm sống
  --------------------------------------- ------------------------------- ------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Auth thật --- `/auth/login` (mới)**   [ĐÓNG TẬN GỐC]{.tag .t-green}   `auth.py:23` verify bcrypt qua pgcrypto `crypt()`, không lộ email tồn tại, 401/503 đúng. Token là **HMAC-signed** (`lx1.payload.sig`) có expiry.
  **Chống giả mạo token**                 [VỮNG MẬT MÃ]{.tag .t-green}    Sống: token thật → `admin_ops`; sửa chữ ký → **anonymous**; tự chế payload admin + ký bừa → **anonymous**. `hmac.compare_digest` constant-time.
  **FE Login nối auth thật**              [SỬA]{.tag .t-green}            `Login.tsx:23` gọi `POST /auth/login` với email+password. **Hết RBAC chuỗi email**, password được gửi thật. Session persist qua F5.
  **Dead code + route chết**              [DỌN]{.tag .t-green}            Xóa `protocols.py`, `workers/legal_jobs.py` trùng, `test_be1.py`, 2 `App.css`. Thêm route `/graph`, `/news/:id` (`NewsDetailPage`). `citizen/index.html` title đã sửa.
  **Endpoint FE nối**                     [11 → 28]{.tag .t-green}        7 trang admin mới (Graph, Jobs, Khoan, Review, Social, Suggestions, Briefs). Ingest tách NER chạy nền, thêm OCR fallback PDF scan.
  **Test**                                [38 PASS]{.tag .t-green}        Chạy venv sạch: **38 passed** (lần 3 là 25/27). Test embedding hết phụ thuộc Ollama --- đã hermetic lại.
:::

**Nhận định:** đây là lần cập nhật đóng được **lỗ hổng nghiêm trọng nhất
còn lại** (auth). Cùng với lần 3 (M1--M4 + 3 ý tưởng đột phá), hệ thống
đã vượt ngưỡng \"chạy được thật\" cho luồng chính.
:::

::: {.card .amber}
### Điểm còn cần biết (verify sâu)

1.  **`except Exception` tiếp tục tăng: 72 → 82.** Code mới (7 trang,
    collectors, scripts) thêm try/except. Nợ nuốt lỗi im lặng vẫn phình.
2.  **Dev shortcut token vẫn còn** --- `test-admin-multi` v.v.
    exact-match, có chủ đích cho eval. Vô hại nếu `AUTH_TOKEN_SECRET`
    được đặt ở production, nhưng **secret mặc định
    `"dev-lexsocial-secret-change-me"`** phải đổi khi deploy thật, nếu
    không ai cũng ký được token admin.
3.  **28 endpoint FE nối nhưng chưa chạy end-to-end thật** --- cần
    Neo4j+Qdrant+Ollama sống để kiểm. Số route nối không đồng nghĩa mọi
    màn hoạt động.
:::

::: {.card style="border-color:color-mix(in srgb, var(--green) 25%, transparent)"}
### [Lịch sử ---]{.muted style="font-weight:400"} LẦN 3 (commit `11fb753`): 4 lỗi P0 của lần 2 đã đóng + 3 ý tưởng đột phá được triển khai {#lịch-sử-lần-3-commit-11fb753-4-lỗi-p0-của-lần-2-đã-đóng-3-ý-tưởng-đột-phá-được-triển-khai style="margin-top:0"}

Đã boot app thật + khai thác sống, không tin commit message. Toàn bộ
nhóm lỗi M1--M4 tôi báo cáo lần trước **đã sửa và kiểm chứng đóng**:

::: {.tblwrap style="margin-bottom:12px"}
  Lỗi P0 (lần 1)                   Trạng thái              Bằng chứng khai thác sống
  -------------------------------- ----------------------- -------------------------------------------------------------------------------------------------------------------------------------------------------------
  **M1 · Không ghi Neo4j**         [ĐÓNG]{.tag .t-green}   `neo4j_legal.py:62-78` có MERGE `VanBanPhapLuat/Dieu/Khoan` + `CO_DIEU/CO_KHOAN`; `pipeline.py` nối writer + reindex Qdrant; gọi từ worker + `diff_facade`.
  **M2 · Mock trong validator**    [ĐÓNG]{.tag .t-green}   `citation_validator.py:20` giờ `return None` (fail-closed), xóa hẳn canonical text bịa. Comment ghi rõ \"must never invent the source text\".
  **M3 · Token đoán được**         [ĐÓNG]{.tag .t-green}   Sống: `Bearer toi-la-admin_ops-hehe` → **403** (trước 200). `security.py` đổi sang **exact match** `t == "test-admin-ops"`. FE cũng bỏ token cứng.
  **M4 · File nội bộ fail-open**   [ĐÓNG]{.tag .t-green}   `citizen/legal.py:67` giờ `file_public `**`and`**` parent_public` --- đổi OR thành AND, comment và code đã khớp.
:::

**Và quan trọng nhất: cả 3 ý tưởng đột phá trong report này đã được
triển khai thật** (commit `11fb753`), tôi đã boot app xác nhận:

-   **Ý tưởng 01 · Time-travel QA** --- `qa_service.py:20-34` lọc
    `ngay_hieu_luc > $as_of` + loại Khoản bị `THAY_THE`. Refuse message
    sống: *\"No legal candidates **in force as of the requested
    date**.\"*
-   **Ý tưởng 02 · Clarity Index** --- endpoint
    `GET /admin/graph/clarity-index` (`graph.py:25`) gộp `DOI_CHIEU`.
    Sống: không token → 403, có token → 200.
-   **Ý tưởng 03 · Entailment citation** ---
    `qa_service.py:150 _verify_faithfulness` tái dùng `NLIService` kiểm
    mỗi claim có được Khoản ủng hộ, dùng heuristic offline nên không
    thêm phụ thuộc.
:::

::: {.card .amber}
### Nhưng verify sâu tìm ra 3 điểm mới cần biết

1.  **Test không còn hermetic.** Commit ghi \"27 pass\" --- đúng trên
    máy nhóm, nhưng tôi chạy được **25 pass, 2 fail**. Hai test
    `test_be2_core` giờ gọi HTTP thật tới API embedding (Ollama
    `bge-m3`, thay torch local ở commit `e4b827b`) → máy không chạy
    Ollama là fail với `ConnectError`. **Test có phụ thuộc ngoài ẩn**;
    \"pass\" phụ thuộc môi trường.
2.  **`except Exception` TĂNG từ 53 lên 72** (kèm `pass`: 43, gần như
    giữ nguyên). Code pipeline mới thêm \~19 try/except. Nợ nuốt lỗi im
    lặng chưa trả.
3.  **Nhiều commit message không chuyên nghiệp** --- `"adidaphat"`,
    `"nam mô adi đà lạt"`, `"commit again"`. Không ảnh hưởng code nhưng
    nếu repo được chấm cả lịch sử git thì nên squash trước khi nộp.
:::

::: {.card .green style="display:none"}
### Cập nhật 11 commit --- cả 4 lỗi P0 đã sửa THẬT, đã tự kiểm chứng {#cập-nhật-11-commit-cả-4-lỗi-p0-đã-sửa-thật-đã-tự-kiểm-chứng style="margin-top:0"}

Không tin theo commit message. Từng lỗi được đọc code và chạy lại:

::: {.tblwrap style="margin-bottom:12px"}
  Lỗi P0                     Trạng thái                  Bằng chứng đã kiểm
  -------------------------- --------------------------- ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **L1 · Bypass xác thực**   [SỬA ĐÚNG]{.tag .t-green}   `role_checker(user: UserToken = Depends(get_current_user))` + Portal Isolation. **Khai thác sống: không token → 403, body tự khai role → 403, token citizen → 403.** Đóng thật.
  **L2 · RAG vỏ rỗng**       [SỬA ĐÚNG]{.tag .t-green}   `embedder.embed_texts([question])` thay vector giả; `router.complete(task=,prompt=,schema=,complexity=)` đúng chữ ký; prompt có `retrieved_context`.
  **L3 · Fail-closed giả**   [DI DỜI]{.tag .t-amber}     Xóa khỏi `qa_service` ✓ --- nhưng keyword **chuyển sang** `conftest.py:175`. Xem mục 3.
  **L4 · Test không chạy**   [SỬA ĐÚNG]{.tag .t-green}   13 deps đủ + `pytest.ini`. **Dựng venv sạch, chạy thật: `24 passed`.**
:::

Thêm: `deps.py` **không còn class `Fake` nào**; CORS đã siết;
`VersionDiff.diff()` đã có thật; ontology edge `CO_YKIEN` đã sửa; FE
**build xanh cả 2 app** và nối được **11/24 endpoint**.
:::

**Nhận định tổng:** 11 commit sửa thật nhóm lỗi **cấu hình và guardrail
dễ kiểm** (Depends, requirements, CORS, ontology, enum, wording). Nhưng
**phần lõi giá trị vẫn nguyên vẹn chưa động tới**: không có đường ghi
Neo4j, không enqueue job thật, LLM extract vẫn mock.

::: {.card style="border-color:color-mix(in srgb, var(--green) 30%, transparent)"}
### Bốn lỗi P0 (từng báo ở lần rà soát trước) --- [nay đã ĐÓNG hết ở commit `11fb753`/`db859e7`]{style="color:var(--green)"} {#bốn-lỗi-p0-từng-báo-ở-lần-rà-soát-trước-nay-đã-đóng-hết-ở-commit-11fb753db859e7 style="margin-top:0"}

Giữ lại đây để đối chiếu. Chi tiết bằng chứng khai thác sống ở bảng mục
1.

1.  ~~Không ghi Neo4j~~ → **đã có `neo4j_legal.py:62-78` MERGE node +
    `pipeline.py` reindex Qdrant.**
2.  ~~Mock trong CitationValidator~~ → **`citation_validator.py:20` giờ
    `return None` fail-closed.**
3.  ~~Token đoán được~~ → **exact match; `Bearer …admin_ops…` giờ trả
    403 (đã test sống).**
4.  ~~File nội bộ fail-open~~ → **`citizen/legal.py:67` đổi OR thành
    AND.**
:::

::: {.card .amber}
### Một cáo buộc SAI --- đã bác bỏ

Rà soát tự động báo `GET/PATCH /admin/briefs/{id}` mất auth. **Sai.**
`briefs.py:11` có `dependencies=[Depends(require_admin())]` ở **cấp
router** --- bảo vệ toàn bộ route trong file. Ghi lại đây để không ai
tốn công \"sửa\" thứ không hỏng.
:::

## [2.]{.num}Mức độ hoàn thiện --- cập nhật {#kientruc}

::: tblwrap
+-----------------------+-----------------------+-----------------------+
| Thành phần            | Lần 3 → Lần 4         | Thay đổi thực chất ở  |
|                       |                       | lần cập nhật mới nhất |
+=======================+=======================+=======================+
| **Data**              | ::: bar               | Thêm                  |
|                       | :::                   | `de                   |
|                       |                       | mo_content_seed.sql`. |
|                       | [\~90% (giữ)]{.muted} | Payload index Qdrant  |
|                       |                       | vẫn chưa tạo.         |
+-----------------------+-----------------------+-----------------------+
| **BE2**\              | ::: bar               | **Nâng.** 3 ý tưởng   |
| [Inte                 | :::                   | đột phá triển khai    |
| lligence/RAG]{.muted} |                       | thật (time-travel,    |
|                       | [65% →                | clarity, entailment). |
|                       | **\~75%**]{.muted}    | Validator hết mock.   |
|                       |                       | Đổi sang embedder     |
|                       |                       | OpenAI-compatible     |
|                       |                       | (Ollama). Còn: test   |
|                       |                       | embedding phụ thuộc   |
|                       |                       | Ollama, `graph_paths` |
|                       |                       | vẫn rỗng cứng.        |
+-----------------------+-----------------------+-----------------------+
| **BE3**\              | ::: bar               | **Nâng.** M3/M4 đóng  |
| [                     | :::                   | (token exact-match,   |
| API/services]{.muted} |                       | file AND). Endpoint   |
|                       | [55% →                | clarity-index có      |
|                       | **\~68%**]{.muted}    | auth. Thêm upload     |
|                       |                       | MinIO thật. Còn: **72 |
|                       |                       | chỗ                   |
|                       |                       | `except Exception`**  |
|                       |                       | (tăng), enqueue job   |
|                       |                       | vẫn chưa nối          |
|                       |                       | end-to-end.           |
+-----------------------+-----------------------+-----------------------+
| **BE1**\              | ::: bar               | **Nhảy vọt.**         |
| [Legal                | :::                   | `pipeline.py` mới nối |
| Pipeline]{.muted}     |                       | parse → MERGE Neo4j → |
|                       | [30% →                | reindex Qdrant.       |
|                       | **\~55%**]{.muted}    | `extractor` gọi LLM   |
|                       |                       | router thật (hết      |
|                       |                       | mock).                |
|                       |                       | `minio_storage.py`,   |
|                       |                       | `extract_text.py`     |
|                       |                       | mới. File trùng đã    |
|                       |                       | tách khác nhau. Còn:  |
|                       |                       | `parse                |
|                       |                       | r.fallback_llm_parse` |
|                       |                       | vẫn                   |
|                       |                       | `                     |
|                       |                       | NotImplementedError`. |
+-----------------------+-----------------------+-----------------------+
| **Frontend**          | ::: bar               | **Nhảy vọt.** Login   |
|                       | :::                   | nối `/auth/login`     |
|                       |                       | thật, session persist |
|                       | [62% →                | F5, endpoint **11 →   |
|                       | **\~80%**]{.muted}    | 28**, 7 trang admin   |
|                       |                       | mới, route chết đã    |
|                       |                       | sửa, dead `App.css`   |
|                       |                       | xóa. Còn: một số màn  |
|                       |                       | chưa kiểm chạy        |
|                       |                       | end-to-end với hạ     |
|                       |                       | tầng sống.            |
+-----------------------+-----------------------+-----------------------+
:::

## [3.]{.num}Danh mục lỗi còn lại {#loi}

::: {.card .green}
### Nhóm lỗi P0 từ các lần trước --- [nay đã đóng hết]{style="color:var(--green)"} {#nhóm-lỗi-p0-từ-các-lần-trước-nay-đã-đóng-hết style="margin-top:0"}

Toàn bộ lỗi chặn từng báo (L1--L4 lần 2, M1--M4 lần 3, auth bypass) đã
được sửa và kiểm chứng sống. Chi tiết bằng chứng ở bảng mục 1. Không còn
lỗi **P0 chặn demo** nào ở lần 4.

::: {.tblwrap style="margin-bottom:0"}
  Lỗi                                       Đóng ở   Kiểm chứng
  ----------------------------------------- -------- ----------------------------------
  Auth bypass / token đoán được / giả mạo   lần 4    token giả mạo → anonymous (sống)
  M1 · không ghi Neo4j                      lần 3    `neo4j_legal.py:62-78` MERGE
  M2 · mock trong validator                 lần 3    `return None` fail-closed
  M4 · file nội bộ fail-open                lần 3    OR → AND
  FE Login RBAC chuỗi email                 lần 4    `POST /auth/login` thật
  Route chết, dead code, index.html title   lần 4    đã xóa/thêm route
:::
:::

### [P1]{.tag .t-amber}  Nợ kỹ thuật còn lại

::: tblwrap
  -----------------------------------------------------------------------------------------------
  Vấn đề                            Vị trí                  Chi tiết
  --------------------------------- ----------------------- -------------------------------------
  **82 chỗ `except Exception`**\    toàn `app/`             Nặng nhất vẫn ở `brief_service`: nuốt
  [tăng liên tục: 53→72→82]{.muted}                         lỗi INSERT/UPDATE rồi **trả dict như
                                                            thể thành công** → API 200 trong khi
                                                            DB không ghi. Đây là nợ kỹ thuật
                                                            **duy nhất phình to qua mỗi lần cập
                                                            nhật**.

  **Enqueue job chưa nối            `diff_facade.py`        Có `on_startup` ctx + worker
  end-to-end**                                              functions, nhưng API vẫn INSERT job
                                                            rồi trả `queued` --- chưa thấy
                                                            `enqueue_job`. Với NER giờ tách chạy
                                                            nền qua `POST /admin/legal/run-ner`,
                                                            cần kiểm luồng này có chạy thật
                                                            không.

  **`graph_paths` vẫn rỗng cứng**   `qa_service.py`         Đã bỏ lấy từ LLM (đúng) nhưng chưa
                                                            thay bằng Cypher. Time-travel/clarity
                                                            dùng graph thật, riêng `graph_paths`
                                                            trong QA response vẫn `[]`.

  **`parser.fallback_llm_parse`**   `parser.py:139`         Còn `NotImplementedError`. Parser
                                                            regex chạy tốt trên văn bản chuẩn;
                                                            văn bản lệch format rơi vào nhánh
                                                            chưa cài.

  **Secret token mặc định**         `security.py:20`        `AUTH_TOKEN_SECRET` mặc định
                                                            `"dev-lexsocial-secret-change-me"`.
                                                            Nếu deploy không đổi, bất kỳ ai biết
                                                            secret này **tự ký được token admin
                                                            hợp lệ**. Phải đặt biến môi trường ở
                                                            production.
  -----------------------------------------------------------------------------------------------
:::

::: {.card .amber}
### Chất lượng test --- 38 PASS nghĩa là gì (cập nhật)

**Chạy venv sạch: `38 passed`** (lần 3 là 25/27 do phụ thuộc Ollama; nay
đã hermetic lại). Con số tăng thật, coverage rộng hơn.

**Điểm cộng:** `conftest.py` override ở tầng **dependency** nên mã
production `QAService`/`LLMRouter`/`CitationValidator`/`PublishGate`
**chạy thật**. Guardrail thật được kiểm.

**Vẫn giữ nguyên các giới hạn từ lần trước:** cheat keyword ở
`conftest.py:175` (fake được phép kịch bản hóa, nhưng test fail-closed
là dàn dựng); embedder fake trả vector hằng số → ranking vô nghĩa; **0%
đường dữ liệu thật (Qdrant/Neo4j/Ollama sống) được kiểm trong CI**. \"38
PASS\" chứng minh guardrail đúng, **không** chứng minh hệ thống chạy
được với hạ tầng thật --- vẫn cần một lần chạy end-to-end thủ công.
:::

## [4.]{.num}Ý tưởng đột phá --- 3 mũi nhọn {#dotpha}

::: {.card .violet}
**Luận điểm trung tâm:** Nhóm đã xây một knowledge graph đầy đủ, nhưng
hiện tại **graph không đóng góp gì cho sản phẩm**. QA chỉ vector search;
`graph_paths` lấy từ output LLM (tức là bịa). Nếu bỏ Neo4j đi, hệ thống
vẫn chạy y hệt --- **và đó chính là vấn đề**. Nếu KG có thể bị gỡ bỏ mà
không ai nhận ra, giám khảo sẽ hỏi: vậy xây nó làm gì?

Ba ý tưởng dưới đây có một mẫu số chung: **chúng chỉ làm được bằng
graph, và không thể làm bằng vector search**. Mỗi ý tưởng đều dùng thứ
đã có sẵn trong ontology mà chưa ai động tới. Đây là cách biến KG từ
trang trí thành lý do tồn tại.
:::

::: {.idea-hd style="margin-top:40px"}
[01]{.n} [Time-Travel Legal QA --- RAG nhận biết thời điểm hiệu
lực]{.ttl} [MŨI NHỌN KỸ THUẬT]{.tag .t-violet}
:::

#### Vấn đề chưa ai giải

Đề bài mở đầu bằng đúng một câu: *\"Từ 01/07/2026, nhiều luật/nghị
định/thông tư mới có hiệu lực\"*. **Toàn bộ bài toán sinh ra từ sự
chuyển giao phiên bản.** Nhưng mọi hệ RAG pháp luật hiện có --- kể cả
bản của nhóm --- trả lời như thể luật là bất biến: retrieve top-k theo
similarity, không quan tâm điều khoản còn hiệu lực không, hay hành vi
xảy ra lúc nào.

**Insight:** Mọi câu hỏi pháp lý đều có một tham số ẩn mà không ai nhập:
**thời điểm**. \"Mức phạt nồng độ cồn là bao nhiêu?\" --- phạt cho hành
vi xảy ra hôm nay, hay tháng trước? Nếu hành vi xảy ra 30/06/2026 thì
phải áp luật cũ. Đây không phải chi tiết kỹ thuật --- **đây là nguyên
tắc áp dụng pháp luật theo thời điểm**. Một hệ thống trả lời theo luật
mới cho hành vi cũ là trả lời **sai về mặt pháp lý**, dù citation hoàn
toàn có thật.

#### Nguyên liệu đã có sẵn

-   `VanBanPhapLuat` đã có `ngay_ban_hanh`, `ngay_hieu_luc`,
    `trang_thai` --- **seed đã điền** (`nghi_dinh_mau.cypher`: hiệu lực
    2024-03-01).
-   Cạnh `THAY_THE` / `SUA_DOI` đã trong `ontology.json:191` --- **chưa
    ai dùng**.
-   `VersionDiff` (BE1) đã có khung --- cần method `diff()` (trùng với
    lỗi P1 phải sửa).

#### Cách làm

    POST /citizen/qa/ask  { "question": "...", "as_of": "2026-06-30" }   # mặc định: hôm nay

    # 1. Retrieval filter theo thời điểm (Cypher, không phải vector):
    MATCH (vb:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan)
    WHERE vb.ngay_hieu_luc <= $as_of
      AND NOT EXISTS {
        MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(vb)
        WHERE moi.ngay_hieu_luc <= $as_of        # chỉ loại nếu VB thay thế ĐÃ hiệu lực
      }
    RETURN k.khoan_id

    # 2. Chỉ search Qdrant trong tập khoan_id hợp lệ (payload filter)
    # 3. Nếu câu hỏi ngụ ý mốc khác ("năm ngoái tôi bị phạt..."), LLM extract mốc → hỏi lại

::: demo
**Khoảnh khắc demo:** Gõ **cùng một câu hỏi**, đổi mỗi tham số ngày:\
→ `as_of=2026-06-30`: \"Mức phạt là 2--3 triệu đồng\" [--- cite NĐ cũ,
Điều 6 Khoản 6]{.muted}\
→ `as_of=2026-07-01`: \"Mức phạt là 6--8 triệu đồng\" [--- cite NĐ mới,
Điều 7 Khoản 2]{.muted}\
→ kèm banner tự sinh: **\"⚠ Quy định này đã thay đổi từ 01/07/2026. Xem
thay đổi →\"** (nối thẳng vào diff hunks của module 4)
:::

::: why
**Vì sao đột phá:**

-   **Vector search về nguyên tắc không làm được điều này.** Nó cần
    graph traversal trên cạnh `THAY_THE`. Đây là bằng chứng không thể
    chối cãi rằng KG là cần thiết --- trả lời trực tiếp câu hỏi \"xây
    Neo4j làm gì\".
-   Nó trả lời đúng câu hỏi mà **đề bài đặt ra ngay dòng đầu tiên**, thứ
    mà không nhóm nào khác sẽ chạm tới.
-   Nó **nối module 4 (diff) vào module 7 (QA)** --- hai module rời rạc
    trong spec trở thành một tính năng. Diff không còn là màn hình ai đó
    phải bấm vào, nó trở thành cảnh báo tự nhảy ra đúng lúc người dùng
    cần.
-   Nó biến một **bug pháp lý** (trả lời sai luật cho hành vi cũ) thành
    **feature**.
:::

::: {.idea-hd style="margin-top:44px"}
[02]{.n} [Chỉ số Mù mờ Pháp lý --- vòng phản hồi ngược từ dư luận về nhà
nước]{.ttl} [MŨI NHỌN SẢN PHẨM]{.tag .t-violet}
:::

#### Vấn đề chưa ai giải

Hệ thống hiện tại --- và mọi hệ thống giám sát MXH --- nhìn theo **một
chiều**: dân hiểu sai → gắn nhãn → đính chính. Ngầm định là: **luật
đúng, dân sai**. Nhiệm vụ của AI là phát hiện ai sai và sửa họ.

**Insight đảo ngược:** Nếu 500 người cùng hiểu sai **một** điều khoản,
vấn đề có thể không nằm ở 500 người đó. Nó nằm ở cách điều khoản ấy
**được viết**, hoặc **được truyền thông**. Nói cách khác: **dư luận MXH
là một bộ test QA miễn phí, quy mô triệu người, cho chất lượng soạn thảo
luật.** Hiện tại nhà nước đang vứt bỏ tín hiệu đó.

#### Nguyên liệu đã có sẵn --- đây là phần đẹp nhất

**Không cần model mới. Không cần dữ liệu mới.** Toàn bộ tín hiệu đã nằm
trong graph:

-   `DOI_CHIEU` edges đã có `label ∈ {khop, mau_thuan, khong_ro}` +
    `score` --- **bắt buộc theo ontology**.
-   `GAN_CO_CAN_KIEM_CHUNG` đã link `BaiDang → Khoan` với `score`.
-   Chỉ cần **một câu Cypher aggregate** và một màn hình.

```{=html}
<!-- -->
```
    // Chỉ số mù mờ: mỗi Khoản bị hiểu sai bao nhiêu, và hiểu sai theo mấy hướng khác nhau
    MATCH (y:YKien)-[d:DOI_CHIEU]->(k:Khoan)
    WITH k,
         count(CASE WHEN d.label = 'mau_thuan' THEN 1 END) AS mau_thuan,
         count(CASE WHEN d.label = 'khong_ro'  THEN 1 END) AS khong_ro,
         count(*) AS tong
    WHERE tong >= 5                                    // đủ tín hiệu mới kết luận
    RETURN k.khoan_id, k.noi_dung,
           toFloat(mau_thuan + khong_ro) / tong AS clarity_risk,
           tong AS volume
    ORDER BY clarity_risk * log(volume) DESC           // vừa sai nhiều, vừa lan rộng

::: demo
**Khoảnh khắc demo:** **Heatmap trên chính cây Điều--Khoản của văn bản
luật.**\
Điều 1 xanh · Điều 2 xanh · **Điều 6 Khoản 6 ĐỎ RỰC** · Điều 7 vàng...\
\
Click vào ô đỏ → drill down:\
*\"Điều 6 Khoản 6 --- 47 bài đăng đối chiếu mâu thuẫn, 3 cụm hiểu lầm
chính:\
(a) 22 bài tưởng áp dụng cả xe đạp --- **khoản không nêu rõ loại phương
tiện**\
(b) 15 bài nhầm mức phạt sang khung khác\
(c) 10 bài không rõ \'nồng độ cồn bằng 0\' nghĩa là gì\"*\
\
→ Nút: **\"Sinh báo cáo chất lượng truyền thông\"** gửi cơ quan soạn
thảo.
:::

::: why
**Vì sao đột phá:**

-   **Đổi khách hàng của sản phẩm.** Từ \"công cụ giám sát dân\" thành
    \"công cụ giúp nhà nước tự cải thiện\". Với bối cảnh Việt Nam, đây
    là khác biệt rất lớn về mặt chính trị-xã hội --- an toàn hơn, và giá
    trị hơn nhiều.
-   **Nó là hệ quả tự nhiên của chính nguyên tắc đạo đức nhóm đã chọn.**
    Nhóm quyết định không phán đúng/sai, chỉ đo mức đối chiếu. Ý tưởng
    này dùng **chính mức đối chiếu đó** để đo độ rõ ràng của luật ---
    thay vì để đo độ sai của dân. Nguyên tắc đạo đức không còn là hạn
    chế phải chấp nhận, **nó trở thành nguồn của tính năng hay nhất**.
    Đây là luận điểm mạnh nhất bạn có thể trình bày.
-   **Chi phí gần bằng 0.** Một Cypher query + một màn heatmap. Toàn bộ
    pipeline BE2 đã sinh sẵn dữ liệu này rồi và đang vứt đi.
-   Nó tạo **vòng lặp khép kín**: luật → dân hiểu → hiểu lầm → tín hiệu
    → luật viết rõ hơn lần sau. Đây là thứ biến dự án từ \"tool\" thành
    \"hệ thống\".
:::

**Lưu ý ranh giới --- nói rõ khi bảo vệ:** Hệ thống **không** phán
\"điều luật này viết sai\". Nó chỉ báo \"điều khoản này đang được hiểu
theo nhiều hướng khác nhau\" --- một tín hiệu **truyền thông**, không
phải kết luận **pháp lý**. Thẩm quyền sửa luật thuộc về con người. Ranh
giới này phải giữ đúng như nguyên tắc gốc của dự án.

::: {.idea-hd style="margin-top:44px"}
[03]{.n} [Citation kiểm chứng bằng suy luận --- AI tự soi bằng chính
thước đo nó soi dân]{.ttl} [MŨI NHỌN NIỀM TIN]{.tag .t-violet}
:::

#### Vấn đề chưa ai giải

`citation_validator.py:65` check **substring**: quote có nằm trong
`noi_dung` không. Điều đó chỉ chứng minh **trích dẫn có thật** ---
**không** chứng minh trích dẫn **ủng hộ câu trả lời**.

**Lỗ hổng cụ thể:** LLM hoàn toàn có thể trích đúng nguyên văn một
Khoản, rồi kết luận **ngược lại** nó:

    Answer:   "Bạn KHÔNG bị phạt nếu nồng độ cồn dưới 0.25 mg/l."
    Citation: "Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển
               xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn..."   ← trích ĐÚNG nguyên văn

    → substring check: PASS ✓     (quote có thật trong Neo4j)
    → nhưng câu trả lời SAI HOÀN TOÀN, và citation đang chứng minh điều ngược lại

Đây là hallucination **tinh vi hơn** loại bịa citation, và substring
check **mù hoàn toàn** trước nó. Nó cũng nguy hiểm hơn: câu trả lời
**trông có căn cứ**.

#### Nguyên liệu đã có sẵn

**Nhóm đã có sẵn NLI model** --- `intelligence/nli.py`, viết cho MXH,
chất lượng tốt, fail-safe đúng. **Dùng lại chính nó cho QA.**

    # Sau khi LLM trả answer + citations:
    claims = tach_claim_atomic(answer)            # LLM hoặc rule-based

    for claim in claims:
        ho_tro = False
        for cit in citations:
            khoan = neo4j.get_khoan(cit.khoan_id)              # nguyên văn, source of truth
            kq = await nli.predict(premise=khoan.noi_dung,     # ← đúng model dùng cho MXH
                                   hypothesis=claim)
            if kq.label == "khop" and kq.score >= threshold:
                ho_tro = True; break
        if not ho_tro:
            return refuse(f"Không tìm được căn cứ cho: {claim}")

    # citation_faithfulness_score THẬT — thay cho score: 0.95 hardcode hiện tại

::: demo
**Khoảnh khắc demo:** Ép LLM trả lời sai có trích dẫn thật (prompt
injection nhẹ, hoặc dùng model yếu).\
→ Substring check: **PASS** ✓ --- \"citation hợp lệ\"\
→ NLI entailment: **mau_thuan** ✗ --- \"citation đang nói ngược lại câu
trả lời\"\
→ Hệ thống **tự chặn câu trả lời của chính mình** và refuse.
:::

::: why
**Vì sao đột phá:**

-   **Nó hợp nhất hai module rời rạc thành một nguyên lý.** NLI cho MXH
    và validator cho QA hiện là hai thứ không liên quan. Sau thay đổi
    này, cả hai trả lời **cùng một câu hỏi**: *\"phát biểu này có được
    quy định kia ủng hộ không?\"* --- dù phát biểu đến từ người dân trên
    Facebook hay từ chính AI.
-   **Luận điểm đạo đức mạnh nhất của cả dự án:** *\"Hệ thống áp dụng
    lên câu trả lời của chính nó đúng thước đo nghiêm khắc mà nó áp lên
    phát ngôn của người dân.\"* Một AI gắn nhãn `mau_thuan` cho bài đăng
    của dân, thì cũng phải chấp nhận bị gắn `mau_thuan` cho câu trả lời
    của mình. Đây là câu bạn nên nói trong buổi bảo vệ.
-   **Chi phí thấp nhất trong 3 ý tưởng** --- reuse code đã viết xong và
    đã có test.
-   Nó cho ra **metric thật** cho đúng tiêu chí chấm của đề bài (\"tỷ lệ
    citation đúng trong Q&A\"), thay cho `score: 0.95` hardcode.
:::

### Vì sao đúng ba ý tưởng này, và vì sao chúng thuộc về nhau {#vì-sao-đúng-ba-ý-tưởng-này-và-vì-sao-chúng-thuộc-về-nhau style="margin-top:44px"}

::: tblwrap
  Ý tưởng                        Chứng minh điều gì                                         Dùng thứ có sẵn                   Vector search làm được?
  ------------------------------ ---------------------------------------------------------- --------------------------------- ---------------------------------------
  **01 · Time-Travel**           KG là **cần thiết**, không phải trang trí                  `ngay_hieu_luc`, `THAY_THE`       **Không** --- cần traversal
  **02 · Clarity Index**         Sản phẩm phục vụ **ai** --- và đạo đức sinh ra tính năng   `DOI_CHIEU.label`, pipeline BE2   **Không** --- cần aggregate quan hệ
  **03 · Entailment Citation**   Hệ thống **đáng tin**, và tự soi mình                      `nli.py`, `citation_validator`    **Không** --- cần nguyên văn từ Neo4j
:::

Ba ý tưởng kể **một câu chuyện duy nhất**, không phải ba tính năng rời:
*knowledge graph không phải để trang trí slide --- nó cho phép trả lời
**đúng thời điểm** (01), nghe ngược lại từ **xã hội** (02), và **tự kiểm
chứng** chính mình (03). Ba việc mà không hệ RAG pháp luật nào hiện nay
làm được.*

## [5.]{.num}Gợi ý bổ sung & cách đo {#goiy}

### Ý tưởng hạng A --- làm nếu còn dư sức

::: card
### G1 · \"Luật của tôi\" --- nghĩa vụ theo vai [Citizen]{.tag .t-blue}

KG đã có `ChuThe` + `AP_DUNG_CHO` +
`NghiaVu`/`QuyenLoi`/`HanhViCam`/`ThoiHan`/`CheTai` --- **chưa dùng gì
cho Citizen**.

Người dân nhập vai: *\"tôi là chủ quán ăn ở Hà Nội\"* → LLM map sang
`ChuThe` nodes → Cypher traverse ngược `AP_DUNG_CHO` → ra **đúng nghĩa
vụ + thời hạn + chế tài áp dụng cho vai đó**, mỗi mục kèm citation.

**Deliverable:** checklist tuân thủ cá nhân hóa, có deadline lấy từ
`ThoiHan` → xuất ra lịch. **Biến \"tra cứu luật\" thành \"biết tôi phải
làm gì\"** --- đây là thứ người dân thật sự cần, và lại là graph
traversal thuần túy.
:::

::: card
### G2 · Dự báo hiểu lầm trước khi lan [Admin]{.tag .t-blue}

Khi luật mới ingest xong, **trước khi có bài MXH nào**: LLM sinh N
\"cách hiểu sai có khả năng xảy ra\" cho mỗi Khoản (few-shot bằng chính
các cụm hiểu lầm thật từ những luật cũ tương tự --- dữ liệu từ ý tưởng
02). Soạn sẵn đính chính, để ở trạng thái `draft`.

Khi bài MXH thật xuất hiện khớp cụm đã dự báo → **đính chính đã nằm sẵn
đó**, cán bộ chỉ việc duyệt. **Tiêu chí chấm có \"thời gian triage Alert
→ đề xuất đính chính\" --- ý tưởng này đưa nó về gần bằng 0.** Tấn công
trực tiếp một tiêu chí chấm.
:::

::: card
### G3 · Đường dẫn liên kết giải thích được [Module 5]{.tag .t-blue}

Module 5 được đề bài đánh giá \"Rất cao\" và gọi là **\"nút thắt lớn
nhất\"**. Khi link `BaiDang → Khoan`, hiện chỉ có `score` + `method` ---
một con số không ai kiểm chứng được.

Thêm **đường đi thật trên graph**: *\"Bài này nói \'uống 1 lon bia\' →
ChuDe \'nồng độ cồn\' → LIEN_QUAN → Điều 6 Khoản 6\"*. Lưu ý:
`graph_paths` hiện lấy từ **output LLM** (`qa_service.py:83`) --- tức là
**bịa**, và vi phạm nguyên tắc \"Graph chỉ từ Neo4j\"
(`SYSTEM_BACKEND.md:329`). Lấy thật từ Cypher vừa sửa lỗi vừa thành tính
năng.
:::

### G4 · Cách đo --- vấn đề cấp bách nhất về mặt khoa học

::: {.card .amber}
**Gold set hiện tại vô dụng để đo chất lượng.** Nó sinh máy móc:
hypothesis nhãn `khop` **giống hệt chuỗi** premise, `khong_ro` là **một
câu duy nhất lặp 6 lần**. Một model trả về `khop` khi hai chuỗi giống
nhau sẽ đạt điểm cao --- mà đó chỉ là so sánh chuỗi, không phải NLI.
**Mọi con số precision/recall đo trên gold này đều không có ý nghĩa.**

**Hai việc, theo thứ tự:**

1.  **Adversarial eval suite (làm được ngay, giá trị cao):** tự sinh câu
    hỏi bẫy để đo **refuse rate** --- thứ đo được mà không cần nhãn
    người:
    -   Hỏi về điều khoản **không tồn tại** → phải refuse
    -   Hỏi mơ hồ giữa **2 phiên bản** luật → phải hỏi lại mốc thời gian
        (nối ý tưởng 01)
    -   Hỏi **ngoài phạm vi** 20 Khoản seed → phải refuse
    -   Câu trả lời đúng nhưng **citation nói ngược** → phải bị chặn
        (nối ý tưởng 03)

    **Đo được mà không cần nhãn người** --- và đo đúng thứ có thể đem đi
    thi: hệ thống biết nói \"tôi không biết\".
2.  **Gold set người gán nhãn (bắt buộc nếu đi tiếp):** ≥200 mẫu, ít
    nhất 2 annotator, đo inter-annotator agreement (Cohen\'s κ). Không
    có cái này thì không ai --- kể cả nhóm --- biết hệ thống tốt hay dở.

[Lưu ý: `scripts/eval_be2_gold.py:41` đọc
`Data/seed/van_ban_mau/*.cypher` bằng đường dẫn sai --- sửa trước khi
chạy.]{.muted}
:::

## [6.]{.num}Chiến lược trình bày & roadmap {#huongphattrien}

::: {.card .green}
### Ba điều nên nhấn khi bảo vệ

1.  **Demo Time-Travel** --- cùng câu hỏi, hai mốc thời gian, hai câu
    trả lời đúng, mỗi câu cite đúng phiên bản. Rồi nói: *\"Đây là lý do
    chúng em cần knowledge graph. Vector search không làm được điều này
    --- nó không biết luật nào thay thế luật nào.\"*
2.  **Demo AI tự chặn mình** --- citation có thật nhưng nói ngược, hệ
    thống refuse. Rồi nói: *\"Chúng em áp lên câu trả lời của AI đúng
    thước đo mà chúng em áp lên phát ngôn của người dân.\"*
3.  **Demo Heatmap mù mờ** --- điều khoản nào bị hiểu sai nhiều nhất.
    Rồi nói: *\"Nguyên tắc không phán đúng/sai ban đầu trông như một hạn
    chế. Nhưng chính nó cho phép chúng em đo được điều ngược lại: luật
    nào đang viết chưa đủ rõ.\"*
:::

::: {.card .amber}
### Ba thứ phải xóa trước khi nộp

Không phải vì chúng là bug, mà vì **chúng đọc như gian lận** --- thiệt
hại lớn hơn nhiều so với thừa nhận chưa làm xong:

1.  **Cheat keyword** `qa_service.py:89` --- hệ thống tự bịa citation
    khi thấy chữ \"bịa\"/\"hallucinate\" để test pass.
2.  **\"Bảo mật cấp độ 3\" / \"E2EE\"** ở màn Login --- trong khi
    password không hề được đọc.
3.  **`status:"queued"`** ở ingest --- không có gì trong hàng đợi, API
    không enqueue job nào.
:::

### Roadmap

::: tblwrap
  Giai đoạn           Việc                                                                                                                                                 Giá trị
  ------------------- ---------------------------------------------------------------------------------------------------------------------------------------------------- -------------------------------------------------------------------------------------------------------------------------
  **Điều kiện cần**   Sửa L1--L4: `Depends()`, requirements + pytest.ini, RAG thật, xóa cheat.                                                                             **Mọi ý tưởng ở mục 4 đều dựng trên RAG chạy thật.** Không có bước này thì không có gì cả.
  **Mũi nhọn**        Ý tưởng 03 (entailment citation) → 01 (time-travel) → 02 (clarity index).                                                                            Thứ tự theo chi phí tăng dần. 03 rẻ nhất (reuse `nli.py`), 02 cần dữ liệu MXH đủ nhiều để aggregate có nghĩa.
  **Ngay sau**        Hoàn thiện BE1: NER thật qua LLM schema-locked (`extract_khoan.schema.json` đã có sẵn), Neo4j legal writer, Qdrant upsert, lineage.                  Mở khóa toàn bộ giá trị --- hiện KG chỉ có 20 Khoản seed. Ý tưởng 02 cần nhiều luật thật mới có ý nghĩa thống kê.
  **Ngắn hạn**        Gold set người gán nhãn (≥200 mẫu, 2 annotator, đo κ). Bỏ `Fake*` khỏi `deps.py` → cờ `USE_FAKES`. Bỏ \~30 chỗ `except: pass`. Prometheus metrics.   Không có gold thật thì mọi số đều vô nghĩa. Không bỏ Fake thì không vận hành được (không phân biệt DB chết vs DB rỗng).
  **Trung hạn**       Module 5 với dữ liệu thật + tuning threshold. Adapter Facebook/YouTube (tôn trọng ToS).                                                              Đề bài đánh giá \"Rất cao\", gọi là \"nút thắt lớn nhất\". Làm tốt phần này là làm được thứ chưa ai làm.
  **Dài hạn**         Semantic cache, rate limit, signed URL thật, MinIO, retention, CI/CD.                                                                                Vận hành production. Chưa cấp thiết khi lõi chưa chạy.
:::

------------------------------------------------------------------------

::: {.card .violet}
### Việc cần làm, theo thứ tự {#việc-cần-làm-theo-thứ-tự style="margin-top:0"}

1.  **Sửa L1--L4** --- `Depends()`, requirements + pytest.ini, RAG thật,
    xóa cheat `qa_service.py:89`. Điều kiện cần: không có bước này thì
    không có gì để demo.
2.  **Xóa thứ đọc như gian lận** --- cheat keyword ở `qa_service.py:89`,
    dòng \"E2EE\"/\"Bảo mật cấp độ 3\" ở Login, nhãn \"Thông tin chính
    xác\" ở `RiskBadge`. Bị bắt gặp thiệt hại lớn hơn thừa nhận chưa
    làm.
3.  **Làm ý tưởng 03 → 01 → 02** --- theo chi phí tăng dần.

**Câu hỏi giám khảo chắc chắn sẽ hỏi: \"Sao phải dùng knowledge graph?
Sao không vector search cho nhanh?\"** Hiện tại hệ thống **không có câu
trả lời** --- gỡ Neo4j ra thì mọi thứ chạy y hệt. Ba ý tưởng ở mục 4 tồn
tại để trả lời đúng câu đó, và mỗi ý tưởng đều là thứ vector search **về
nguyên tắc không làm được**.
:::

Báo cáo lập ngày 17/07/2026 · Rà soát dựa trên đọc toàn bộ mã nguồn +
chạy kiểm chứng thực tế trên commit `c093305`
:::
