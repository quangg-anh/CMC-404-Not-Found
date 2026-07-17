# BE2 — Social & Intelligence (Người Backend 2/3)

> Phân công tổng: `TEAM_ASSIGNMENT.md`  
> Contract: `Backend/SYSTEM_BACKEND.md` · Data: `Data/SYSTEM_DATA.md`  
> Module sở hữu: **3 (MXH topic), 5 (link bài↔Khoản), 6 (NLI), 9a (Brief generate), 9b (Suggest)** + **LLM Router + Embedding**

---

## 1. Sứ mệnh

1. Sở hữu **tầng Intelligence**: embedding, 9R-Shield LLM router, NLI, rerank.  
2. Pipeline MXH: ingest → topic → link Khoản → claim check → alert signal.  
3. Sinh **draft** `BaiTomTat` và `DeXuatDinhChinh` (không tự publish / không tự đăng MXH).

BE2 **không** làm: parser luật (BE1), expose FastAPI/Auth/PublishGate (BE3), UI (FE).

---

## 2. Hệ thống / thư viện BẮT BUỘC

| Hệ thống | Chi tiết dùng |
|---|---|
| Python 3.11+ | `app/intelligence/`, `app/pipelines/social/`, `app/pipelines/content/` |
| **sentence-transformers** / TEI | Model `bge-m3` hoặc `keepitreal/vietnamese-sbert` |
| **Qdrant** | Collection `khoan`, `baidang`, `chude` |
| **Neo4j** | Ghi BaiDang, ChuDe, YKien, cạnh link (đúng schema) |
| **Redis + Arq/Celery** | Worker social + generate |
| **httpx** | Gọi LLM gateway local + cloud |
| **9R-Shield** (gateway nội bộ) | Route local Gemma vs model lớn theo policy |
| **NLI** (vd. mDeBERTa / model VN tương đương) | `premise=Khoản`, `hypothesis=claim` |
| Facebook Graph API / YouTube Data API | Phase B — có API key, rate limit |
| Pydantic v2 | Schema brief/suggest/claim labels |
| Postgres | AlertMeta meta, draft brief/suggest status (hoặc qua BE3 repo) |
| pytest + gold set | `Data/gold/links.json`, `Data/gold/nli.json` |

---

## 3. Phạm vi code

```
Backend/app/
  intelligence/
    embedder.py           # embed batch
    llm_router.py         # 9R-Shield policy
    nli.py                # khop|mau_thuan|khong_ro
    rerank.py             # LLM hoặc cross-encoder
  pipelines/social/
    ingest.py
    topic_classify.py
    entity_link.py        # retrieval 2 tầng + ChuDe trung gian
    claim_check.py
    alert_signal.py
  pipelines/content/
    brief_generate.py
    suggest_generate.py
  workers/
    social_jobs.py
    content_jobs.py
```

---

## 4. Chính sách LLM Router (BE2 sở hữu)

| Tín hiệu | Route |
|---|---|
| Parse lệch nhẹ / extract ngắn | local Gemma |
| NER/RE Khoản phức tạp | large (schema-locked) |
| Re-rank bài–Khoản | large |
| QA / Brief / Suggest | large **chỉ** trên context đã retrieve |
| Output không match JSON schema | retry 1 lần → `needs_review` |

API nội bộ tối thiểu cho BE1/BE3:

```text
embed_texts(texts: list[str]) -> list[vector]
llm_complete(task, prompt, schema, complexity) -> dict
nli_pair(premise, hypothesis) -> {label, score}
rerank(query, candidates) -> ordered_ids
```

---

## 5. Việc cụ thể (checklist)

### Phase A

- [ ] Embedder chạy được; collection `khoan` nhận vector từ BE1
- [ ] LLM router + health check gateway
- [ ] Document policy + timeout/retry cho team

### Phase B — MXH

- [ ] Social ingest (API/webhook) → normalize, hash PII, dedupe `(platform, external_id)`
- [ ] Topic classify zero-shot embedding → gắn `ChuDe`
- [ ] Link 2 tầng: vector top-k Khoản (theo ChuDe) → LLM re-rank
- [ ] **Invariant:** không tạo `GAN_CO_CAN_KIEM_CHUNG` dưới threshold / chưa qua ChuDe
- [ ] Claim extract → NLI → label `khop|mau_thuan|khong_ro` + confidence
- [ ] Alert signal khi `mau_thuan` + confidence cao + volume (ghi AlertMeta)
- [ ] `POST` logic hỗ trợ `/admin/link/preview` (dry-run, không ghi DB nếu flag)

### Phase C — Content

- [ ] `brief_generate`: từ Khoản/VB/diff → title, bullets bình dân, citations[] — validate substring
- [ ] Status draft only; publish do BE3 PublishGate
- [ ] `suggest_generate`: cluster alert cùng ChuDe+Khoản → draft đính chính + disclaimer
- [ ] Không có hàm auto-post Facebook/TikTok

---

## 6. Contract với người khác

| Đối tác | BE2 đưa | BE2 nhận |
|---|---|---|
| **BE1** | `embed_texts`, `llm_complete` ổn định | Khoản đã có trong Neo4j+vector để link |
| **BE3** | Service functions + job names; không tự mount route | Expose API social/briefs/suggestions; PublishGate |
| **DB** | Yêu cầu collection/index MXH | Schema cạnh MXH, threshold config table |
| **FE** | — | UI wording nhãn khớp BE; CTA Suggest = copy/export |

---

## 7. Job names

| Job | Input | Output |
|---|---|---|
| `social_ingest` | payload MXH | BaiDang |
| `social_topic` | bai_dang_id | ChuDe + score |
| `social_link` | bai_dang_id | edges + scores |
| `social_claim` | bai_dang_id | YKien + DOI_CHIEU |
| `alert_fanout` | thresholds | AlertMeta |
| `brief_generate` | van_ban_id / khoan_ids / diff_id | BaiTomTat draft |
| `suggest_generate` | alert_ids | DeXuatDinhChinh draft |

---

## 8. Tiêu chí Done BE2

- Router có policy test (local vs large) + không lộ key trong repo.  
- Link precision@k trên `Data/gold` đạt ngưỡng team.  
- NLI không bao giờ trả label ngoài bộ 3.  
- Brief draft fail nếu citation không phải substring Khoản.  
- Suggest luôn kèm disclaimer nội bộ trong payload.

---

## 9. Ethics (bắt buộc)

- Không field `is_fake=true` tuyệt đối.  
- Hash/ẩn tác giả MXH khi không cần.  
- Tôn trọng ToS & rate limit từng nền tảng.  
- Log mọi lần gọi LLM (task, tokens, model) phục vụ chi phí.
