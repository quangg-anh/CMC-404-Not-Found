from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.config import BE2Config, get_config
from app.domain.legal_provision import (
    ProvisionLevel,
    ProvisionReviewStatus,
    build_provision_version,
    parse_lineage_id,
)
from app.exceptions import TemporalDataIntegrityError, TemporalLawNotFoundError, ValidationError
from app.main import app
from app.services.temporal_law_service import TemporalLawService
from tests.fixtures.temporal_legal import LOGICAL_VB_ID, V2_DATE, V3_DATE, temporal_legal_fixture


def _row(item: Any, *, superseded_by_ids: list[str] | None = None) -> dict[str, Any]:
    data = item.model_dump(mode="json")
    data["superseded_by_ids"] = list(superseded_by_ids or [])
    return data


class FixtureTemporalRepository:
    def __init__(self, items: list[Any] | None = None, *, edge_map: dict[str, list[str]] | None = None) -> None:
        self.items = list(items or temporal_legal_fixture())
        self.edge_map = edge_map or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def _visible(item: Any, public_only: bool) -> bool:
        return not public_only or (
            item.visibility == "public" and str(item.review_status) == "approved"
        )

    async def find_effective(
        self,
        *,
        as_of: str,
        logical_vb_id: str | None = None,
        lineage_ids: list[str] | None = None,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        self.calls.append(("find_effective", locals().copy()))
        when = date.fromisoformat(as_of)
        lineage_set = set(lineage_ids or [])
        return [
            _row(item)
            for item in self.items
            if item.is_effective_on(when)
            and (logical_vb_id is None or item.logical_vb_id == logical_vb_id)
            and (not lineage_set or item.lineage_id in lineage_set)
            and self._visible(item, public_only)
        ]

    async def find_by_identifier(
        self,
        identifier: str,
        *,
        as_of: str | None = None,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        self.calls.append(("find_by_identifier", locals().copy()))
        when = date.fromisoformat(as_of) if as_of else None
        return [
            _row(item)
            for item in self.items
            if identifier in {item.provision_id, item.lineage_id}
            and (when is None or item.is_effective_on(when))
            and self._visible(item, public_only)
        ]

    async def find_by_provision_ids(
        self,
        provision_ids: list[str],
        *,
        public_only: bool = False,
    ) -> list[dict[str, Any]]:
        self.calls.append(("find_by_provision_ids", locals().copy()))
        ids = set(provision_ids)
        return [
            _row(item)
            for item in self.items
            if item.provision_id in ids and self._visible(item, public_only)
        ]

    async def timeline(self, identifier: str, *, public_only: bool = False) -> list[dict[str, Any]]:
        self.calls.append(("timeline", locals().copy()))
        anchors = [item for item in self.items if identifier in {item.provision_id, item.lineage_id}]
        if not anchors:
            return []
        lineage_id = anchors[0].lineage_id
        return [
            _row(item, superseded_by_ids=self.edge_map.get(item.provision_id, []))
            for item in self.items
            if item.lineage_id == lineage_id and self._visible(item, public_only)
        ]


def _point_a_versions() -> list[Any]:
    return sorted(
        [item for item in temporal_legal_fixture() if item.point == "a"],
        key=lambda item: item.version_no,
    )


def _texts(snapshot: dict[str, Any]) -> list[str]:
    return [str(item["text"]) for item in snapshot["items"]]

def test_parse_lineage_preserves_document_numbers_with_slashes() -> None:
    coordinates = parse_lineage_id("01/2026/ND-CP::D5.K2.Pa")

    assert coordinates.logical_vb_id == "01/2026/ND-CP"
    assert (coordinates.article, coordinates.clause, coordinates.point) == ("5", "2", "a")



@pytest.mark.anyio
async def test_law_as_of_switches_at_cutover_and_keeps_partial_amendment() -> None:
    service = TemporalLawService(FixtureTemporalRepository())

    before = await service.law_as_of(date(2026, 6, 30), logical_vb_id=LOGICAL_VB_ID)
    cutover = await service.law_as_of(V2_DATE, logical_vb_id=LOGICAL_VB_ID)

    assert any("200" in text for text in _texts(before))
    assert any("500" in text for text in _texts(cutover))
    assert any(item["point"] == "b" for item in before["items"])
    assert any(item["point"] == "b" for item in cutover["items"])
    assert any(item["level"] == "khoan" and item["clause"] == "3" for item in cutover["items"])
    assert any(item["level"] == "dieu" and item["article"] == "6" for item in cutover["items"])
    assert all(not (item["article"] == "5" and item["level"] != "diem" and item["clause"] == "2") for item in cutover["items"])


@pytest.mark.anyio
async def test_law_as_of_excludes_future_and_repealed_provisions() -> None:
    service = TemporalLawService(FixtureTemporalRepository())

    cutover = await service.law_as_of(V2_DATE, logical_vb_id=LOGICAL_VB_ID)
    future = await service.law_as_of(V3_DATE, logical_vb_id=LOGICAL_VB_ID)

    assert all(item["article"] not in {"7", "8"} for item in cutover["items"])
    assert any(item["article"] == "7" for item in future["items"])
    assert all(item["article"] != "8" for item in future["items"])


@pytest.mark.anyio
async def test_law_as_of_requires_a_bounded_document_or_lineage_scope() -> None:
    service = TemporalLawService(FixtureTemporalRepository())

    with pytest.raises(ValidationError, match="logical_vb_id or lineage_ids"):
        await service.law_as_of(V2_DATE)


@pytest.mark.anyio
async def test_overlap_is_fail_closed() -> None:
    items = temporal_legal_fixture()
    overlap = build_provision_version(
        logical_vb_id=LOGICAL_VB_ID,
        source_vb_id="FIXTURE-LAW-OVERLAP",
        level=ProvisionLevel.DIEM,
        article="5",
        clause="2",
        point="a",
        text="Overlapping version must never be selected.",
        effective_from=date(2026, 8, 1),
        version_no=99,
    )
    service = TemporalLawService(FixtureTemporalRepository([*items, overlap]))

    with pytest.raises(TemporalDataIntegrityError, match="Multiple legal provision versions"):
        await service.law_as_of(date(2026, 9, 1), logical_vb_id=LOGICAL_VB_ID)


@pytest.mark.anyio
async def test_timeline_orders_v1_v2_v3_and_reports_complete_chain() -> None:
    versions = _point_a_versions()
    edges = {
        versions[0].provision_id: [versions[1].provision_id],
        versions[1].provision_id: [versions[2].provision_id],
    }
    service = TemporalLawService(FixtureTemporalRepository(edge_map=edges))

    result = await service.timeline(versions[1].lineage_id, audience="admin")

    assert [item["version_no"] for item in result["items"]] == [1, 2, 3]
    assert result["complete_chain"] is True
    assert all(item["relation_present"] for item in result["transitions"])
    assert all(item["interval_contiguous"] for item in result["transitions"])


@pytest.mark.anyio
async def test_timeline_rejects_non_increasing_version_numbers() -> None:
    versions = _point_a_versions()
    invalid_v2 = versions[1].model_copy(update={"version_no": 1})
    service = TemporalLawService(FixtureTemporalRepository([versions[0], invalid_v2, versions[2]]))

    with pytest.raises(TemporalDataIntegrityError, match="strictly increasing"):
        await service.timeline(versions[0].lineage_id, audience="admin")


@pytest.mark.anyio
async def test_timeline_rejects_supersession_cycle() -> None:
    versions = _point_a_versions()
    edges = {
        versions[0].provision_id: [versions[1].provision_id],
        versions[1].provision_id: [versions[2].provision_id],
        versions[2].provision_id: [versions[0].provision_id],
    }
    service = TemporalLawService(FixtureTemporalRepository(edge_map=edges))

    with pytest.raises(TemporalDataIntegrityError, match="cycle"):
        await service.timeline(versions[0].lineage_id, audience="admin")


@pytest.mark.anyio
async def test_compare_versions_requires_same_lineage_and_chronological_order() -> None:
    versions = _point_a_versions()
    service = TemporalLawService(FixtureTemporalRepository())

    result = await service.compare_versions(versions[0].provision_id, versions[1].provision_id)
    assert result["diff"]["status"] == "modified"
    assert result["diff"]["total_hunks"] > 0

    point_b = next(item for item in temporal_legal_fixture() if item.point == "b")
    with pytest.raises(ValidationError, match="same legal lineage"):
        await service.compare_versions(versions[0].provision_id, point_b.provision_id)


@pytest.mark.anyio
async def test_hydrate_candidates_resolves_stale_physical_id_to_active_version() -> None:
    versions = _point_a_versions()
    service = TemporalLawService(FixtureTemporalRepository())

    hydrated = await service.hydrate_candidates(
        [versions[0].provision_id],
        as_of=V2_DATE,
        audience="citizen",
    )

    assert [item.provision_id for item in hydrated] == [versions[1].provision_id]


@pytest.mark.anyio
async def test_citizen_cannot_resolve_internal_or_unapproved_versions() -> None:
    internal = build_provision_version(
        logical_vb_id="INTERNAL-LAW",
        source_vb_id="INTERNAL-LAW-V1",
        level=ProvisionLevel.DIEU,
        article="1",
        text="Internal legal review draft.",
        effective_from=date(2026, 1, 1),
        visibility="internal",
    )
    unapproved = build_provision_version(
        logical_vb_id="REVIEW-LAW",
        source_vb_id="REVIEW-LAW-V1",
        level=ProvisionLevel.DIEU,
        article="1",
        text="Public provision awaiting legal review.",
        effective_from=date(2026, 1, 1),
        review_status=ProvisionReviewStatus.NEEDS_REVIEW,
    )
    repository = FixtureTemporalRepository([internal, unapproved])
    service = TemporalLawService(repository)

    with pytest.raises(TemporalLawNotFoundError):
        await service.get_provision(internal.provision_id, as_of=V2_DATE, audience="citizen")
    with pytest.raises(TemporalLawNotFoundError):
        await service.get_provision(unapproved.provision_id, as_of=V2_DATE, audience="citizen")
    admin_result = await service.get_provision(internal.provision_id, as_of=V2_DATE, audience="admin")
    assert admin_result["item"]["visibility"] == "internal"
    citizen_calls = [params for method, params in repository.calls if method == "find_by_identifier"]
    assert citizen_calls[0]["public_only"] is True


class StubTemporalService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def law_as_of(self, as_of: date, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("law_as_of", {"as_of": as_of, **kwargs}))
        return {"as_of": as_of.isoformat(), "items": [], "total": 0}

    async def timeline(self, identifier: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("timeline", {"identifier": identifier, **kwargs}))
        return {"identifier": identifier, "items": [], "transitions": [], "total": 0}

    async def compare_versions(self, old_id: str, new_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("compare", {"old_id": old_id, "new_id": new_id, **kwargs}))
        return {"old": {"provision_id": old_id}, "new": {"provision_id": new_id}, "diff": {}}

    async def get_provision(self, identifier: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_provision", {"identifier": identifier, **kwargs}))
        return {"as_of": str(kwargs.get("as_of")), "item": {"provision_id": identifier}}


@pytest.mark.anyio
async def test_temporal_api_is_hidden_while_flags_are_off() -> None:
    stub = StubTemporalService()

    async def service_override() -> StubTemporalService:
        return stub

    app.dependency_overrides[deps.get_temporal_law_service] = service_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/citizen/legal/provisions/FIXTURE-LAW::D5.K2.Pa?as_of=2026-07-01")

    assert response.status_code == 404
    assert stub.calls == []


@pytest.mark.anyio
async def test_enabled_temporal_apis_forward_admin_and_citizen_audience() -> None:
    stub = StubTemporalService()

    async def config_override() -> BE2Config:
        return BE2Config(legal_provision_v2_read=True, temporal_law_v2=True)

    async def service_override() -> StubTemporalService:
        return stub

    app.dependency_overrides[get_config] = config_override
    app.dependency_overrides[deps.get_temporal_law_service] = service_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-admin-phap-che"}
        as_of = await client.get(
            "/admin/legal/documents/FIXTURE-LAW/as-of?date=2026-07-01",
            headers=headers,
        )
        timeline = await client.get(
            "/admin/legal/provisions/FIXTURE-LAW::D5.K2.Pa/timeline",
            headers=headers,
        )
        compare = await client.get(
            "/admin/legal/provisions/compare",
            params={"old_id": "old/id", "new_id": "new/id"},
            headers=headers,
        )
        citizen = await client.get(
            "/citizen/legal/provisions/FIXTURE-LAW::D5.K2.Pa?as_of=2026-07-01"
        )
        citizen_timeline = await client.get(
            "/citizen/legal/provisions/FIXTURE-LAW::D5.K2.Pa/timeline"
        )
        citizen_compare = await client.get(
            "/citizen/legal/provisions/compare",
            params={"old_id": "old/id", "new_id": "new/id"},
        )

    assert [
        as_of.status_code,
        timeline.status_code,
        compare.status_code,
        citizen.status_code,
        citizen_timeline.status_code,
        citizen_compare.status_code,
    ] == [200, 200, 200, 200, 200, 200]
    assert ("law_as_of", {"as_of": V2_DATE, "logical_vb_id": LOGICAL_VB_ID, "audience": "admin"}) in stub.calls
    assert any(method == "timeline" and params["audience"] == "admin" for method, params in stub.calls)
    assert any(method == "compare" and params["old_id"] == "old/id" for method, params in stub.calls)
    assert any(method == "get_provision" and params["audience"] == "citizen" for method, params in stub.calls)
    assert any(method == "timeline" and params["audience"] == "citizen" for method, params in stub.calls)
    assert any(
        method == "compare"
        and params["old_id"] == "old/id"
        and params["audience"] == "citizen"
        for method, params in stub.calls
    )


@pytest.mark.anyio
async def test_hydrate_exact_versions_does_not_redirect_stale_id() -> None:
    versions = _point_a_versions()
    service = TemporalLawService(FixtureTemporalRepository())

    stale = await service.hydrate_exact_versions(
        [versions[0].provision_id],
        as_of=V2_DATE,
        audience="citizen",
    )
    current = await service.hydrate_exact_versions(
        [versions[1].provision_id],
        as_of=V2_DATE,
        audience="citizen",
    )

    assert stale == []
    assert [item.provision_id for item in current] == [versions[1].provision_id]