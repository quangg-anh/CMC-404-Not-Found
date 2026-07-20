# LAWGIC Core Progress

## Status: Phase L5.1 / PR-L5.1 complete — preview-only; L5.2 is next

## Quick reference

- Research: `docs/lawgic-core/RESEARCH.md`
- Implementation: `docs/lawgic-core/IMPLEMENTATION.md`
- Execution plan: `docs/architecture/lawgic-core-execution-plan-v2.md`

## Tasks completed

- Baseline code, khoảng hở, execution plan v2 và ba ADR đã được xác nhận.
- Thêm immutable `LegalProvisionVersion`, lineage/version ID, checksum và interval validation.
- Thêm `CitationContractV2` claim-level với mapping hai chiều và fail-closed refusal.
- Nâng ontology 2.0.0, constraints/index additive và quan hệ `SUPERSEDED_BY`/`AMENDED_BY`.
- Thêm feature flags v2 với read/write/temporal/citation/amendment mặc định tắt.
- Thêm temporal fixture V1/V2/V3: partial amendment, future, repeal, Khoản không Điểm và Điều không Khoản.
- Thêm acceptance query contract T01–T10.
- Sửa `_build_tree()` giữ `diem_list`, canonical ID, lineage, parent lineage và checksum.
- Hoàn thành immutable Neo4j writer cho Điều/Khoản/Điểm trong một managed transaction.
- Bỏ việc tự tạo Khoản giả cho Điều không có Khoản.
- Thêm preflight/collision report, concurrent Cypher guard và per-document dry-run.
- Nối atomic dual-schema writer sau `LEGAL_PROVISION_V2_WRITE`; default v1 không đổi.
- Mở rộng Admin ingest request nhận ngày hiệu lực và logical lineage metadata.

## Verification

- Latest full backend suite: 219 tests passed.
- Focused L4B canonical citation/QA/temporal suite: 66 tests passed.
- Python compileall: passed.
- Qdrant collection JSON contract: parsed successfully.
- Git whitespace check: passed.
- Live/staging stores were not mutated and every v2 rollout flag remains off.

## Blockers

- Không có blocker code cho Phase L2; cần snapshot/staging trước mọi migration apply.
- Sandbox Windows không chạy được công cụ sửa tệp tích hợp; các thay đổi được áp dụng bằng bản vá Git trong workspace.

## Session log

### 2026-07-19

- Bắt đầu Phase L0 + PR-L1.1.
- Hoàn thành contract, schema additive, flags, fixture, acceptance queries và parser preservation.
- Giữ scope an toàn: chưa sửa QA production, chưa chạy migration thật, chưa bật writer/read v2.
- Hoàn thành PR-L1.2; writer v2 vẫn sau feature flag và không đóng interval trong ingest thường.
- Live Neo4j migration/integration mutation chưa chạy trên dữ liệu người dùng.

## Files changed

- `Backend/app/domain/legal_provision.py`
- `Backend/app/domain/citation_contract.py`
- `Backend/app/domain/legal_write.py`
- `Backend/app/adapters/neo4j_legal_v2.py`
- `Backend/app/adapters/neo4j_legal.py`
- `Backend/app/api/admin/legal.py`
- `Backend/app/pipelines/legal/normalize.py`
- `Backend/app/pipelines/legal/pipeline.py`
- `Backend/app/config.py`
- `Backend/.env.example`
- `Backend/tests/fixtures/temporal_legal.py`
- `Backend/tests/test_legal_temporal_contracts.py`
- `Backend/tests/test_neo4j_legal_v2.py`
- `Data/schema/ontology.json`
- `Data/schema/neo4j_constraints.cypher`
- `Data/schema/acceptance_queries.cypher`

## Previous next task: Phase L2 (superseded by the update below)

- Tạo Qdrant collection `legal_provision` với ID-only payload.
- Viết migration inventory dry-run, raw-source coverage và collision report cho dữ liệu v1.
- Thêm resumable reindex và shadow parity v1/v2.
- Không chạy migration apply trước snapshot/staging Go/No-Go 1.

## Phase L2 update - 2026-07-19

Completed in code:

