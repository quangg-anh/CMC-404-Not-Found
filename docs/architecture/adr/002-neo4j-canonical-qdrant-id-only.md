# ADR-002: Neo4j canonical legal text; Qdrant returns IDs only

## Status

Proposed

## Context

Current QA retrieval can pass `CandidateKhoan.noi_dung` from vector/preloaded candidates into citation validation. If Qdrant payload is stale or altered, a quote may be validated without re-reading the canonical graph node.

## Options considered

| Option | Advantages | Disadvantages | Complexity |
|---|---|---|---|
| Trust Qdrant payload text | Lowest latency | Two sources of truth; stale citation risk | Low |
| Store canonical text in PostgreSQL | Familiar transactions | Duplicates graph source and migration work | Medium |
| Hydrate candidate IDs from Neo4j | One source of truth; exact temporal check | Additional batch query and latency | Medium |

## Decision

Qdrant is candidate discovery only. It returns `provision_id` and ranking metadata. Before prompting or validating citations, the backend batch-hydrates canonical text, visibility, checksum and effective interval from Neo4j through `TemporalLawService`.

`text_preview` may remain in Qdrant for diagnostics but must never be accepted as canonical evidence.

## Rationale

- This preserves the project’s existing source-of-truth principle.
- It makes citation validation independent of vector payload freshness.
- Batch hydration limits the latency cost and centralizes temporal filtering.

## Trade-offs

- Every grounded QA request needs a Neo4j read after retrieval.
- Neo4j availability becomes a hard dependency for legal answers.

This is accepted because legal answers should fail closed when canonical evidence is unavailable. Mitigation: batch reads, short-lived cache keyed by checksum/revision, health checks and explicit refusal reason codes.

## Consequences

- `CitationValidator` must remove canonical trust in `preloaded_sources`.
- `legal_provision` Qdrant payload must carry ID/checksum/date metadata.
- Citizen QA refuses when Neo4j is unavailable; it does not return an unverified legal answer.
- Tests must tamper with Qdrant preview and prove the citation still comes from Neo4j.

## Revisit trigger

Revisit only if measured Neo4j hydration causes unacceptable P95 latency after batching and caching. Any alternate read store must still be checksum-verifiable against the canonical graph.
