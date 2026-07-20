# LAWGIC Core Research

## Overview

Nâng CMC từ legal RAG cấp Khoản/văn bản thành lõi pháp lý có version bất biến ở Điều–Khoản–Điểm, truy vấn theo ngày, citation claim-level và phát hiện thông tin từng đúng nhưng đã lỗi thời.

## Source documents

- `docs/architecture/lawgic-core-implementation-plan.md`: phân tích baseline và roadmap nền.
- `docs/architecture/lawgic-core-execution-plan-v2.md`: kế hoạch thực thi hiện hành.
- `docs/architecture/adr/`: quyết định và đánh đổi kiến trúc.

## Confirmed code findings

- `LegalParser` nhận `diem_list`, nhưng `_build_tree()` làm mất danh sách này.
- Neo4j writer hiện ghi đè `Khoan.noi_dung` và chưa ghi `Diem`.
- QA time travel lọc ở cấp văn bản nên không biểu diễn partial amendment.
- Citation validator còn có thể tin nguồn preloaded thay vì luôn hydrate Neo4j.
- `version_diff.py` mới tạo token diff, chưa có lineage hoặc commit workflow.

## Recommended approach

Giữ modular monolith và stack hiện tại. Bổ sung additive contract/version fields, dual-write có feature flag, một TemporalLawService duy nhất, Neo4j canonical/Qdrant ID-only và amendment human review trước khi commit graph.

## Risks

Raw source của văn bản cũ có thể đã mất Điểm sau ingest. Migration chỉ được report và re-ingest từ raw/MinIO; không được tự dựng lại nội dung pháp luật.
## PR-L1.2 transaction research

Neo4j managed write transactions có thể tự retry callback, nên callback phải idempotent và không dựa vào side effect ngoài transaction. `MERGE` cần đi cùng uniqueness constraints để khóa định danh và ngăn node trùng.

Quyết định triển khai:

- Dùng `AsyncSession.execute_write()` cho toàn bộ Văn bản–Điều–Khoản–Điểm.
- Khi `LEGAL_PROVISION_V2_WRITE=true`, writer v2 ghi đồng thời trường tương thích v1 và contract v2 trên cùng node; không chạy writer v1 mutable sau đó.
- Preflight phát hiện collision trước mutation; Cypher có guard lần hai để chặn race giữa hai transaction.
- Re-ingest cùng identity/checksum/interval/source là idempotent.
- Ingest thường không được thay `effective_from`, `effective_to`, source document hoặc source checksum.
- `dry_run=True` trả count/conflict nhưng không ghi; inventory migration toàn kho vẫn thuộc Phase L2.

Nguồn chính thức:

- Neo4j Python Driver — managed transactions và yêu cầu transaction function idempotent: https://neo4j.com/docs/python-manual/current/transactions/
- Neo4j Cypher Manual — `MERGE` và khuyến nghị dùng uniqueness constraints: https://neo4j.com/docs/cypher-manual/current/clauses/merge/
- Neo4j Cypher Manual — constraints: https://neo4j.com/docs/cypher-manual/current/schema/constraints/

## Phase L2 Qdrant research

Official Qdrant documentation confirms that point loading/upsert operations are idempotent and UUID point IDs are supported. Payloads are JSON metadata and payload indexes should be created for fields used by filters.

Implementation decisions:

- Use UUID5(provision_id) so retries overwrite the same point instead of creating duplicates.
- Keep canonical legal text in Neo4j. The v2 Qdrant payload contains identity, temporal metadata and checksum only; text_preview is opt-in debug data.
- Index the deepest available leaf: Point, otherwise Clause, otherwise Article.
- Store effective dates as RFC 3339 midnight timestamps so Qdrant datetime indexes can filter them later.
- Resume checks compare both provision_id and text_checksum; a stale checksum is reindexed.
- Graph migration inventory is read-only in this phase. Missing Point coverage is reported as unverified and requires raw-source review, never guessed from legacy data.

Primary sources:

