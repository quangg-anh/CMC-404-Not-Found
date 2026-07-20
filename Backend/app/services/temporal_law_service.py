from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any, Literal

from pydantic import ValidationError as PydanticValidationError

from app.domain.legal_provision import LegalProvisionVersion, parse_lineage_id
from app.exceptions import (
    TemporalDataIntegrityError,
    TemporalLawNotFoundError,
    ValidationError,
)
from app.pipelines.legal.version_diff import VersionDiff

Audience = Literal["admin", "citizen"]


class TemporalLawService:
    """Canonical read service for immutable legal provisions at a point in time."""

    def __init__(self, repository: Any, *, diff_engine: VersionDiff | None = None) -> None:
        self.repository = repository
        self.diff_engine = diff_engine or VersionDiff()

    @staticmethod
    def _public_only(audience: Audience) -> bool:
        if audience not in {"admin", "citizen"}:
            raise ValidationError("audience must be admin or citizen")
        return audience == "citizen"

    @staticmethod
    def _iso_date(value: date) -> str:
        if not isinstance(value, date):
            raise ValidationError("as_of must be a date")
        return value.isoformat()

    @staticmethod
    def _natural_key(value: str) -> tuple[Any, ...]:
        return tuple(
            int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value)
        )

    @classmethod
    def _sort_key(cls, item: LegalProvisionVersion) -> tuple[Any, ...]:
        return (
            cls._natural_key(item.logical_vb_id),
            cls._natural_key(item.article),
            cls._natural_key(item.clause or ""),
            cls._natural_key(item.point or ""),
            item.effective_from,
            item.version_no,
        )

    @staticmethod
    def _serialize(item: LegalProvisionVersion) -> dict[str, Any]:
        return item.model_dump(mode="json")

    @staticmethod
    def _to_model(row: dict[str, Any]) -> LegalProvisionVersion:
        try:
            coordinates = parse_lineage_id(str(row.get("lineage_id") or ""))
            payload = {
                "provision_id": row.get("provision_id"),
                "lineage_id": row.get("lineage_id"),
                "parent_lineage_id": row.get("parent_lineage_id"),
                "level": row.get("level"),
                "version_no": row.get("version_no"),
                "source_vb_id": row.get("source_vb_id"),
                "logical_vb_id": row.get("logical_vb_id"),
                "article": coordinates.article,
                "clause": coordinates.clause,
                "point": coordinates.point,
                "text": row.get("text"),
                "effective_from": row.get("effective_from"),
                "effective_to": row.get("effective_to"),
                "text_checksum": row.get("text_checksum"),
                "source_checksum": row.get("source_checksum"),
                "visibility": row.get("visibility", "public"),
                "review_status": row.get("review_status", "approved"),
            }
            if row.get("recorded_at") is not None:
                payload["recorded_at"] = row["recorded_at"]
            return LegalProvisionVersion.model_validate(payload)
        except (PydanticValidationError, ValueError, TypeError) as exc:
            raise TemporalDataIntegrityError(
                "Temporal legal node violates the immutable provision contract",
                details={
                    "provision_id": row.get("provision_id"),
                    "lineage_id": row.get("lineage_id"),
                    "validation_error": str(exc),
                },
            ) from exc

    @classmethod
    def _models(cls, rows: list[dict[str, Any]]) -> list[LegalProvisionVersion]:
        return [cls._to_model(row) for row in rows]

    @staticmethod
    def _assert_unique_active(items: list[LegalProvisionVersion], as_of: date) -> None:
        grouped: dict[str, list[LegalProvisionVersion]] = defaultdict(list)
        for item in items:
            if not item.is_effective_on(as_of):
                raise TemporalDataIntegrityError(
                    "Repository returned a legal provision outside the requested date",
                    details={"provision_id": item.provision_id, "as_of": as_of.isoformat()},
                )
            grouped[item.lineage_id].append(item)
        overlaps = {
            lineage: [item.provision_id for item in versions]
            for lineage, versions in grouped.items()
            if len(versions) > 1
        }
        if overlaps:
            raise TemporalDataIntegrityError(
                "Multiple legal provision versions are effective for the same lineage",
                details={"as_of": as_of.isoformat(), "overlaps": overlaps},
            )

    @classmethod
    def _deepest_leaves(cls, items: list[LegalProvisionVersion]) -> list[LegalProvisionVersion]:
        active_lineages = {item.lineage_id for item in items}
        parent_lineages = {
            item.parent_lineage_id
            for item in items
            if item.parent_lineage_id in active_lineages
        }
        return sorted(
            [item for item in items if item.lineage_id not in parent_lineages],
            key=cls._sort_key,
        )

    async def law_as_of(
        self,
        as_of: date,
        *,
        logical_vb_id: str | None = None,
        lineage_ids: list[str] | None = None,
        audience: Audience = "citizen",
    ) -> dict[str, Any]:
        document = str(logical_vb_id or "").strip() or None
        lineages = [str(value).strip() for value in (lineage_ids or []) if str(value).strip()]
        if document is None and not lineages:
            raise ValidationError("logical_vb_id or lineage_ids is required")
        rows = await self.repository.find_effective(
            as_of=self._iso_date(as_of),
            logical_vb_id=document,
            lineage_ids=list(dict.fromkeys(lineages)),
            public_only=self._public_only(audience),
        )
        models = self._models(rows)
        self._assert_unique_active(models, as_of)
        leaves = self._deepest_leaves(models)
        return {
            "as_of": as_of.isoformat(),
            "logical_vb_id": document,
            "lineage_ids": lineages,
            "items": [self._serialize(item) for item in leaves],
            "total": len(leaves),
        }

    async def resolve_version(
        self,
        identifier: str,
        as_of: date,
        *,
        audience: Audience = "citizen",
    ) -> LegalProvisionVersion:
        key = str(identifier or "").strip()
        if not key:
            raise ValidationError("identifier is required")
        public_only = self._public_only(audience)
        anchor_rows = await self.repository.find_by_identifier(key, as_of=None, public_only=public_only)
        anchors = self._models(anchor_rows)
        if not anchors:
            raise TemporalLawNotFoundError(
                "Legal provision was not found or is not visible",
                details={"identifier": key},
            )
        lineages = list(dict.fromkeys(item.lineage_id for item in anchors))
        rows = await self.repository.find_effective(
            as_of=self._iso_date(as_of),
            lineage_ids=lineages,
            public_only=public_only,
        )
        models = self._models(rows)
        self._assert_unique_active(models, as_of)
        if len(models) != 1:
            raise TemporalLawNotFoundError(
                "No unique legal provision is effective on the requested date",
                details={"identifier": key, "as_of": as_of.isoformat()},
            )
        return models[0]

    async def get_provision(
        self,
        provision_id: str,
        *,
        as_of: date | None = None,
        audience: Audience = "citizen",
    ) -> dict[str, Any]:
        requested_date = as_of or date.today()
        item = await self.resolve_version(provision_id, requested_date, audience=audience)
        return {"as_of": requested_date.isoformat(), "item": self._serialize(item)}

    @staticmethod
    def _assert_timeline_integrity(
        versions: list[LegalProvisionVersion],
        edge_map: dict[str, set[str]],
    ) -> None:
        if not versions:
            return
        lineages = {item.lineage_id for item in versions}
        levels = {item.level for item in versions}
        ids = [item.provision_id for item in versions]
        if len(lineages) != 1 or len(levels) != 1 or len(ids) != len(set(ids)):
            raise TemporalDataIntegrityError(
                "Timeline contains mixed lineages, levels, or duplicate versions",
                details={"lineages": sorted(lineages), "provision_ids": ids},
            )
        ordered = sorted(versions, key=lambda item: (item.effective_from, item.version_no))
        for previous, current in zip(ordered, ordered[1:]):
            if current.version_no <= previous.version_no:
                raise TemporalDataIntegrityError(
                    "Timeline version numbers are not strictly increasing",
                    details={"old_id": previous.provision_id, "new_id": current.provision_id},
                )
            if previous.effective_to is None or previous.effective_to > current.effective_from:
                raise TemporalDataIntegrityError(
                    "Timeline contains overlapping effective intervals",
                    details={"old_id": previous.provision_id, "new_id": current.provision_id},
                )

        known_ids = set(ids)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise TemporalDataIntegrityError(
                    "SUPERSEDED_BY relationships contain a cycle",
                    details={"provision_id": node_id},
                )
            if node_id in visited:
                return
            visiting.add(node_id)
            for next_id in edge_map.get(node_id, set()):
                if next_id in known_ids:
                    visit(next_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for item_id in ids:
            visit(item_id)

    async def timeline(
        self,
        identifier: str,
        *,
        audience: Audience = "citizen",
    ) -> dict[str, Any]:
        key = str(identifier or "").strip()
        if not key:
            raise ValidationError("identifier is required")
        rows = await self.repository.timeline(key, public_only=self._public_only(audience))
        versions = self._models(rows)
        if not versions:
            raise TemporalLawNotFoundError(
                "Legal provision timeline was not found or is not visible",
                details={"identifier": key},
            )
        edge_map = {
            str(row.get("provision_id")): {
                str(value) for value in (row.get("superseded_by_ids") or []) if value
            }
            for row in rows
        }
        self._assert_timeline_integrity(versions, edge_map)
        ordered = sorted(versions, key=lambda item: (item.effective_from, item.version_no))
        transitions = [
            {
                "old_id": old.provision_id,
                "new_id": new.provision_id,
                "relation_present": new.provision_id in edge_map.get(old.provision_id, set()),
                "interval_contiguous": old.effective_to == new.effective_from,
            }
            for old, new in zip(ordered, ordered[1:])
        ]
        return {
            "identifier": key,
            "lineage_id": ordered[0].lineage_id,
            "items": [self._serialize(item) for item in ordered],
            "transitions": transitions,
            "complete_chain": all(
                item["relation_present"] and item["interval_contiguous"] for item in transitions
            ),
            "total": len(ordered),
        }

    async def compare_versions(
        self,
        old_id: str,
        new_id: str,
        *,
        audience: Audience = "admin",
    ) -> dict[str, Any]:
        rows = await self.repository.find_by_provision_ids(
            [old_id, new_id],
            public_only=self._public_only(audience),
        )
        versions = self._models(rows)
        by_id = {item.provision_id: item for item in versions}
        if old_id not in by_id or new_id not in by_id:
            raise TemporalLawNotFoundError(
                "One or both legal provision versions were not found or are not visible",
                details={"old_id": old_id, "new_id": new_id},
            )
        old = by_id[old_id]
        new = by_id[new_id]
        if old.lineage_id != new.lineage_id:
            raise ValidationError("Only versions from the same legal lineage can be compared")
        if old.effective_from >= new.effective_from:
            raise ValidationError("old_id must precede new_id")
        return {
            "old": self._serialize(old),
            "new": self._serialize(new),
            "diff": self.diff_engine.compare_khoan_texts(old.text, new.text),
        }

    async def load_versions_by_ids(
        self,
        provision_ids: list[str],
        *,
        audience: Audience = "admin",
    ) -> list[LegalProvisionVersion]:
        """Load exact immutable versions without applying an effective-date filter."""
        ordered_ids = list(
            dict.fromkeys(
                str(value).strip()
                for value in provision_ids
                if str(value).strip()
            )
        )
        if not ordered_ids:
            return []
        rows = await self.repository.find_by_provision_ids(
            ordered_ids,
            public_only=self._public_only(audience),
        )
        models = self._models(rows)
        by_id = {item.provision_id: item for item in models}
        missing = [item for item in ordered_ids if item not in by_id]
        if missing:
            raise TemporalLawNotFoundError(
                "One or more immutable legal provision versions were not found",
                details={"missing_provision_ids": missing},
            )
        return [by_id[item] for item in ordered_ids]

    async def hydrate_exact_versions(        self,
        candidate_ids: list[str],
        *,
        as_of: date,
        audience: Audience,
    ) -> list[LegalProvisionVersion]:
        """Hydrate requested physical IDs only when they are effective at ``as_of``.

        Unlike ``hydrate_candidates``, this never follows lineage to another physical
        version. Citation validation uses it to reject stale or off-date node IDs.
        """
        ordered_ids = list(
            dict.fromkeys(
                str(value).strip()
                for value in candidate_ids
                if str(value).strip()
            )
        )
        if not ordered_ids:
            return []
        rows = await self.repository.find_by_provision_ids(
            ordered_ids,
            public_only=self._public_only(audience),
        )
        models = self._models(rows)
        by_id = {item.provision_id: item for item in models}
        exact = [
            by_id[provision_id]
            for provision_id in ordered_ids
            if provision_id in by_id and by_id[provision_id].is_effective_on(as_of)
        ]
        self._assert_unique_active(exact, as_of)
        return exact
    async def hydrate_candidates(
        self,
        candidate_ids: list[str],
        *,
        as_of: date,
        audience: Audience,
    ) -> list[LegalProvisionVersion]:
        ordered_ids = list(dict.fromkeys(str(value).strip() for value in candidate_ids if str(value).strip()))
        if not ordered_ids:
            return []
        public_only = self._public_only(audience)
        anchor_rows = await self.repository.find_by_provision_ids(ordered_ids, public_only=public_only)
        anchors = self._models(anchor_rows)
        anchor_by_id = {item.provision_id: item for item in anchors}
        lineages = list(dict.fromkeys(item.lineage_id for item in anchors))
        rows = await self.repository.find_effective(
            as_of=self._iso_date(as_of),
            lineage_ids=lineages,
            public_only=public_only,
        )
        effective = self._models(rows)
        self._assert_unique_active(effective, as_of)
        by_lineage = {item.lineage_id: item for item in effective}
        hydrated: list[LegalProvisionVersion] = []
        seen: set[str] = set()
        for candidate_id in ordered_ids:
            anchor = anchor_by_id.get(candidate_id)
            active = by_lineage.get(anchor.lineage_id) if anchor else None
            if active and active.provision_id not in seen:
                hydrated.append(active)
                seen.add(active.provision_id)
        return hydrated
