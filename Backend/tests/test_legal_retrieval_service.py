from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from app.domain.legal_provision import ProvisionLevel, build_provision_version
from app.domain.legal_retrieval import RetrievalProfile, RetrievalSource
from app.services.legal_retrieval_service import (
    LegalRetrievalService,
    RankedHit,
    build_fulltext_query,
    extract_document_numbers,
    extract_legal_identifiers,
    reciprocal_rank_fusion,
)
from tests.fixtures.temporal_legal import LOGICAL_VB_ID, V2_DATE, temporal_legal_fixture


def _point_versions(point: str) -> list[Any]:
    return sorted(
        [item for item in temporal_legal_fixture() if item.point == point],
        key=lambda item: item.version_no,
    )


def _row(item: Any, raw_score: float = 1.0, **extra: Any) -> dict[str, Any]:
    return {
        "provision_id": item.provision_id,
        "lineage_id": item.lineage_id,
        "level": item.level,
        "logical_vb_id": item.logical_vb_id,
        "source_vb_id": item.source_vb_id,
        "raw_score": raw_score,
        **extra,
    }


class FakeRepository:
    def __init__(
        self,
        *,
        exact: list[dict[str, Any]] | None = None,
        lexical: list[dict[str, Any]] | None = None,
        graph: list[dict[str, Any]] | None = None,
    ) -> None:
        self.exact = list(exact or [])
        self.lexical = list(lexical or [])
        self.graph = list(graph or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def exact_search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("exact", kwargs))
        return self.exact

    async def lexical_search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("lexical", {"query": query, **kwargs}))
        return self.lexical

    async def expand_graph(self, seed_ids: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("graph", {"seed_ids": seed_ids, **kwargs}))
        return self.graph


class FakeTemporalService:
    def __init__(self, items: list[Any] | None = None) -> None:
        self.items = list(items or temporal_legal_fixture())
        self.calls: list[dict[str, Any]] = []

    async def hydrate_candidates(
        self,
        candidate_ids: list[str],
        *,
        as_of: date,
        audience: str,
    ) -> list[Any]:
        self.calls.append({"candidate_ids": candidate_ids, "as_of": as_of, "audience": audience})
        by_id = {item.provision_id: item for item in self.items}
        active_by_lineage = {
            item.lineage_id: item
            for item in self.items
            if item.is_effective_on(as_of)
            and (
                audience != "citizen"
                or (item.visibility == "public" and str(item.review_status) == "approved")
            )
        }
        result: list[Any] = []
        seen: set[str] = set()
        for candidate_id in candidate_ids:
            anchor = by_id.get(candidate_id)
            active = active_by_lineage.get(anchor.lineage_id) if anchor else None
            if active and active.provision_id not in seen:
                result.append(active)
                seen.add(active.provision_id)
        return result


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.1, 0.2] for _ in texts]


class FakeQdrant:
    def __init__(self, hits: list[dict[str, Any]] | None = None) -> None:
        self.hits = list(hits or [])
        self.calls: list[dict[str, Any]] = []

    async def search(self, collection: str, vector: list[float], **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"collection": collection, "vector": vector, **kwargs})
        return self.hits


def _vector_hit(item: Any, score: float, **payload_extra: Any) -> dict[str, Any]:
    return {
        "id": f"point-{item.version_no}-{item.point or item.article}",
        "score": score,
        "payload": {
            "provision_id": item.provision_id,
            "lineage_id": item.lineage_id,
            "text_checksum": item.text_checksum,
            "visibility": item.visibility,
            "review_status": str(item.review_status),
            **payload_extra,
        },
    }


def test_reference_extractors_preserve_slashes_and_version_suffix() -> None:
    point = _point_versions("a")[0]
    query = f"Xem {point.provision_id} và Nghị định 01/2026/ND-CP"

    assert extract_legal_identifiers(query) == [point.provision_id]
    assert "01/2026/ND-CP" in extract_document_numbers(query)
    lexical = build_fulltext_query("Thời hạn hoàn thuế theo quy định là bao nhiêu?")
    assert "hoàn" in lexical and "thuế" in lexical
    assert "quy" not in lexical.split()


