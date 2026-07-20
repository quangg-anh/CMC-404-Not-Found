from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import BE2Config
from app.domain.citation_contract import (
    CitationAnswerDraftV2,
    CitationContractV2,
    QAAnswerStatus,
)
from app.exceptions import ValidationError
from app.services.canonical_citation_validator import CanonicalCitationValidator
from app.services.legal_qa_v2_service import LegalQAV2Service
from app.services.qa_service import QAService
from tests.fixtures.temporal_legal import V2_DATE, temporal_legal_fixture


def _current_point() -> Any:
    return sorted(
        [item for item in temporal_legal_fixture() if item.point == "a"],
        key=lambda item: item.version_no,
    )[1]


class FakeRetrieval:
    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.calls: list[dict[str, Any]] = []

    async def retrieve(self, query: str, **kwargs: Any) -> SimpleNamespace:
        self.calls.append({"query": query, **kwargs})
        return SimpleNamespace(
            items=[
                SimpleNamespace(provision=provision)
                for provision in self.items
            ],
            warnings=[],
        )


class FakeTemporal:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    async def hydrate_exact_versions(
        self,
        candidate_ids: list[str],
        *,
        as_of: date,
        audience: str,
    ) -> list[Any]:
        ids = set(candidate_ids)
        return [
            item
            for item in self.items
            if item.provision_id in ids and item.is_effective_on(as_of)
        ]


class FakeNLI:
    async def nli_pair(self, *, premise: str, hypothesis: str) -> dict[str, Any]:
        return {
            "label": "khop",
            "score": 0.98,
            "model": "fixture",
            "needs_review": False,
        }


class FakeRouter:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.output


def _draft(node_id: str) -> dict[str, Any]:
    answer = "Ngưỡng áp dụng là 500 triệu đồng."
    return {
        "answer": answer,
        "claims": [
            {
                "claim_id": "claim_1",
                "text": answer,
                "citation_ids": ["citation_1"],
            }
        ],
        "citations": [
            {
                "citation_id": "citation_1",
                "node_id": node_id,
                "quote": answer,
                "supports_claim_ids": ["claim_1"],
            }
        ],
    }


@pytest.mark.anyio
async def test_legal_qa_v2_returns_only_canonical_contract() -> None:
    provision = _current_point()
    retrieval = FakeRetrieval([provision])
    router = FakeRouter(_draft(provision.provision_id))
    validator = CanonicalCitationValidator(
        FakeTemporal([provision]),
        FakeNLI(),
        entailment_threshold=0.7,
    )
    service = LegalQAV2Service(retrieval, validator, router)

    contract = await service.answer(
        "Ngưỡng áp dụng là bao nhiêu?",
        audience="citizen",
        as_of=V2_DATE,
    )

    assert contract.status == QAAnswerStatus.ANSWERED
    assert contract.citations[0].node_id == provision.provision_id
    assert contract.citations[0].validation_source == "neo4j"
    assert retrieval.calls[0]["profile"] == "hybrid_graph_rerank"
    assert router.calls[0]["schema"] is CitationAnswerDraftV2
    assert provision.provision_id in router.calls[0]["prompt"]


@pytest.mark.anyio
async def test_legal_qa_v2_refuses_without_retrieval_basis() -> None:
    retrieval = FakeRetrieval([])
    router = FakeRouter({})
    service = LegalQAV2Service(retrieval, object(), router)

    contract = await service.answer(
        "Ngưỡng áp dụng là bao nhiêu?",
        audience="citizen",
        as_of=V2_DATE,
    )

    assert contract.status == QAAnswerStatus.REFUSED
    assert contract.reason_code == "insufficient_legal_basis"
    assert router.calls == []


@pytest.mark.anyio
async def test_legal_qa_v2_refuses_invalid_model_output() -> None:
    provision = _current_point()
    service = LegalQAV2Service(
        FakeRetrieval([provision]),
        object(),
        FakeRouter({"status": "needs_review", "needs_review": True}),
    )

    contract = await service.answer(
        "Ngưỡng áp dụng là bao nhiêu?",
        audience="citizen",
        as_of=V2_DATE,
    )

    assert contract.reason_code == "invalid_model_output"


@pytest.mark.anyio
async def test_legal_qa_v2_refuses_non_legal_meta_without_retrieval() -> None:
    retrieval = FakeRetrieval([_current_point()])
    service = LegalQAV2Service(retrieval, object(), FakeRouter({}))

    contract = await service.answer(
        "Bạn là model gì?",
        audience="citizen",
        as_of=V2_DATE,
    )

    assert contract.reason_code == "non_legal_meta_question"
    assert retrieval.calls == []


@pytest.mark.anyio
async def test_qa_service_dispatches_to_v2_only_when_flag_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class Delegate:
        async def answer(self, question: str, **kwargs: Any) -> CitationContractV2:
            calls.append({"question": question, **kwargs})
            return CitationContractV2(
                status=QAAnswerStatus.REFUSED,
                as_of=kwargs["as_of"],
                reason_code="fixture_refusal",
            )

    monkeypatch.setattr(
        "app.services.qa_service.get_config",
        lambda: BE2Config(
            qa_citation_v2=True,
            legal_provision_v2_read=True,
            temporal_law_v2=True,
        ),
    )
    service = QAService(
        nli=FakeNLI(),
        legal_qa_v2_service=Delegate(),
    )

    output = await service.answer(
        "Câu hỏi pháp lý",
        audience="citizen",
        as_of=V2_DATE.isoformat(),
    )

    assert output == {
        "status": "refused",
        "as_of": V2_DATE.isoformat(),
        "answer": None,
        "claims": [],
        "citations": [],
        "reason_code": "fixture_refusal",
    }
    assert calls[0]["as_of"] == V2_DATE


@pytest.mark.anyio
async def test_qa_v2_dispatch_rejects_invalid_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.qa_service.get_config",
        lambda: BE2Config(
            qa_citation_v2=True,
            legal_provision_v2_read=True,
            temporal_law_v2=True,
        ),
    )
    service = QAService(nli=FakeNLI())

    with pytest.raises(ValidationError, match="as_of must be an ISO date"):
        await service.answer(
            "Câu hỏi pháp lý",
            audience="citizen",
            as_of="20-07-2026",
        )


@pytest.mark.anyio
async def test_qa_v2_dispatch_requires_temporal_read_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Delegate:
        async def answer(self, *_: Any, **__: Any) -> CitationContractV2:
            calls.append("called")
            raise AssertionError("delegate must not run")

    monkeypatch.setattr(
        "app.services.qa_service.get_config",
        lambda: BE2Config(qa_citation_v2=True),
    )
    service = QAService(
        nli=FakeNLI(),
        legal_qa_v2_service=Delegate(),
    )

    output = await service.answer(
        "Câu hỏi pháp lý",
        audience="citizen",
        as_of=V2_DATE.isoformat(),
    )

    assert output["status"] == "refused"
    assert output["reason_code"] == "citation_v2_dependencies_disabled"
    assert calls == []