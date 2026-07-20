from __future__ import annotations

from typing import Any

from app.exceptions import TemporalLawUnavailableError


_PROVISION_RETURN = """
p.provision_id AS provision_id,
p.lineage_id AS lineage_id,
p.parent_lineage_id AS parent_lineage_id,
p.level AS level,
p.version_no AS version_no,
p.source_vb_id AS source_vb_id,
p.logical_vb_id AS logical_vb_id,
coalesce(p.noi_dung, p.tieu_de, '') AS text,
p.effective_from AS effective_from,
p.effective_to AS effective_to,
p.text_checksum AS text_checksum,
p.source_checksum AS source_checksum,
coalesce(p.visibility, 'public') AS visibility,
p.recorded_at AS recorded_at,
coalesce(p.review_status, 'approved') AS review_status
"""

_EFFECTIVE_QUERY = f"""
/* temporal_v2_find_effective */
MATCH (p:LegalProvision)
WHERE p.effective_from IS NOT NULL
  AND date(p.effective_from) <= date($as_of)
  AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
  AND ($logical_vb_id IS NULL OR p.logical_vb_id = $logical_vb_id)
  AND (size($lineage_ids) = 0 OR p.lineage_id IN $lineage_ids)
  AND (
    NOT $public_only
    OR (
      coalesce(p.visibility, 'public') = 'public'
      AND coalesce(p.review_status, 'approved') = 'approved'
    )
  )
RETURN {_PROVISION_RETURN}
ORDER BY p.logical_vb_id, p.lineage_id, p.effective_from, p.version_no
"""

_IDENTIFIER_QUERY = f"""
/* temporal_v2_find_identifier */
MATCH (p:LegalProvision)
WHERE (p.provision_id = $identifier OR p.lineage_id = $identifier)
  AND (
    $as_of IS NULL
    OR (
      p.effective_from IS NOT NULL
      AND date(p.effective_from) <= date($as_of)
      AND (p.effective_to IS NULL OR date($as_of) < date(p.effective_to))
    )
  )
  AND (
    NOT $public_only
    OR (
      coalesce(p.visibility, 'public') = 'public'
      AND coalesce(p.review_status, 'approved') = 'approved'
    )
  )
RETURN {_PROVISION_RETURN}
ORDER BY p.effective_from, p.version_no
"""

_EXACT_IDS_QUERY = f"""
/* temporal_v2_find_exact_ids */
MATCH (p:LegalProvision)
WHERE p.provision_id IN $provision_ids
  AND (
    NOT $public_only
    OR (
      coalesce(p.visibility, 'public') = 'public'
      AND coalesce(p.review_status, 'approved') = 'approved'
    )
  )
RETURN {_PROVISION_RETURN}
ORDER BY p.provision_id
"""

_TIMELINE_QUERY = f"""
/* temporal_v2_timeline */
MATCH (anchor:LegalProvision)
WHERE anchor.provision_id = $identifier OR anchor.lineage_id = $identifier
WITH DISTINCT anchor.lineage_id AS lineage_id
MATCH (p:LegalProvision {{lineage_id: lineage_id}})
WHERE (
  NOT $public_only
  OR (
    coalesce(p.visibility, 'public') = 'public'
    AND coalesce(p.review_status, 'approved') = 'approved'
  )
)
OPTIONAL MATCH (p)-[:SUPERSEDED_BY]->(next:LegalProvision)
RETURN {_PROVISION_RETURN},
       collect(DISTINCT CASE
         WHEN next IS NULL THEN null
         WHEN NOT $public_only THEN next.provision_id
         WHEN coalesce(next.visibility, 'public') = 'public'
          AND coalesce(next.review_status, 'approved') = 'approved'
         THEN next.provision_id
         ELSE null
       END) AS superseded_by_ids
ORDER BY p.effective_from, p.version_no
"""


class Neo4jTemporalRepository:
    """Read-only repository for immutable LegalProvision versions."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

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

    async def _read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if not (self.driver and hasattr(self.driver, "session")):
            raise TemporalLawUnavailableError("Temporal legal graph is not available")
        try:
            async with self.driver.session() as session:
                execute_read = getattr(session, "execute_read", None)
                if callable(execute_read):
                    return await execute_read(self._collect, query, params)
                return await self._collect(session, query, params)
        except TemporalLawUnavailableError:
            raise
        except Exception as exc:
            raise TemporalLawUnavailableError("Temporal legal graph read failed") from exc

    async def find_effective(
        self,
        *,
        as_of: str,
        logical_vb_id: str | None = None,
        lineage_ids: list[str] | None = None,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        return await self._read(
            _EFFECTIVE_QUERY,
            as_of=as_of,
            logical_vb_id=logical_vb_id,
            lineage_ids=list(lineage_ids or []),
            public_only=public_only,
        )

    async def find_by_identifier(
        self,
        identifier: str,
        *,
        as_of: str | None = None,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        return await self._read(
            _IDENTIFIER_QUERY,
            identifier=identifier,
            as_of=as_of,
            public_only=public_only,
        )

    async def find_by_provision_ids(
        self,
        provision_ids: list[str],
        *,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        if not provision_ids:
            return []
        return await self._read(
            _EXACT_IDS_QUERY,
            provision_ids=list(dict.fromkeys(provision_ids)),
            public_only=public_only,
        )

    async def timeline(
        self,
        identifier: str,
        *,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        return await self._read(
            _TIMELINE_QUERY,
            identifier=identifier,
            public_only=public_only,
        )
