from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import BE2Config
from app.domain.citation_contract import (
    AnswerClaimV2,
    CitationContractV2,
    CitationV2,
    ClaimSupportStatus,
    QAAnswerStatus,
)
from app.domain.legal_provision import (
    LegalProvisionVersion,
    ProvisionLevel,
    build_lineage_id,
    legal_text_checksum,
)
from app.pipelines.legal.normalize import generate_diem_id, generate_dieu_id
from app.pipelines.legal.parser import LegalParser
from app.pipelines.legal.pipeline import _build_tree
from tests.fixtures.temporal_legal import (
    LOGICAL_VB_ID,
    V2_DATE,
    V3_DATE,
    deepest_leaf_versions,
    temporal_legal_fixture,
)

ROOT = Path(__file__).resolve().parents[2]


def _point_a_versions() -> list[LegalProvisionVersion]:
    return sorted(
        [item for item in temporal_legal_fixture() if item.point == "a"],
        key=lambda item: item.version_no,
    )


def test_temporal_fixture_has_stable_lineage_and_immutable_version_ids():
    versions = _point_a_versions()

    assert len(versions) == 3
    assert len({item.lineage_id for item in versions}) == 1
    assert len({item.provision_id for item in versions}) == 3
    assert [item.version_no for item in versions] == [1, 2, 3]
    assert versions[0].effective_to == V2_DATE
    assert versions[1].effective_from == V2_DATE
    assert versions[1].effective_to == V3_DATE
    assert versions[2].effective_from == V3_DATE


def test_deepest_leaf_fixture_handles_partial_amendment_future_and_repeal():
    before = deepest_leaf_versions(date(2026, 6, 30))
    cutover = deepest_leaf_versions(V2_DATE)
    future = deepest_leaf_versions(V3_DATE)

    assert any(item.point == "a" and "200 triệu" in item.text for item in before)
    assert any(item.point == "a" and "500 triệu" in item.text for item in cutover)
    assert any(item.point == "a" and "700 triệu" in item.text for item in future)
    assert all(not (item.level == ProvisionLevel.DIEU and item.article == "5") for item in before)
    assert any(item.level == ProvisionLevel.KHOAN and item.clause == "3" for item in cutover)
    assert any(item.level == ProvisionLevel.DIEU and item.article == "6" for item in cutover)
    assert any(item.level == ProvisionLevel.DIEU and item.article == "8" for item in before)
    assert all(item.article != "8" for item in cutover)
    assert all(item.article != "7" for item in cutover)
    assert any(item.article == "7" for item in future)
    assert any(item.point == "b" for item in before)
    assert any(item.point == "b" for item in cutover)


def test_legal_provision_contract_rejects_invalid_interval_and_checksum():
    source = _point_a_versions()[0].model_dump()

    with pytest.raises(ValidationError, match="effective_to must be later"):
        LegalProvisionVersion.model_validate({
            **source,
            "effective_to": source["effective_from"],
        })

    with pytest.raises(ValidationError, match="text_checksum does not match"):
        LegalProvisionVersion.model_validate({
            **source,
            "text": "Nội dung đã bị ghi đè.",
        })

    with pytest.raises(ValidationError, match="provision_id does not match"):
        LegalProvisionVersion.model_validate({
            **source,
            "provision_id": "fabricated-version-id",
        })

def test_lineage_builder_enforces_legal_coordinates():
    assert build_lineage_id(LOGICAL_VB_ID, "5") == "FIXTURE-LAW::D5"
    assert build_lineage_id(LOGICAL_VB_ID, "5", "2") == "FIXTURE-LAW::D5.K2"
    assert build_lineage_id(LOGICAL_VB_ID, "5", "2", "a)") == "FIXTURE-LAW::D5.K2.Pa"
    with pytest.raises(ValueError, match="point requires clause"):
        build_lineage_id(LOGICAL_VB_ID, "5", point="a")


