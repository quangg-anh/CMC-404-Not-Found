// LAWGIC core v2 acceptance queries (T01-T15).
// Parameters are supplied by the temporal fixture loader. These queries are read-only.

// T01 — parser/writer preserved every Điểm expected for one Khoản.
MATCH (k:LegalProvision:Khoan {lineage_id: $khoan_lineage})-[:CO_DIEM]->(p:LegalProvision:Diem)
RETURN collect(DISTINCT p.lineage_id) AS diem_lineages, count(DISTINCT p) AS diem_count;

// T02 — deepest leaf: a Khoản with active Điểm must not be returned as a leaf.
MATCH (k:LegalProvision:Khoan {lineage_id: $khoan_lineage})
WHERE date(k.effective_from) <= date($as_of)
  AND (k.effective_to IS NULL OR date($as_of) < date(k.effective_to))
OPTIONAL MATCH (k)-[:CO_DIEM]->(p:LegalProvision:Diem)
WHERE date(p.effective_from) <= date($as_of)
  AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
RETURN k.provision_id AS khoan_id, collect(p.provision_id) AS active_diem_ids;

// T03 — a Khoản without active Điểm is itself a leaf.
MATCH (k:LegalProvision:Khoan {lineage_id: $leaf_khoan_lineage})
WHERE date(k.effective_from) <= date($as_of)
  AND (k.effective_to IS NULL OR date($as_of) < date(k.effective_to))
  AND NOT EXISTS {
    MATCH (k)-[:CO_DIEM]->(p:LegalProvision:Diem)
    WHERE date(p.effective_from) <= date($as_of)
      AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
  }
RETURN k.provision_id AS leaf_id;

// T04 — an Điều without active Khoản is itself a leaf.
MATCH (d:LegalProvision:Dieu {lineage_id: $leaf_dieu_lineage})
WHERE date(d.effective_from) <= date($as_of)
  AND (d.effective_to IS NULL OR date($as_of) < date(d.effective_to))
  AND NOT EXISTS {
    MATCH (d)-[:CO_KHOAN]->(k:LegalProvision:Khoan)
    WHERE date(k.effective_from) <= date($as_of)
      AND (k.effective_to IS NULL OR date($as_of) < date(k.effective_to))
  }
RETURN d.provision_id AS leaf_id;

// T05 — partial amendment changes only Điểm a; Điểm b stays open-ended.
MATCH (a:LegalProvision:Diem {lineage_id: $diem_a_lineage})
MATCH (b:LegalProvision:Diem {lineage_id: $diem_b_lineage})
RETURN collect(a.provision_id) AS diem_a_versions,
       collect(b.provision_id) AS diem_b_versions,
       collect(b.effective_to) AS diem_b_effective_to;

// T06 — V1 → V2 → V3 is ordered and contains no directed cycle.
MATCH path=(first:LegalProvision {lineage_id: $lineage})-[:SUPERSEDED_BY*1..10]->(last:LegalProvision)
RETURN [node IN nodes(path) | node.provision_id] AS version_path,
       length(path) AS hops;

// T07 — future-effective versions are absent before their start date.
MATCH (p:LegalProvision {lineage_id: $future_lineage})
WHERE date(p.effective_from) <= date($as_of)
  AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
RETURN collect(p.provision_id) AS active_ids;

// T08 — repealed provisions are absent at and after exclusive effective_to.
MATCH (p:LegalProvision {lineage_id: $repealed_lineage})
WHERE date(p.effective_from) <= date($as_of)
  AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
RETURN collect(p.provision_id) AS active_ids;

// T09 — provision_id is globally unique after repeated ingest.
MATCH (p:LegalProvision)
WITH p.provision_id AS id, count(*) AS occurrences
WHERE occurrences > 1
RETURN id, occurrences;

// T10 — every v2 provision has canonical text/checksum and an interval start.
MATCH (p:LegalProvision)
WHERE p.noi_dung IS NULL OR p.text_checksum IS NULL OR p.effective_from IS NULL
RETURN p.provision_id AS invalid_id, labels(p) AS labels;

// T11 — canonical citation material is loaded from Neo4j by physical ID, never Qdrant text.
MATCH (p:LegalProvision {provision_id: $citation_node_id})
RETURN p.provision_id AS node_id,
       coalesce(p.noi_dung, p.tieu_de, '') AS canonical_text,
       p.text_checksum AS text_checksum,
       p.source_checksum AS source_checksum;

// T12 — a fabricated physical node resolves to zero canonical rows.
OPTIONAL MATCH (p:LegalProvision {provision_id: $fabricated_node_id})
RETURN count(p) AS canonical_node_count;

// T13 — an exact physical citation node must itself be effective at as_of.
MATCH (p:LegalProvision {provision_id: $citation_node_id})
WHERE date(p.effective_from) <= date($as_of)
  AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
  AND coalesce(p.visibility, 'public') = 'public'
  AND coalesce(p.review_status, 'approved') = 'approved'
RETURN p.provision_id AS active_citation_node_id;

// T14 — the proposed quote must be an exact canonical substring after application normalization.
MATCH (p:LegalProvision {provision_id: $citation_node_id})
WHERE coalesce(p.noi_dung, p.tieu_de, '') CONTAINS $exact_quote
RETURN p.provision_id AS quote_valid_node_id;

// T15 — return canonical premise for claim-level NLI; service must refuse non-entailed edges.
MATCH (p:LegalProvision {provision_id: $citation_node_id})
RETURN p.provision_id AS node_id,
       coalesce(p.noi_dung, p.tieu_de, '') AS nli_premise,
       $claim_text AS nli_hypothesis;