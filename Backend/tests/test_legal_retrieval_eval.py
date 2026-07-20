from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.domain.legal_retrieval import RetrievalProfile
from app.services.legal_retrieval_eval import (
    RetrievalGoldCase,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    run_retrieval_ablation,
)


class FakeRetrievalService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def retrieve(self, query: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"query": query, **kwargs})
        profile = kwargs["profile"]
        if profile == RetrievalProfile.LEXICAL:
            predicted = ["law::D1", "law::DX"]
            warnings = ["lexical_baseline"]
        elif profile == RetrievalProfile.VECTOR:
            predicted = ["law::DX", "law::D2"]
            warnings = []
        else:
            predicted = ["law::D1", "law::D2"]
            warnings = []
        items = [
            SimpleNamespace(provision=SimpleNamespace(lineage_id=lineage_id))
            for lineage_id in predicted
        ]
        return SimpleNamespace(items=items, warnings=warnings)


def test_metric_functions_use_binary_relevance_and_requested_k() -> None:
    expected = ["law::D1", "law::D2"]

    assert recall_at_k(["law::D1", "law::DX"], expected, 2) == 0.5
    assert reciprocal_rank(["law::DX", "law::D2"], expected) == 0.5
    assert ndcg_at_k(["law::D1", "law::D2"], expected, 2) == pytest.approx(1.0)
    assert ndcg_at_k(["law::DX", "law::D2"], expected, 2) < 0.5


@pytest.mark.anyio
async def test_ablation_runs_profiles_and_reports_real_per_case_metrics() -> None:
    service = FakeRetrievalService()
    cases = [
        RetrievalGoldCase(
            case_id="threshold-before-change",
            query="Ngưỡng áp dụng là bao nhiêu?",
            as_of=date(2026, 6, 30),
            expected_lineage_ids=["law::D1", "law::D2", "law::D1"],
        )
    ]

    report = await run_retrieval_ablation(
        service,
        cases,
        profiles=[
            RetrievalProfile.LEXICAL,
            RetrievalProfile.VECTOR,
            RetrievalProfile.HYBRID,
        ],
        k=2,
    )

    assert report.mutated is False
    assert report.canonical_source == "neo4j_temporal"
    assert report.total_cases == 1
    assert [metric.profile for metric in report.profiles] == [
        RetrievalProfile.LEXICAL,
        RetrievalProfile.VECTOR,
        RetrievalProfile.HYBRID,
    ]
    assert report.profiles[0].recall_at_k == 0.5
    assert report.profiles[0].case_metrics[0].warnings == ["lexical_baseline"]
    assert report.profiles[1].mrr == 0.5
    assert report.profiles[2].recall_at_k == 1.0
    assert all(call["limit"] == 2 for call in service.calls)
    assert all(call["as_of"] == date(2026, 6, 30) for call in service.calls)


@pytest.mark.anyio
async def test_ablation_counts_source_errors_as_zero_instead_of_hiding_them() -> None:
    class BrokenService:
        async def retrieve(self, *_: object, **__: object) -> SimpleNamespace:
            raise RuntimeError("source down")

    report = await run_retrieval_ablation(
        BrokenService(),
        [
            RetrievalGoldCase(
                case_id="broken-source",
                query="Quy định nào áp dụng?",
                as_of=date(2026, 7, 1),
                expected_lineage_ids=["law::D1"],
            )
        ],
        profiles=[RetrievalProfile.VECTOR],
        k=5,
    )

    metric = report.profiles[0]
    assert metric.errors == 1
    assert metric.completed == 0
    assert metric.recall_at_k == 0.0
    assert metric.case_metrics[0].status == "error"
    assert metric.case_metrics[0].error == "RuntimeError: source down"
