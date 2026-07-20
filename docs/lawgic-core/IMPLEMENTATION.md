# LAWGIC Core Implementation Plan

## Authoritative plan

Chi tiết đầy đủ nằm tại `docs/architecture/lawgic-core-execution-plan-v2.md`.

## Completed phases: L0 + PR-L1.1 + PR-L1.2 + PR-L2.1 safe preparation

### Objective

Khóa contract và fixture trước, sau đó sửa đường parse để giữ đầy đủ Điều–Khoản–Điểm mà chưa thay đổi QA production hoặc chạy migration thật.

### Tasks

- [x] Tạo `LegalProvisionVersion` và `CitationContractV2`.
- [x] Nâng ontology/constraints additive.
- [x] Thêm feature flags mặc định an toàn.
- [x] Tạo temporal fixture V1/V2/V3 và acceptance queries nền tảng.
- [x] Sửa `_build_tree()` để giữ `diem_list`, lineage và checksum.
- [x] Thêm test contract, parser round-trip và deepest-leaf fixture.
- [x] Chạy full backend tests và compile check.

### Success criteria

- Existing behavior v1 vẫn là mặc định.
- Parser tree giữ nguyên văn và ID của mọi Điểm trong fixture.
- Contract chặn interval sai và citation reference sai.
- Không có migration apply, QA v2 read hoặc amendment commit trong phase này.

## Completion note — 2026-07-19

- Backend: 105 tests passed.
- Compile check: passed.
- Ontology v2 JSON và T01–T10 acceptance query contract: passed.
- Các cờ v2 read/write/temporal/citation/amendment mặc định tắt.
- Không chạy migration và không thay đổi production QA path.


## Phase PR-L1.2 — Immutable Neo4j writer

### Tasks

- [x] Không tạo Khoản giả cho Điều không có Khoản.
- [x] Flatten và validate Điều/Khoản/Điểm thành immutable rows.
- [x] Ghi đủ ba cấp trong một managed transaction.
- [x] Ghi đồng thời compatibility fields v1 và contract v2 trên cùng node.
- [x] Chặn checksum, source và interval collision trước mutation.
- [x] Thêm Cypher guard chống concurrent overwrite.
- [x] Thêm report `written | idempotent | dry_run | conflict | invalid` theo từng cấp.
- [x] Nối writer sau `LEGAL_PROVISION_V2_WRITE`; mặc định vẫn tắt.
- [x] Mở rộng ingest API nhận temporal metadata.
- [x] Thêm repository/pipeline tests và full regression.

### Completion note — 2026-07-19

- Backend: 116 tests passed sau khi thêm 11 test PR-L1.2.
- Compile và whitespace checks: passed.
- Không chạy migration, không bật v2 read, không tạo `SUPERSEDED_BY` trong ingest thường.
- `dry_run=True` hiện là preflight cho một parsed document; migration inventory toàn kho chưa chạy.

## Previous next phase: L2 — implemented as safe preparation below

- Tạo collection `legal_provision` ID-only payload.
- Thêm migration inventory dry-run cho dữ liệu v1, raw-source coverage và collision report.
- Thêm reindex resumable và shadow count parity.
- Chỉ xem xét migration apply sau snapshot/staging Go/No-Go 1.

## Phase PR-L2.1 - Qdrant dual-index and migration safety tooling

### Completed

- [x] Added the additive `legal_provision` collection contract with ID-only payload and datetime indexes.
- [x] Added deepest-leaf dual-index after a successful/idempotent v2 Neo4j write.
- [x] Kept the legacy `khoan` index active while `LEGAL_PROVISION_V2_READ=false`.
- [x] Added stable UUID5 point IDs and checksum-aware skip/repair behavior.
- [x] Added a read-only legacy migration inventory with raw-source/Point coverage reasons.
- [x] Added resumable reindex with `--resume-from` and optional checkpoint file.
- [x] Added identity/checksum parity reporting between Neo4j and Qdrant.
- [x] Added an additive-only collection bootstrap; it never deletes or recreates a collection.
- [x] Added unit/integration coverage and full backend regression.