def test_citation_contract_v2_requires_reciprocal_claim_support():
    provision = _point_a_versions()[1]
    claim = AnswerClaimV2(
        claim_id="claim_1",
        text="Ngưỡng áp dụng là 500 triệu đồng.",
        citation_ids=["citation_1"],
        support_status=ClaimSupportStatus.ENTAILED,
    )
    citation = CitationV2(
        citation_id="citation_1",
        node_id=provision.provision_id,
        lineage_id=provision.lineage_id,
        level=provision.level,
        document_number="FIXTURE-LAW-V2",
        article=provision.article,
        clause=provision.clause,
        point=provision.point,
        quote=provision.text,
        effective_from=provision.effective_from,
        effective_to=provision.effective_to,
        text_checksum=provision.text_checksum,
        source_checksum=provision.source_checksum or "0" * 64,
        supports_claim_ids=["claim_1"],
        entailment_score=0.99,
    )

    contract = CitationContractV2(
        status=QAAnswerStatus.ANSWERED,
        as_of=V2_DATE,
        answer="Ngưỡng áp dụng là 500 triệu đồng.",
        claims=[claim],
        citations=[citation],
    )
    assert contract.status == QAAnswerStatus.ANSWERED

    with pytest.raises(ValidationError, match="unknown citations"):
        CitationContractV2(
            status=QAAnswerStatus.ANSWERED,
            as_of=V2_DATE,
            answer="Ngưỡng áp dụng là 500 triệu đồng.",
            claims=[claim.model_copy(update={"citation_ids": ["missing"]})],
            citations=[citation],
        )


def test_citation_contract_v2_refusal_is_fail_closed():
    refused = CitationContractV2(
        status=QAAnswerStatus.REFUSED,
        as_of=V2_DATE,
        reason_code="insufficient_legal_basis",
    )
    assert refused.answer is None
    assert refused.citations == []

    with pytest.raises(ValidationError, match="no answer/claims/citations"):
        CitationContractV2(
            status=QAAnswerStatus.REFUSED,
            as_of=V2_DATE,
            answer="Câu trả lời không có căn cứ.",
            reason_code="insufficient_legal_basis",
        )


def test_build_tree_preserves_diem_ids_lineage_text_and_checksums():
    text = """Điều 5. Ngưỡng áp dụng
2. Ngưỡng áp dụng được quy định như sau:
a) Ngưỡng áp dụng là 500 triệu đồng.
Dòng tiếp theo vẫn thuộc Điểm a.
b) Điểm b tiếp tục có hiệu lực.
"""
    parsed, needs_review = LegalParser().parse_text(text)
    tree = _build_tree("01/2026/ND-CP", parsed)

    assert needs_review is False
    assert len(tree) == 1
    dieu = tree[0]
    khoan = dieu["khoan_list"][0]
    diem_a, diem_b = khoan["diem_list"]

    assert dieu["dieu_id"] == generate_dieu_id("01/2026/ND-CP", "5")
    assert khoan["lineage_id"] == "01/2026/ND-CP::D5.K2"
    assert diem_a["diem_id"] == generate_diem_id(khoan["khoan_id"], "a")
    assert diem_a["lineage_id"] == "01/2026/ND-CP::D5.K2.Pa"
    assert diem_a["parent_lineage_id"] == khoan["lineage_id"]
    assert "Dòng tiếp theo" in diem_a["noi_dung"]
    assert diem_a["text_checksum"] == legal_text_checksum(diem_a["noi_dung"])
    assert diem_b["diem_id"].endswith(".Pb")
    assert _build_tree("01/2026/ND-CP", parsed) == tree


def test_lawgic_v2_flags_are_safe_by_default():
    config = BE2Config()
    assert config.legal_provision_v2_write is False
    assert config.legal_provision_v2_read is False
    assert config.temporal_law_v2 is False
    assert config.qa_citation_v2 is False
    assert config.qa_strict_grounding_v2 is True
    assert config.amendment_preview_v2 is False
    assert config.amendment_commit_v2 is False
    assert config.misconception_temporal_v2 is False


def test_ontology_v2_and_acceptance_contract_are_present():
    ontology = json.loads((ROOT / "Data/schema/ontology.json").read_text(encoding="utf-8"))
    constraints = (ROOT / "Data/schema/neo4j_constraints.cypher").read_text(encoding="utf-8")
    queries = (ROOT / "Data/schema/acceptance_queries.cypher").read_text(encoding="utf-8")

    assert ontology["version"] == "2.0.0"
    assert ontology["canonical_keys"]["LegalProvision"].startswith("provision_id")
    assert any("approved amendment commit" in item for item in ontology["invariants"])
    assert "legalprovision_id" in constraints
    assert "legalprovision_effective_interval" in constraints
    assert all(f"T{number:02d}" in queries for number in range(1, 16))
