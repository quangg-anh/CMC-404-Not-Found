# ADR-003: Deterministic-first amendment matching with human-reviewed commit

## Status

Proposed

## Context

`version_diff.py` currently produces token diffs but does not determine legal lineage, effectivity or impact. Automatically linking the wrong old/new provision would corrupt historical answers and citations.

## Options considered

| Option | Advantages | Disadvantages | Complexity |
|---|---|---|---|
| LLM-only pairing and commit | Fast prototype | Non-deterministic; difficult to audit; unsafe | Low initially |
| Deterministic rules only | Explainable | Misses renumbering and semantic rewrites | Medium |
| Hybrid matching + review gate | Better recall with explicit safeguards | Requires review workflow and gold set | Medium–High |
| Manual-only linking | Highest control | Slow; does not scale | Low code, high operations |

## Decision

Use deterministic-first hybrid matching:

1. Explicit legal references.
2. Structural number/title match.
3. Lexical and extracted-entity similarity.
4. Embedding and cross-reference overlap for unresolved candidates.

Persist proposals in PostgreSQL. Only approved candidates may be committed to Neo4j. Split, merge and uncertain cases always require review. Automatic approval is disabled until gold-set pairing precision reaches at least 95%.

## Rationale

- Incorrect temporal edges are more damaging than missing automated links.
- The existing Admin Portal can host the review queue.
- Score components and source references make decisions auditable.
- The approach can improve incrementally without changing the graph contract.

## Trade-offs

- Some amendments remain pending and historical coverage is incomplete until reviewed.
- Review UI and persistence add implementation work.
- High precision targets may reduce automatic recall.

These are accepted in favor of legal-data integrity. Coverage gaps are visible as `needs_review`; they must not be silently inferred.

## Consequences

- Matching, classification and graph commit are separate modules.
- Dry-run/preview cannot mutate Neo4j.
- Commit must be transactional, idempotent and checksum-guarded.
- Evaluation reports must publish pairing precision/recall, review rate and errors by change type.

## Revisit trigger

Raise automation only after an independently labeled gold set shows stable precision across multiple document families. Lowering the threshold requires a new ADR or explicit approval with measured risk.