### Operational commands

```text
python Backend/scripts/migrate_temporal_v2.py --output work/temporal-v2-inventory.json
python Backend/scripts/bootstrap_qdrant_v2.py
python Backend/scripts/bootstrap_qdrant_v2.py --apply --yes
python Backend/scripts/reindex_legal_provisions.py --checkpoint-file work/legal-v2-checkpoint.json
python Backend/scripts/reindex_legal_provisions.py --apply --yes --checkpoint-file work/legal-v2-checkpoint.json
python Backend/scripts/compare_legal_v1_v2.py --output work/legal-v2-parity.json
```

The inventory and parity commands are read-only. Bootstrap/reindex require explicit `--apply --yes` before mutation. No live command was executed in this phase.

### Verification - 2026-07-19

- Focused Phase L2 tests: 21 passed.
- Full backend suite: 126 passed.
- Python compile and whitespace checks: passed.
- Live/staging Neo4j and Qdrant were not mutated.
- Graph migration apply remains deferred until snapshot, inventory review and staging Go/No-Go.
## Phase PR-L3.1/L3.2 - Temporal repository, service and read-only APIs

### Completed

- [x] Added a read-only Neo4j temporal repository using managed read transactions.
- [x] Added half-open effective-date filtering at provision level.
- [x] Added `law_as_of`, `get_provision`, `resolve_version`, `timeline`, `compare_versions` and `hydrate_candidates`.
- [x] Added deepest-leaf selection based on active `parent_lineage_id` values.
- [x] Added fail-closed overlap, invalid-contract and supersession-cycle checks.
- [x] Enforced public + approved visibility for Citizen reads.
- [x] Added Admin as-of/timeline/compare APIs and Citizen as-of provision API.
- [x] Protected every new API with both v2 read and temporal feature flags.
- [x] Added repository, service, API and partial-amendment acceptance tests.
- [x] Removed references to the six intentionally deleted legacy documentation files.

### API contract

```text
GET /admin/legal/documents/{id}/as-of?date=YYYY-MM-DD
GET /admin/legal/provisions/{id}/timeline
GET /admin/legal/provisions/compare?old_id=...&new_id=...
GET /citizen/legal/provisions/{id}?as_of=YYYY-MM-DD
```

The compare endpoint uses query parameters because legal provision IDs may contain `/`; this avoids ambiguous two-ID path routing.

### Verification - 2026-07-19

- Focused L3 + temporal contract tests: 40 passed.
- Full backend suite: 157 passed.
- Python compileall and Git whitespace checks: passed.
- No live/staging Neo4j or Qdrant mutation was executed.
- `LEGAL_PROVISION_V2_READ=false` and `TEMPORAL_LAW_V2=false` remain the defaults.
- Production QA still uses v1 until the L4 citation/retrieval gates pass.

## Phase PR-L4.1 - Hybrid legal retrieval

### Completed

- [x] Added a typed retrieval contract with exact, lexical, vector, graph and reranker evidence.
- [x] Added strict exact-reference handling for provision IDs, lineage IDs and document numbers.
- [x] Added ID-only Neo4j full-text discovery and a bounded two-hop graph expansion allowlist.
- [x] Added Qdrant vector discovery with `public + approved` Citizen filtering.
- [x] Added application-side RRF by lineage; raw full-text and cosine scores are never compared directly.
- [x] Added mandatory `TemporalLawService.hydrate_candidates()` before any legal text is returned.
- [x] Added stale physical-ID resolution to the version effective at the requested date.
- [x] Added a deterministic token-overlap reranker baseline without a new model dependency.
- [x] Added five measurable profiles: `lexical`, `vector`, `hybrid`, `hybrid_graph`, `hybrid_graph_rerank`.
- [x] Added a read-only ablation harness with Recall@K, MRR and nDCG@K.
- [x] Added the `legal_provision_text_ft` Neo4j index and synchronized Qdrant `review_status` payload/index contracts.