def test_rrf_uses_rank_and_deduplicates_historical_versions_by_lineage() -> None:
    versions = _point_versions("a")
    point_b = _point_versions("b")[0]
    rankings = {
        RetrievalSource.LEXICAL: [
            RankedHit(versions[0].provision_id, versions[0].lineage_id, raw_score=0.01),
            RankedHit(versions[1].provision_id, versions[1].lineage_id, raw_score=999.0),
            RankedHit(point_b.provision_id, point_b.lineage_id, raw_score=0.9),
        ],
        RetrievalSource.VECTOR: [
            RankedHit(versions[2].provision_id, versions[2].lineage_id, raw_score=0.1),
        ],
    }

    fused = reciprocal_rank_fusion(rankings)

    assert fused[0].lineage_id == versions[0].lineage_id
    assert len(fused[0].evidence) == 2
    assert {item.source for item in fused[0].evidence} == {
        RetrievalSource.LEXICAL,
        RetrievalSource.VECTOR,
    }
    assert fused[0].fusion_score <= 1


@pytest.mark.anyio
async def test_explicit_identifier_is_strict_and_hydrates_stale_version() -> None:
    versions = _point_versions("a")
    repository = FakeRepository(exact=[_row(versions[0])])
    temporal = FakeTemporalService()
    embedder = FakeEmbedder()
    qdrant = FakeQdrant([_vector_hit(versions[0], 1.0)])
    service = LegalRetrievalService(
        repository,
        temporal,
        qdrant=qdrant,
        embedder=embedder,
    )

    result = await service.retrieve(
        f"Nội dung {versions[0].provision_id} là gì?",
        as_of=V2_DATE,
        audience="citizen",
        profile=RetrievalProfile.HYBRID_GRAPH,
    )

    assert result.total == 1
    assert result.items[0].provision.provision_id == versions[1].provision_id
    assert result.items[0].exact_match is True
    assert embedder.calls == []
    assert qdrant.calls == []
    assert all(method != "lexical" for method, _params in repository.calls)


@pytest.mark.anyio
async def test_missing_explicit_identifier_does_not_fall_through_to_semantic_search() -> None:
    embedder = FakeEmbedder()
    qdrant = FakeQdrant()
    service = LegalRetrievalService(
        FakeRepository(),
        FakeTemporalService(),
        qdrant=qdrant,
        embedder=embedder,
    )

    result = await service.retrieve(
        "UNKNOWN-LAW::D9.K9.Pz có nội dung gì?",
        as_of=V2_DATE,
        profile=RetrievalProfile.HYBRID,
    )

    assert result.items == []
    assert "explicit_identifier_not_found" in result.warnings
    assert embedder.calls == []
    assert qdrant.calls == []


@pytest.mark.anyio
async def test_missing_document_number_does_not_fall_through_to_semantic_search() -> None:
    repository = FakeRepository()
    embedder = FakeEmbedder()
    qdrant = FakeQdrant()
    service = LegalRetrievalService(
        repository,
        FakeTemporalService(),
        qdrant=qdrant,
        embedder=embedder,
    )

    result = await service.retrieve(
        "Nghị định 999/2099/ND-CP quy định gì?",
        as_of=V2_DATE,
        profile=RetrievalProfile.HYBRID,
    )

    assert result.items == []
    assert "explicit_identifier_not_found" in result.warnings
    assert embedder.calls == []
    assert qdrant.calls == []
    assert repository.calls[0][1]["document_numbers"] == ["999/2099/ND-CP"]

@pytest.mark.anyio
async def test_hybrid_result_ignores_qdrant_text_and_uses_temporal_canonical_text() -> None:
    versions = _point_versions("a")
    repository = FakeRepository(lexical=[_row(versions[0], 0.2)])
    qdrant = FakeQdrant(
        [_vector_hit(versions[0], 0.99, text_preview="TAMPERED VECTOR LEGAL TEXT")]
    )
    temporal = FakeTemporalService()
    service = LegalRetrievalService(
        repository,
        temporal,
        qdrant=qdrant,
        embedder=FakeEmbedder(),
    )

    result = await service.retrieve(
        "ngưỡng áp dụng bao nhiêu tiền",
        as_of=V2_DATE,
        profile=RetrievalProfile.HYBRID,
    )

    assert result.items[0].provision.provision_id == versions[1].provision_id
    assert "500" in result.items[0].provision.text
    assert "TAMPERED" not in json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    assert {item.source for item in result.items[0].evidence} == {
        RetrievalSource.LEXICAL,
        RetrievalSource.VECTOR,
    }
    assert temporal.calls[0]["as_of"] == V2_DATE


