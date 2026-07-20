from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.domain.citation_contract import QAAnswerStatus
from app.services.canonical_citation_validator import CanonicalCitationValidator
from tests.fixtures.temporal_legal import V2_DATE, temporal_legal_fixture


def _point_a_versions() -> list[Any]:
    return sorted(
        [item for item in temporal_legal_fixture() if item.point == "a"],
        key=lambda item: item.version_no,
    )


class FakeTemporalService:
    def __init__(self, items: list[Any] | None = None) -> None:
        self.items = list(items or temporal_legal_fixture())
        self.calls: list[dict[str, Any]] = []

    async def hydrate_exact_versions(
        self,
        candidate_ids: list[str],
        *,
        as_of: date,
        audience: str,
    ) -> list[Any]:
        self.calls.append(
            {
                "candidate_ids": candidate_ids,
                "as_of": as_of,
                "audience": audience,
            }
        )
        ids = set(candidate_ids)
        return [
            item
            for item in self.items
            if item.provision_id in ids
            and item.is_effective_on(as_of)
            and (
                audience != "citizen"
                or (
                    item.visibility == "public"
                    and str(item.review_status) == "approved"
                )
            )
        ]


class FakeNLI:
    def __init__(self, *, supported: bool = True) -> None:
        self.supported = supported
        self.calls: list[tuple[str, str]] = []

    async def nli_pair(self, *, premise: str, hypothesis: str) -> dict[str, Any]:
        self.calls.append((premise, hypothesis))
        if self.supported:
            return {
                "label": "khop",
                "score": 0.96,
                "model": "fixture-nli",
                "needs_review": False,
            }
        return {
            "label": "khong_ro",
            "score": 0.4,
            "model": "fixture-nli",
            "needs_review": True,
        }


def _draft(node_id: str, *, quote: str = "Ngưỡng áp dụng là 500 triệu đồng.") -> dict[str, Any]:
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
                "quote": quote,
                "supports_claim_ids": ["claim_1"],
            }
        ],
    }


@pytest.mark.anyio
async def test_validator_builds_all_canonical_metadata_from_exact_neo4j_node() -> None:
    current = _point_a_versions()[1]
    temporal = FakeTemporalService()
    nli = FakeNLI()
    validator = CanonicalCitationValidator(
        temporal,
        nli,
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        _draft(current.provision_id),
        as_of=V2_DATE,
        audience="citizen",
        allowed_node_ids={current.provision_id},
    )

    assert outcome.issues == []
    assert outcome.contract.status == QAAnswerStatus.ANSWERED
    citation = outcome.contract.citations[0]
    assert citation.node_id == current.provision_id
    assert citation.lineage_id == current.lineage_id
    assert citation.document_number == current.source_vb_id
    assert citation.text_checksum == current.text_checksum
    assert citation.source_checksum == current.source_checksum
    assert citation.validation_source == "neo4j"
    assert citation.entailment_score == 0.96
    assert temporal.calls[0]["audience"] == "citizen"
    assert nli.calls == [(current.text, outcome.contract.claims[0].text)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("node_id", "as_of"),
    [
        ("fabricated-node", V2_DATE),
        (_point_a_versions()[0].provision_id, V2_DATE),
    ],
)
async def test_fabricated_or_off_date_physical_node_is_refused(
    node_id: str,
    as_of: date,
) -> None:
    validator = CanonicalCitationValidator(
        FakeTemporalService(),
        FakeNLI(),
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        _draft(node_id),
        as_of=as_of,
        audience="citizen",
    )

    assert outcome.contract.status == QAAnswerStatus.REFUSED
    assert outcome.contract.reason_code == "citation_node_invalid_for_as_of"
    assert outcome.contract.answer is None
    assert outcome.contract.citations == []


@pytest.mark.anyio
async def test_node_outside_retrieval_candidates_is_refused_before_hydration() -> None:
    current = _point_a_versions()[1]
    temporal = FakeTemporalService()
    validator = CanonicalCitationValidator(
        temporal,
        FakeNLI(),
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        _draft(current.provision_id),
        as_of=V2_DATE,
        audience="citizen",
        allowed_node_ids={"another-node"},
    )

    assert outcome.contract.reason_code == "citation_node_not_retrieved"
    assert temporal.calls == []


@pytest.mark.anyio
async def test_wrong_quote_is_refused() -> None:
    current = _point_a_versions()[1]
    validator = CanonicalCitationValidator(
        FakeTemporalService(),
        FakeNLI(),
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        _draft(current.provision_id, quote="Đoạn bịa đặt không có trong văn bản."),
        as_of=V2_DATE,
        audience="citizen",
    )

    assert outcome.contract.reason_code == "citation_quote_mismatch"


@pytest.mark.anyio
async def test_unsupported_claim_is_refused_even_when_quote_is_exact() -> None:
    current = _point_a_versions()[1]
    validator = CanonicalCitationValidator(
        FakeTemporalService(),
        FakeNLI(supported=False),
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        _draft(current.provision_id),
        as_of=V2_DATE,
        audience="citizen",
    )

    assert outcome.contract.reason_code == "claim_not_supported"


@pytest.mark.anyio
async def test_unmapped_material_answer_statement_is_refused() -> None:
    current = _point_a_versions()[1]
    draft = _draft(current.provision_id)
    draft["answer"] += "\nMức phạt là 100 triệu đồng."
    validator = CanonicalCitationValidator(
        FakeTemporalService(),
        FakeNLI(),
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        draft,
        as_of=V2_DATE,
        audience="citizen",
    )

    assert outcome.contract.reason_code == "unmapped_material_claim"


@pytest.mark.anyio
async def test_canonical_checksum_mismatch_is_refused() -> None:
    current = _point_a_versions()[1]
    tampered = current.model_copy(update={"text_checksum": "0" * 64})
    validator = CanonicalCitationValidator(
        FakeTemporalService([tampered]),
        FakeNLI(),
        entailment_threshold=0.7,
    )

    outcome = await validator.validate_answer_draft(
        _draft(current.provision_id),
        as_of=V2_DATE,
        audience="citizen",
    )

    assert outcome.contract.reason_code == "citation_checksum_mismatch"