### Retrieval safety contract

```text
source discovery (IDs only)
  -> RRF by lineage
  -> bounded graph expansion
  -> temporal Neo4j hydration at as_of
  -> optional rerank
  -> canonical LegalProvisionVersion output
```

Qdrant text is never copied into a result. An explicit legal reference that is not present returns no candidates and cannot fall through to semantic retrieval. Citizen candidates must be public and approved at discovery and hydration time.

### Read-only ablation command

```text
python Backend/scripts/eval_legal_retrieval_v2.py --gold Data/gold/legal_retrieval_v2.json --k 5 --output work/legal-retrieval-v2-report.json
```

Gold input must be a non-empty list, or an object with a `cases` list:

```json
{
  "cases": [{
    "case_id": "threshold-before-change",
    "query": "Nguong ap dung la bao nhieu?",
    "as_of": "2026-06-30",
    "audience": "citizen",
    "expected_lineage_ids": ["01/2026/ND-CP::D5.K2.Pa"]
  }]
}
```

The runner reports source errors as zero-scoring cases instead of excluding them. No benchmark result is claimed until a reviewed gold file is supplied and the command is run against an approved environment.

### Verification - 2026-07-19

- Focused retrieval/index/evaluation tests: 39 passed.
- Full backend suite: 187 passed.
- Python compileall, JSON contract parsing and Git whitespace checks: passed.
- No live/staging Neo4j or Qdrant mutation was executed.
- No v2 feature flag was enabled; production QA remains on v1.
- L4B citation wiring is deliberately not included in PR-L4.1.
## Phase PR-L4.2/L4.3 - Canonical Citation v2 and strict refusal

### Completed

- [x] Added strict untrusted draft models for claims and citation pointers with extra fields forbidden.
- [x] Added `text_checksum` to Citation v2 and validated node identity from lineage, date and checksum.
- [x] Added exact physical-version hydration that never redirects a stale citation to a newer version.
- [x] Added canonical Neo4j validation for node visibility, effective date, checksum and exact quote containment.
- [x] Restricted model citations to node IDs returned by canonical retrieval.
- [x] Added reciprocal claim/citation mapping validation and NLI validation for every declared edge.
- [x] Added hard refusal for unmapped material amounts, rates, deadlines, duties, prohibitions and penalties.
- [x] Added an isolated Citation v2 QA service using the L4A retrieval service.
- [x] Wired Admin/Citizen QA through a shared factory while preserving the v1 service when flags are off.
- [x] Required `LEGAL_PROVISION_V2_READ`, `TEMPORAL_LAW_V2` and `QA_CITATION_V2` together before dispatch.
- [x] Kept Citation v2 uncached during the validation rollout.
- [x] Extended the read-only acceptance catalog from T01-T10 to T01-T15.

### Validation order

```text
untrusted Pydantic draft
  -> retrieved-node allowlist
  -> exact physical Neo4j hydration at as_of
  -> public + approved visibility
  -> canonical text checksum
  -> exact normalized quote substring
  -> every reciprocal claim-citation edge passes NLI
  -> every material answer statement has a validated claim
  -> CitationContractV2 answered | refused
```

Retrieval may resolve a stale candidate by lineage before generation. Citation validation is stricter: the final `node_id` itself must be the physical version effective on `as_of`; it is never silently rewritten.

### Rollout contract

Citation v2 dispatch occurs only when all three settings are true:

```text
LEGAL_PROVISION_V2_READ=true
TEMPORAL_LAW_V2=true
QA_CITATION_V2=true
```

Defaults remain false. If `QA_CITATION_V2` is enabled without the two read prerequisites, QA returns `citation_v2_dependencies_disabled` and does not call the v2 delegate.

### Verification - 2026-07-20