@pytest.mark.anyio
async def test_graph_expansion_adds_related_canonical_candidate() -> None:
    point_a = _point_versions("a")[1]
    point_b = _point_versions("b")[0]
    repository = FakeRepository(
        lexical=[_row(point_a, 0.8)],
        graph=[_row(point_b, 0.5, graph_distance=2)],
    )
    service = LegalRetrievalService(repository, FakeTemporalService())

    result = await service.retrieve(
        "ngưỡng áp dụng và trường hợp liên quan",
        as_of=V2_DATE,
        profile=RetrievalProfile.HYBRID_GRAPH,
    )

    by_lineage = {item.provision.lineage_id: item for item in result.items}
    assert point_a.lineage_id in by_lineage
    assert point_b.lineage_id in by_lineage
    assert any(
        evidence.source == RetrievalSource.GRAPH
        for evidence in by_lineage[point_b.lineage_id].evidence
    )
    assert any(method == "graph" for method, _params in repository.calls)


@pytest.mark.anyio
async def test_citizen_canonical_hydration_drops_internal_discovery_hit() -> None:
    internal = build_provision_version(
        logical_vb_id="INTERNAL-RETRIEVAL",
        source_vb_id="INTERNAL-RETRIEVAL-V1",
        level=ProvisionLevel.DIEU,
        article="1",
        text="Internal draft only.",
        effective_from=date(2026, 1, 1),
        visibility="internal",
    )
    service = LegalRetrievalService(
        FakeRepository(),
        FakeTemporalService([internal]),
        qdrant=FakeQdrant([_vector_hit(internal, 0.99)]),
        embedder=FakeEmbedder(),
    )

    result = await service.retrieve(
        "internal draft",
        as_of=V2_DATE,
        audience="citizen",
        profile=RetrievalProfile.VECTOR,
    )

    assert result.items == []
    assert "no_canonical_candidates_at_as_of" in result.warnings


@pytest.mark.anyio
async def test_reranker_baseline_reorders_canonical_candidates() -> None:
    first = build_provision_version(
        logical_vb_id="RERANK-LAW",
        source_vb_id="RERANK-LAW-V1",
        level=ProvisionLevel.DIEU,
        article="1",
        text="General filing procedure.",
        effective_from=date(2026, 1, 1),
    )
    second = build_provision_version(
        logical_vb_id="RERANK-LAW",
        source_vb_id="RERANK-LAW-V1",
        level=ProvisionLevel.DIEU,
        article="2",
        text="Special tax refund deadline and application dossier.",
        effective_from=date(2026, 1, 1),
    )
    repository = FakeRepository(
        lexical=[_row(first, 0.9), _row(second, 0.8)],
    )
    service = LegalRetrievalService(repository, FakeTemporalService([first, second]))

    result = await service.retrieve(
        "special tax refund deadline",
        as_of=V2_DATE,
        profile=RetrievalProfile.HYBRID_GRAPH_RERANK,
    )

    assert result.items[0].provision.provision_id == second.provision_id
    assert result.items[0].rerank_score > result.items[1].rerank_score
    assert result.source_counts[RetrievalSource.RERANKER.value] == 2


@pytest.mark.anyio
async def test_vector_profile_does_not_call_lexical_source() -> None:
    point = _point_versions("b")[0]
    repository = FakeRepository(lexical=[_row(point)])
    qdrant = FakeQdrant([_vector_hit(point, 0.7)])
    service = LegalRetrievalService(
        repository,
        FakeTemporalService(),
        qdrant=qdrant,
        embedder=FakeEmbedder(),
    )

    result = await service.retrieve(
        "điểm không sửa đổi",
        as_of=V2_DATE,
        profile=RetrievalProfile.VECTOR,
    )

    assert result.total == 1
    assert all(method != "lexical" for method, _params in repository.calls)
    assert result.source_counts == {"vector": 1}
    assert qdrant.calls[0]["query_filter"] == {
        "must": [
            {"key": "visibility", "match": {"value": "public"}},
            {"key": "review_status", "match": {"value": "approved"}},
        ]
    }
