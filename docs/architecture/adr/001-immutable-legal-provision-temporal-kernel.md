# ADR-001: Immutable legal provision versions and one temporal kernel

## Status

Proposed

## Context

CMC currently identifies and overwrites legal content mainly at document/Khoản level. A partial amendment can change one Điểm while sibling provisions remain effective. Filtering only by document dates cannot answer accurately what the law said on a specific date.

Constraints:

- Keep existing `Dieu`, `Khoan`, `Diem` labels and API compatibility for one release.
- Neo4j Community Edition is the graph store.
- Migration must be additive and rollback must not delete data.
- The five-person team should not adopt event sourcing or a new database in this release.

## Options considered

| Option | Advantages | Disadvantages | Complexity |
|---|---|---|---|
| Mutate existing nodes | Small code change | Destroys history; cannot support as-of queries | Low |
| Duplicate complete documents per amendment | Easy snapshot reasoning | Large duplication; partial amendments are hard to link | Medium |
| Immutable versions per provision | Exact partial history; fine-grained citation | Requires lineage, interval invariants and migration | Medium |
| Full bitemporal/event-sourced model | Strong audit semantics | Too complex for current product/team | High |

## Decision

Use immutable versions at Điều/Khoản/Điểm level. Add common label `LegalProvision`, stable `lineage_id`, immutable `provision_id`, `effective_from`, exclusive `effective_to`, checksum and `SUPERSEDED_BY`.

All reads involving dates must use `TemporalLawService`. Existing IDs remain compatibility aliases; migration does not rewrite them.

## Rationale

- It directly solves partial amendment and historical question requirements.
- It preserves current labels and stack.
- It is materially simpler than full event sourcing while retaining the legal history needed by the product.
- One temporal service prevents divergent date logic in QA, social checks and APIs.

## Trade-offs

- Queries and migrations become more complex.
- Multiple versions can share the same parent lineage.
- Graph storage grows with amendments.

These costs are accepted because correctness at provision level is a core requirement. They are mitigated with interval indexes, fixtures, additive migration and a single repository/service boundary.

## Consequences

- Parser and writer must preserve Điểm and checksum every node.
- Amendment commit becomes the only path allowed to close an effective interval.
- QA cache keys must include the temporal graph revision and `as_of`.
- Acceptance tests must cover partial changes, future rules, repeal and multi-version chains.

## Revisit trigger

Reconsider full bitemporal storage only when the product must answer both “law valid at date X” and “what the system knew at date Y”, or when correction/audit requirements cannot be represented by `recorded_at` plus immutable nodes.