- Focused L4B canonical/QA/temporal tests: 66 passed.
- Full backend suite: 219 passed.
- Python compileall, import smoke and Git whitespace checks: passed.
- Acceptance T11-T15 are present and covered by deterministic fixtures.
- No live/staging Neo4j or Qdrant mutation was executed.
- No feature flag was enabled in an environment; production QA remains on v1.
- Frontend CitationCard/timeline work remains L4C.
## Phase PR-L4.4 - Citation and temporal frontend

### Completed

- [x] Added a single response adapter for both legacy QA v1 and Citation Contract v2.
- [x] Added explicit UI states for `answered` and strict `refused` responses.
- [x] Upgraded `CitationCard` to show physical node metadata, Điều/Khoản/Điểm, effective interval, `as_of`, claim support and entailment score.
- [x] Kept `khoan_id` as a compatibility alias while all new rendering uses `node_id` when available.
- [x] Added expandable canonical quote display and Neo4j validation provenance.
- [x] Added a shared accessible history panel for Citizen/Admin with timeline selection and adjacent-version comparison.
- [x] Added public read-only timeline/compare routes backed by Citizen visibility filtering.
- [x] Wired the adapter into Citizen Ask, Citizen floating chat and Admin QA.
- [x] Added deterministic contract tests for answered v2, refused v2 and legacy v1.
- [x] Kept every v2 environment flag disabled.

### Verification - 2026-07-20

- Frontend response-contract tests: 3 passed.
- Frontend TypeScript + Vite production build: passed.
- Frontend lint: passed with one pre-existing Fast Refresh warning in `CitizenChrome.tsx`.
- Focused temporal/citation backend tests: 66 passed.
- Full backend suite: 219 passed.
- No live/staging data mutation or feature-flag activation was performed.

### Next phase

Phase L5 / PR-L5.1 starts the legal amendment engine: explicit-reference parsing, candidate matching and deterministic change classification. Review persistence, atomic commit and Admin approval UI remain separate slices behind `AMENDMENT_COMMIT_V2=false`.
## Phase PR-L5.1 - Amendment preview engine

### Completed

- [x] Added immutable preview contracts with a hard `commit_allowed=false` invariant.
- [x] Parsed explicit Vietnamese amendment actions, deepest Article/Clause/Point coordinates and quoted phrase replacements.
- [x] Loaded every old/new physical ID through `TemporalLawService.load_versions_by_ids()` so preview text is canonical Neo4j content.
- [x] Rejected fabricated IDs, overlapping old/new physical IDs and candidates outside the requested logical document.
- [x] Added explainable weighted matching and deterministic one-to-one selection.
- [x] Added conservative legal change classification and explicit unmatched `ADDED`/`REMOVED` review records.
- [x] Marked split, merge, uncertain, invalid-date, multi-target and phrase-mismatch results as mandatory review.
- [x] Kept all other results in human review; no result is eligible for auto-approval before the independent 95% precision gate.
- [x] Added an Admin-only preview route behind `LEGAL_PROVISION_V2_READ` and `AMENDMENT_PREVIEW_V2`.
- [x] Kept `AMENDMENT_COMMIT_V2=false`; no review persistence or graph mutation is part of this slice.

### Preview flow

```text
Admin request with immutable old/new provision IDs
  -> exact canonical Neo4j hydration
  -> logical-document boundary validation
  -> explicit amendment-reference parsing
  -> explainable score matrix
  -> deterministic one-to-one selection
  -> conservative change classification
  -> human/mandatory review preview
  -> no persistence and no graph write
```

### Verification - 2026-07-20

- Focused amendment and temporal contract tests: 59 passed.
- Full backend suite: 242 passed.
- Python compileall and Git whitespace checks: passed.
- No live/staging mutation and no feature flag activation were performed.

### Next phase

PR-L5.2 adds review persistence and Admin workflow APIs only. Transactional Neo4j interval closure and `SUPERSEDED_BY` creation remain PR-L5.3 and stay disabled behind `AMENDMENT_COMMIT_V2=false`.