- Qdrant `legal_provision` v2 collection contract with ID-only payload.
- Feature-flagged deepest-leaf dual-index while legacy `khoan` remains available.
- Deterministic UUID5 IDs, checksum repair and resumable checkpoint contract.
- Read-only temporal migration inventory with per-document re-ingest reasons.
- Additive-only Qdrant bootstrap and Neo4j/Qdrant identity+checksum parity report.
- 21 focused tests and 126 full backend tests passed; compile and diff checks passed.

Not executed against live services:

- No collection create/index mutation.
- No vector reindex.
- No Neo4j migration apply.
- No v2 read-path switch.

Historical L2 rollout gate:

1. The six tracked documentation deletions were confirmed as intentional; active references were removed.
2. Take Neo4j/Qdrant snapshots in staging.
3. Run inventory and bootstrap dry-runs.
4. Review documents marked `requires_reingest` or `requires_source_review`.
5. Approve additive bootstrap/reindex, then require exact ID+checksum parity before L3.
## Phase L3 update - 2026-07-19

Completed in code:

- Read-only `Neo4jTemporalRepository` with managed transaction support and half-open interval queries.
- Canonical `TemporalLawService` with deepest-leaf selection, public visibility enforcement and immutable contract hydration.
- Fail-closed checks for duplicate active versions, invalid checksums/coordinates, interval overlap and supersession cycles.
- Stale physical candidate hydration to the active lineage version for the upcoming L4 retrieval path.
- Feature-flagged Admin as-of/timeline/compare APIs and Citizen as-of provision API.
- Dead references to the six intentionally deleted legacy documentation files were removed from active docs.

Verification:

- 40 focused L3/temporal tests passed.
- 157 full backend tests passed.
- Compileall and whitespace checks passed.
- No live or staging data mutation was performed; v2 read and temporal flags remain off.

Next phase:

1. Build hybrid retrieval over exact + lexical + Qdrant + graph candidates.
2. Hydrate every candidate through `TemporalLawService` at the requested date.
3. Connect Citation Contract v2 and strict claim-level grounding.
4. Keep Citizen rollout disabled until citation validity and refusal gates pass.
## Phase L4A start - 2026-07-19

In progress:

- Define ID-only retrieval candidates and application-side RRF by lineage.
- Add explicit-reference, Neo4j full-text, Qdrant vector and bounded graph sources.
- Require canonical temporal hydration before returning candidate text.
- Add deterministic reranker baseline and five-profile ablation harness.
- Keep QA routes and Citizen rollout unchanged until L4B/L4C grounding gates pass.

## Phase L4A completion - 2026-07-19

Completed in code:

- Typed ID-only candidate and evidence contracts for exact, lexical, vector, graph and reranker sources.
- Strict fail-closed exact lookup for physical IDs, lineage IDs and document numbers.
- Neo4j full-text discovery plus bounded two-hop graph expansion.
- Qdrant vector discovery with `public + approved` filtering.
- Application-side RRF deduplicated by lineage and mandatory temporal Neo4j hydration.
- Stale vector/full-text IDs resolve to the legal version effective at `as_of`.
- Five retrieval profiles and a deterministic reranker baseline.
- Read-only gold-set ablation with Recall@K, MRR and nDCG@K; source failures remain visible and score zero.
- Qdrant payload/bootstrap contracts now include `review_status`.

Verification:

- 39 focused L4A tests passed.
- 187 full backend tests passed.
- Compileall, JSON parsing and Git whitespace checks passed.
- No live/staging data mutation, feature-flag activation or QA route switch was performed.

Next phase — L4B:

1. Validate the existing Citation Contract v2 against canonical retrieval candidates.
2. Map answer claims to citations in both directions.
3. Enforce quote checksum, effective-date and claim-support checks.
4. Add strict refusal when any material claim lacks valid support.
5. Wire QA only behind `QA_CITATION_V2`, keeping Citizen rollout disabled until acceptance gates pass.
## Phase L4B completion - 2026-07-20

Completed in code:

- Untrusted Pydantic draft boundary for model-generated claims and citation pointers.
- Exact physical-node Citation v2 validation from Neo4j at `as_of` with no stale-ID rewrite.
- Canonical identity, coordinate, interval, text-checksum and exact-quote validation.
- Retrieval allowlist enforcement so a model cannot cite a valid but unrelated graph node.
- Per-edge NLI entailment and reciprocal claim/citation mapping.
- Strict refusal for unsupported or unmapped material legal statements.
- Isolated `LegalQAV2Service` and shared QA factory for Admin/Citizen routes.
- Three-flag dispatch gate: v2 read + temporal + citation must all be enabled.
- Read-only acceptance catalog extended through T15.

