from __future__ import annotations

from typing import Any

from app.exceptions import LegalRetrievalUnavailableError


_ID_RETURN = """
p.provision_id AS provision_id,
p.lineage_id AS lineage_id,
p.level AS level,
p.logical_vb_id AS logical_vb_id,
p.source_vb_id AS source_vb_id
"""

_EXACT_QUERY = f"""
/* legal_retrieval_v2_exact */
MATCH (p:LegalProvision)
WHERE (
    p.provision_id IN $identifiers
    OR p.lineage_id IN $identifiers
    OR any(document IN $document_numbers WHERE
        toUpper(coalesce(p.logical_vb_id, '')) = toUpper(document)
        OR toUpper(coalesce(p.source_vb_id, '')) = toUpper(document)
    )
)
  AND (
    NOT $public_only
    OR (
      coalesce(p.visibility, 'public') = 'public'
      AND coalesce(p.review_status, 'approved') = 'approved'
    )
  )
WITH p, CASE
    WHEN p.provision_id IN $identifiers THEN 1.0
    WHEN p.lineage_id IN $identifiers THEN 0.99
    ELSE 0.95
END AS raw_score
RETURN {_ID_RETURN}, raw_score
ORDER BY raw_score DESC, p.lineage_id, p.provision_id
LIMIT $limit
"""

_LEXICAL_QUERY = f"""
/* legal_retrieval_v2_lexical */
CALL db.index.fulltext.queryNodes($index_name, $search_query) YIELD node, score
WITH node AS p, score
WHERE p:LegalProvision
  AND (
    NOT $public_only
    OR (
      coalesce(p.visibility, 'public') = 'public'
      AND coalesce(p.review_status, 'approved') = 'approved'
    )
  )
RETURN {_ID_RETURN}, score AS raw_score
ORDER BY raw_score DESC, p.lineage_id, p.provision_id
LIMIT $limit
"""

_GRAPH_QUERY = f"""
/* legal_retrieval_v2_graph_expand */
MATCH (seed:LegalProvision)
WHERE seed.provision_id IN $seed_ids
MATCH path=(seed)-[:SUPERSEDED_BY|CO_KHOAN|CO_DIEM*1..2]-(p:LegalProvision)
WHERE p.provision_id <> seed.provision_id
  AND (
    NOT $public_only
    OR (
      coalesce(p.visibility, 'public') = 'public'
      AND coalesce(p.review_status, 'approved') = 'approved'
    )
  )
WITH p, min(length(path)) AS distance
RETURN {_ID_RETURN},
       1.0 / (toFloat(distance) + 1.0) AS raw_score,
       distance AS graph_distance
ORDER BY graph_distance ASC, p.lineage_id, p.provision_id
LIMIT $limit
"""


class Neo4jLegalRetrievalRepository:
    """ID-only discovery adapter; canonical text is hydrated by TemporalLawService."""

    def __init__(self, driver: Any, *, fulltext_index: str = "legal_provision_text_ft") -> None:
        self.driver = driver
        self.fulltext_index = fulltext_index

    @staticmethod
    def _record_data(record: Any) -> dict[str, Any]:
        data = getattr(record, "data", None)
        return data() if callable(data) else dict(record)

    @classmethod
    async def _collect(cls, runner: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await runner.run(query, **params)
        rows: list[dict[str, Any]] = []
        async for record in result:
            rows.append(cls._record_data(record))
        return rows

    async def _read(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        if not (self.driver and hasattr(self.driver, "session")):
            raise LegalRetrievalUnavailableError("Neo4j legal retrieval is not available")
        try:
            async with self.driver.session() as session:
                execute_read = getattr(session, "execute_read", None)
                if callable(execute_read):
                    return await execute_read(self._collect, cypher, params)
                return await self._collect(session, cypher, params)
        except LegalRetrievalUnavailableError:
            raise
        except Exception as exc:
            raise LegalRetrievalUnavailableError("Neo4j legal retrieval query failed") from exc

    async def exact_search(
        self,
        *,
        identifiers: list[str],
        document_numbers: list[str],
        public_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not identifiers and not document_numbers:
            return []
        return await self._read(
            _EXACT_QUERY,
            identifiers=list(dict.fromkeys(identifiers)),
            document_numbers=list(dict.fromkeys(document_numbers)),
            public_only=public_only,
            limit=limit,
        )

    async def lexical_search(
        self,
        query: str,
        *,
        public_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not str(query or "").strip():
            return []
        return await self._read(
            _LEXICAL_QUERY,
            index_name=self.fulltext_index,
            search_query=query,
            public_only=public_only,
            limit=limit,
        )

    async def expand_graph(
        self,
        seed_ids: list[str],
        *,
        public_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not seed_ids:
            return []
        return await self._read(
            _GRAPH_QUERY,
            seed_ids=list(dict.fromkeys(seed_ids)),
            public_only=public_only,
            limit=limit,
        )