- Qdrant points and idempotent loading: https://qdrant.tech/documentation/concepts/points/
- Qdrant payload metadata: https://qdrant.tech/documentation/concepts/payload/
- Qdrant payload indexes: https://qdrant.tech/documentation/manage-data/indexing/
- Qdrant collection vector contract: https://qdrant.tech/documentation/manage-data/collections/
## Phase L3 temporal read research

Neo4j temporal values can be compared directly after normalization with `date()`, and managed read transactions are the supported retryable read path in the async Python driver. Variable-length graph traversal is not required for `law_as_of`: effective versions are selected by indexed fields, while timeline edges are loaded only for chain validation.

Implementation decisions:

- Use half-open intervals: `effective_from <= as_of < effective_to`.
- Select deepest effective leaves with stable `parent_lineage_id`, so physical version edges do not control leaf semantics.
- Fail closed when more than one version in a lineage is active on the same date, when timeline intervals overlap, or when `SUPERSEDED_BY` contains a cycle.
- Citizen reads require both `visibility=public` and `review_status=approved`.
- Hydrate stale Qdrant physical IDs through lineage to the active Neo4j version before later citation work.
- Keep v1 QA unchanged in L3; temporal APIs require both `LEGAL_PROVISION_V2_READ` and `TEMPORAL_LAW_V2`, which remain off by default.

Primary sources:

- Neo4j Python Driver managed transactions: https://neo4j.com/docs/python-manual/current/transactions/
- Neo4j temporal values and types: https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/
- Neo4j temporal comparison: https://neo4j.com/docs/cypher-manual/current/values-and-types/ordering-equality-comparison/
## Phase L4A hybrid retrieval research

Neo4j and Qdrant both recommend treating full-text/vector result scores as local to their own result set. The v2 retrieval layer therefore performs application-side Reciprocal Rank Fusion (RRF) over independently ranked sources instead of comparing raw Lucene and cosine scores.

Implementation decisions:

- Retrieval sources return only `provision_id`, `lineage_id`, local rank/score and diagnostics; they never supply canonical quote text.
- Exact provision/lineage identifiers and document numbers are strict and fail closed when missing; they do not fall through to semantic search.
- Neo4j full-text and Qdrant vector searches run independently and are fused by lineage so multiple historical physical versions cannot boost one rule unfairly.
- Graph expansion is bounded to two hops and uses an allowlist of structural/version relationships.
- Every fused candidate is batch-hydrated through `TemporalLawService.hydrate_candidates()` before text can reach a caller.
- Citizen visibility is enforced as `public + approved` in Neo4j/Qdrant discovery and again during canonical temporal hydration.
- The initial reranker is a deterministic token-overlap baseline; model-based reranking remains optional until an ablation report justifies it.
- Five profiles are measurable without changing production QA: lexical, vector, hybrid, hybrid+graph, hybrid+graph+reranker.

Primary sources:

- Qdrant hybrid queries and RRF: https://qdrant.tech/documentation/search/hybrid-queries/
- Qdrant filtering and datetime ranges: https://qdrant.tech/documentation/search/filtering/
- Neo4j full-text indexes and score semantics: https://neo4j.com/docs/cypher-manual/25/indexes/semantic-indexes/full-text-indexes/
- Neo4j semantic indexes and hybrid ranking guidance: https://www.neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/
- Neo4j Python driver read/performance guidance: https://neo4j.com/docs/python-manual/current/performance/

## Phase L4B canonical citation and strict grounding research

The existing v1 validator accepts `preloaded_sources` as canonical text. That behavior must remain available only for the v1 path; Citation v2 must re-read exact physical provision IDs from the temporal Neo4j service and must not silently redirect a stale citation to a newer version.

Implementation decisions:

- Treat model output as an untrusted draft. Validate it with a Pydantic model that forbids extra fields, then derive every legal coordinate, checksum and effective interval from Neo4j.
- Keep model-generated citation input minimal: `citation_id`, exact physical `node_id`, `quote` and reciprocal claim IDs. The model cannot supply canonical document metadata.
- Require the cited physical node itself to be visible and effective at `as_of`; retrieval may hydrate stale candidates by lineage, but citation validation may not rewrite a stale citation.
- Require exact normalized quote containment and recompute the legal-text checksum before building `CitationV2`.
- Validate every declared claim-citation edge with NLI. One supported citation cannot make a second unsupported edge valid.
- Require all material numeric, deadline, rate, prohibition and penalty statements in the answer to be represented by a validated claim.
- Return a strict `refused` contract on malformed output, fabricated/off-date nodes, wrong quotes, unsupported claims or unavailable canonical validation.
- Keep Citation v2 uncached initially and behind `QA_CITATION_V2`; v1 response shape and cache remain unchanged while the flag is false.

Primary sources:

- Pydantic validation and validation errors: https://docs.pydantic.dev/2.12/errors/usage_errors/
- OpenAI Structured Outputs / JSON Schema contract: https://platform.openai.com/docs/api-reference/evals/deleteRun
- OWASP LLM09:2025 Misinformation and continuous validation risk: https://genai.owasp.org/llmrisk/llm092025-misinformation/
## Phase L4C frontend contract research

Citation v2 changes the response from the legacy flat answer/citation shape to an explicit `answered | refused` contract. The frontend therefore normalizes both contracts at one boundary instead of spreading version checks across Citizen, Admin and the floating chat.

Implementation decisions:

- Detect v2 only from the explicit `status` contract and keep the v1 `khoan_id` alias readable for one rollout period.
- Render v2 metadata from canonical response fields: physical node, Điều/Khoản/Điểm, effective interval, `as_of`, claim-support status, entailment score and Neo4j validation source.
- Treat `refused` as a first-class safe state with a public explanation and optional technical reason code; never render it as an empty or low-confidence answer.
- Add public read-only timeline/compare endpoints that still enforce the temporal feature flags and `public + approved` service filter.
- Use one shared history panel for Citizen/Admin. It unmounts when closed, resets state when the citation changes, focuses the close button, traps Tab focus, supports Escape and restores previous focus.
- Keep all v2 rollout flags off. L4C changes response rendering only and does not switch production QA.

Primary sources:

- W3C WAI-ARIA modal dialog pattern and keyboard/focus requirements: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- React state preservation/reset behavior for conditionally rendered components: https://react.dev/learn/preserving-and-resetting-state
## Phase L5.1 amendment preview research

Vietnamese amending instruments commonly identify targets explicitly at Article, Clause and Point level, and may replace a quoted phrase inside that target. The preview engine therefore treats explicit legal coordinates and quoted text as review evidence, never as permission to mutate canonical provisions.

Python `difflib.SequenceMatcher` produces a deterministic similarity signal and edit opcodes, but its result is not legal meaning. L5.1 uses it only as one bounded scoring/diff feature; numeric and legal-language direction rules stay conservative, while ambiguous changes remain `UNCERTAIN`.

Implementation decisions:

- Parse the deepest complete Article/Clause/Point target without inventing missing parents.
- Canonically hydrate every immutable old/new candidate ID from Neo4j before scoring.
- Validate quoted replacement phrases against canonical old/new text and require mandatory review on mismatch.
- Keep matching explainable with separate explicit-reference, coordinate, level, lexical, numeric and legal-term scores.
- Use deterministic one-to-one selection and surface possible split/merge structure instead of silently pairing every candidate.
- Represent unmatched old/new candidates as review-only `REMOVED`/`ADDED` proposals.
- Disable auto-approval and commit until an independently labeled amendment gold set reaches at least 95% pairing precision.

Primary sources:

- Python `difflib` and `SequenceMatcher`: https://docs.python.org/3.12/library/difflib.html
- Vietnam Government legal-document portal, official amending-law examples: https://vanban.chinhphu.vn/?classid=1&docid=214592&pageid=27160&typegroupid=3
- Vietnam Government legal-document portal, official decree text: https://vanban.chinhphu.vn/?docid=213327&pageid=27160
- Vietnam national legal-document database, full-text structure: https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=27134&Keyword=