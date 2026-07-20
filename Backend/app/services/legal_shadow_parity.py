from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping


def build_shadow_parity_report(
    neo4j_provision_ids: Iterable[str],
    qdrant_provision_ids: Iterable[str],
    *,
    neo4j_checksums: Mapping[str, str] | None = None,
    qdrant_checksums: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Compare immutable provision identities and optional canonical checksums."""
    neo_values = [str(value) for value in neo4j_provision_ids if value]
    qdrant_values = [str(value) for value in qdrant_provision_ids if value]
    neo_counts = Counter(neo_values)
    qdrant_counts = Counter(qdrant_values)
    neo_set = set(neo_counts)
    qdrant_set = set(qdrant_counts)
    missing = sorted(neo_set - qdrant_set)
    extra = sorted(qdrant_set - neo_set)
    duplicate_neo4j = sorted(key for key, count in neo_counts.items() if count > 1)
    duplicate_qdrant = sorted(key for key, count in qdrant_counts.items() if count > 1)
    checksum_mismatches: list[str] = []
    if neo4j_checksums is not None and qdrant_checksums is not None:
        checksum_mismatches = sorted(
            provision_id
            for provision_id in neo_set & qdrant_set
            if str(neo4j_checksums.get(provision_id) or "")
            != str(qdrant_checksums.get(provision_id) or "")
        )
    exact = not (
        missing
        or extra
        or duplicate_neo4j
        or duplicate_qdrant
        or checksum_mismatches
    )
    denominator = max(len(neo_set), 1)
    return {
        "status": "match" if exact else "mismatch",
        "exact_match": exact,
        "neo4j_count": len(neo_set),
        "qdrant_count": len(qdrant_set),
        "matched_count": len(neo_set & qdrant_set),
        "coverage": round(len(neo_set & qdrant_set) / denominator, 6),
        "missing_in_qdrant": missing,
        "extra_in_qdrant": extra,
        "duplicate_neo4j_ids": duplicate_neo4j,
        "duplicate_qdrant_ids": duplicate_qdrant,
        "checksum_mismatch_ids": checksum_mismatches,
    }