Verification:

- 66 focused L4B tests passed.
- 219 full backend tests passed.
- Compileall, import smoke and Git whitespace checks passed.
- No live/staging mutation or feature-flag activation was performed.

Next phase — L4C:

1. Add frontend response adapters that keep the v1 response readable when Citation v2 is off.
2. Render node level, Điều/Khoản/Điểm, effective interval, `as_of` and claim-support status.
3. Add timeline and compare links from CitationCard.
4. Add frontend tests/build and only then prepare a shadow-read rollout plan.
## Phase L4C completion - 2026-07-20

Completed in code:

- Shared v1/v2 QA response adapter for Citizen Ask, floating chat and Admin QA.
- Citation v2 cards with exact legal coordinates, effective interval, `as_of`, support status, entailment score and canonical-source indicator.
- Strict refusal state with readable public explanation and technical reason code where available.
- Public read-only timeline and compare endpoints that retain temporal flags and Citizen visibility filtering.
- Accessible Citizen/Admin history dialog with focus containment, Escape close, focus restoration, timeline selection and adjacent-version diff.
- Legacy `khoan_id` rendering remains compatible while v2 uses `node_id`.

Verification:

- 3 frontend contract tests passed.
- Frontend production build passed.
- Frontend lint passed with one pre-existing Fast Refresh warning.
- 66 focused backend tests passed.
- 219 full backend tests passed.
- No live/staging mutation or rollout flag activation was performed.

Next phase — L5 / PR-L5.1:

1. Parse explicit amendment targets at Điều/Khoản/Điểm level.
2. Match old/new immutable provision candidates with explainable score breakdown.
3. Classify `UNCHANGED | REWORDED | TIGHTENED | LOOSENED | ADDED | REMOVED | SPLIT | MERGED | UNCERTAIN`.
4. Keep all proposed pairs in preview/review mode; do not commit graph changes yet.
## Phase L5.1 start - 2026-07-20

Scope locked:

- Parse explicit Vietnamese amendment targets and phrase replacements.
- Load all old/new candidate texts canonically by immutable Neo4j IDs.
- Produce explainable match scores and conservative change types.
- Keep `commit_allowed=false`; no interval closure or temporal edge writes.
- Keep high-confidence proposals in human review until independent pairing precision reaches 95%.
## Phase L5.1 completion - 2026-07-20

Completed in code:

- Added strict amendment-domain contracts for explicit references, score breakdowns, diffs, paired matches and unmatched `ADDED`/`REMOVED` candidates.
- Added Vietnamese explicit amendment parsing for Article/Clause/Point targets and quoted phrase replacement.
- Added explainable one-to-one candidate matching with coordinate, lexical, numeric and legal-term signals.
- Added conservative deterministic classification for `UNCHANGED | REWORDED | TIGHTENED | LOOSENED | ADDED | REMOVED | SPLIT | MERGED | UNCERTAIN`.
- Hydrated both old and new immutable candidate IDs from the canonical temporal Neo4j boundary; cross-document or fabricated candidates fail closed.
- Required mandatory review when effective dates regress, targets are ambiguous, phrase replacements do not match canonical text, or the change is split/merge/uncertain.
- Added Admin-only `POST /admin/legal/amendments/preview` behind `AMENDMENT_PREVIEW_V2=false` and the legal v2 read flag.
- Kept `commit_allowed=false` and `auto_approve_eligible=false` for every result until independent pairing precision reaches 95%.
- Performed no interval closure, `SUPERSEDED_BY` write, live/staging mutation or feature-flag activation.

Verification:

- 59 focused amendment/temporal contract tests passed.
- 242 full backend tests passed.
- Python compileall and Git whitespace checks passed.
- The only test warning is the existing Windows pytest-cache permission warning; it does not affect test execution.

Next phase — L5.2:

1. Add PostgreSQL review-batch and candidate persistence with immutable audit fields.
2. Add Admin list/detail/edit/submit-review APIs with optimistic concurrency and idempotency.
3. Keep review persistence separate from Neo4j commit; `AMENDMENT_COMMIT_V2` remains false.
4. Build deterministic amendment gold data and measure pairing precision before any auto-approve path exists.