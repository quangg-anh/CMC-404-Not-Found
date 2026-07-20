from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.config import BE2Config, get_config
from app.domain.amendment import (
    AmendmentReviewRoute,
    LegalChangeType,
)
from app.domain.legal_provision import ProvisionLevel, build_provision_version
from app.exceptions import TemporalLawNotFoundError, ValidationError
from app.main import app
from app.pipelines.legal.amendment_matcher import AmendmentMatcher
from app.pipelines.legal.amendment_parser import AmendmentParser
from app.pipelines.legal.change_classifier import LegalChangeClassifier
from app.services.amendment_preview_service import AmendmentPreviewService
from app.services.temporal_law_service import TemporalLawService
from tests.test_temporal_law_service import FixtureTemporalRepository


LOGICAL_ID = "01/2026/ND-CP"


def _version(
    text: str,
    *,
    effective_from: date,
    version_no: int,
    article: str = "5",
    clause: str = "2",
    point: str = "a",
    effective_to: date | None = None,
    logical_id: str = LOGICAL_ID,
) -> Any:
    return build_provision_version(
        logical_vb_id=logical_id,
        source_vb_id=f"SOURCE-V{version_no}",
        level=ProvisionLevel.DIEM,
        article=article,
        clause=clause,
        point=point,
        text=text,
        effective_from=effective_from,
        effective_to=effective_to,
        version_no=version_no,
    )


def _pair() -> tuple[Any, Any]:
    old = _version(
        "Phạt tiền 5 triệu đồng đối với hành vi vi phạm.",
        effective_from=date(2025, 1, 1),
        effective_to=date(2026, 7, 1),
        version_no=1,
    )
    new = _version(
        "Phạt tiền 10 triệu đồng đối với hành vi vi phạm.",
        effective_from=date(2026, 7, 1),
        version_no=2,
    )
    return old, new


def test_parser_extracts_deepest_coordinates_and_phrase_replacement() -> None:
    text = (
        'Thay thế cụm từ “5 triệu đồng” bằng cụm từ “10 triệu đồng” '
        "tại điểm a khoản 2 Điều 5."
    )

    references = AmendmentParser().parse(text, target_logical_vb_id=LOGICAL_ID)

    assert len(references) == 1
    reference = references[0]
    assert reference.action == "replace"
    assert reference.level == "diem"
    assert (reference.article, reference.clause, reference.point) == ("5", "2", "a")
    assert reference.target_lineage_id == f"{LOGICAL_ID}::D5.K2.Pa"
    assert (reference.old_phrase, reference.new_phrase) == ("5 triệu đồng", "10 triệu đồng")
    assert reference.complete_coordinates is True


def test_parser_keeps_incomplete_instruction_for_mandatory_review() -> None:
    references = AmendmentParser().parse("Sửa đổi quy định về mức phạt như sau")

    assert len(references) == 1
    assert references[0].complete_coordinates is False
    assert references[0].target_lineage_id is None


@pytest.mark.parametrize(
    ("old_text", "new_text", "expected"),
    [
        (
            "Phạt tiền 5 triệu đồng đối với hành vi vi phạm.",
            "Phạt tiền 10 triệu đồng đối với hành vi vi phạm.",
            LegalChangeType.TIGHTENED,
        ),
        (
            "Phạt tiền 10 triệu đồng đối với hành vi vi phạm.",
            "Phạt tiền 5 triệu đồng đối với hành vi vi phạm.",
            LegalChangeType.LOOSENED,
        ),
        (
            "Cá nhân phải nộp hồ sơ hợp lệ tại cơ quan nhà nước có thẩm quyền đúng thời hạn.",
            "Cá nhân phải nộp hồ sơ đầy đủ, hợp lệ tại cơ quan nhà nước có thẩm quyền đúng thời hạn.",
            LegalChangeType.REWORDED,
        ),
        (
            "Ngưỡng doanh thu là 200 triệu đồng.",
            "Ngưỡng doanh thu là 500 triệu đồng.",
            LegalChangeType.UNCERTAIN,
        ),
        ("", "Quy định mới.", LegalChangeType.ADDED),
        ("Quy định cũ.", "", LegalChangeType.REMOVED),
    ],
)
def test_change_classifier_is_conservative(
    old_text: str,
    new_text: str,
    expected: LegalChangeType,
) -> None:
    change_type, reasons = LegalChangeClassifier().classify(old_text, new_text)

    assert change_type == expected
    assert reasons


def test_matcher_produces_explainable_preview_and_never_auto_approves() -> None:
    old, new = _pair()
    references = AmendmentParser().parse(
        "Sửa đổi điểm a khoản 2 Điều 5 như sau:",
        target_logical_vb_id=LOGICAL_ID,
    )

    result = AmendmentMatcher().match(
        target_logical_vb_id=LOGICAL_ID,
        old_versions=[old],
        new_versions=[new],
        references=references,
    )

    assert result.mode == "preview"
    assert result.commit_allowed is False
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.change_type == LegalChangeType.TIGHTENED
    assert match.score.explicit_reference == 1
    assert match.score.coordinate_match == 1
    assert match.confidence == match.score.total
    assert match.review_route == AmendmentReviewRoute.HUMAN_REVIEW
    assert match.auto_approve_eligible is False
    assert "independent_precision_gate_not_met" in match.reason_codes
    assert "preview_only_no_graph_mutation" in result.warnings


def test_matcher_detects_possible_split_and_requires_review() -> None:
    old, new = _pair()
    second_new = _version(
        "Phạt tiền 10 triệu đồng đối với hành vi vi phạm lần đầu.",
        effective_from=date(2026, 7, 1),
        version_no=2,
        point="b",
    )
    references = AmendmentParser().parse(
        "Sửa đổi điểm a khoản 2 Điều 5 như sau:",
        target_logical_vb_id=LOGICAL_ID,
    )

    result = AmendmentMatcher().match(
        target_logical_vb_id=LOGICAL_ID,
        old_versions=[old],
        new_versions=[new, second_new],
        references=references,
    )

    assert result.matches[0].change_type == LegalChangeType.SPLIT
    assert result.matches[0].review_route == AmendmentReviewRoute.MANDATORY_REVIEW
    assert "possible_split_detected" in result.warnings
    assert len(result.unmatched_new_ids) == 1
    assert result.unmatched_changes[0].change_type == LegalChangeType.ADDED
    assert result.unmatched_changes[0].review_route == AmendmentReviewRoute.MANDATORY_REVIEW


def test_phrase_replacement_mismatch_requires_mandatory_review() -> None:
    old = _version(
        "Mức phạt là 5 triệu đồng.",
        effective_from=date(2025, 1, 1),
        effective_to=date(2026, 7, 1),
        version_no=1,
    )
    new = _version(
        "Mức phạt là 10 triệu đồng.",
        effective_from=date(2026, 7, 1),
        version_no=2,
    )
    references = AmendmentParser().parse(
        'Thay thế cụm từ “6 triệu đồng” bằng cụm từ “10 triệu đồng” tại điểm a khoản 2 Điều 5.',
        target_logical_vb_id=LOGICAL_ID,
    )

    result = AmendmentMatcher().match(
        target_logical_vb_id=LOGICAL_ID,
        old_versions=[old],
        new_versions=[new],
        references=references,
    )

    assert result.matches[0].review_route == AmendmentReviewRoute.MANDATORY_REVIEW
    assert "old_phrase_not_found_in_canonical_text" in result.matches[0].reason_codes


class StubCanonicalTemporal:
    def __init__(self, by_id: dict[str, Any]) -> None:
        self.by_id = by_id
        self.calls: list[tuple[list[str], str]] = []

    async def load_versions_by_ids(self, ids: list[str], *, audience: str) -> list[Any]:
        self.calls.append((list(ids), audience))
        return [self.by_id[item] for item in ids]


@pytest.mark.anyio
async def test_preview_service_loads_both_sides_canonically() -> None:
    old, new = _pair()
    temporal = StubCanonicalTemporal({old.provision_id: old, new.provision_id: new})

    result = await AmendmentPreviewService(temporal).preview(
        amendment_text="Sửa đổi điểm a khoản 2 Điều 5 như sau:",
        old_provision_ids=[old.provision_id],
        new_provision_ids=[new.provision_id],
    )

    assert result.target_logical_vb_id == LOGICAL_ID
    assert temporal.calls == [
        ([old.provision_id], "admin"),
        ([new.provision_id], "admin"),
    ]


@pytest.mark.anyio
async def test_preview_service_rejects_new_candidate_from_another_document() -> None:
    old, _ = _pair()
    foreign_new = _version(
        "Mức phạt là 10 triệu đồng.",
        effective_from=date(2026, 7, 1),
        version_no=2,
        logical_id="02/2026/ND-CP",
    )
    temporal = StubCanonicalTemporal(
        {old.provision_id: old, foreign_new.provision_id: foreign_new}
    )

    with pytest.raises(ValidationError, match="new candidates do not belong"):
        await AmendmentPreviewService(temporal).preview(
            amendment_text="Sửa đổi điểm a khoản 2 Điều 5 như sau:",
            old_provision_ids=[old.provision_id],
            new_provision_ids=[foreign_new.provision_id],
        )


@pytest.mark.anyio
async def test_preview_service_rejects_same_physical_id_on_both_sides() -> None:
    old, _ = _pair()
    temporal = StubCanonicalTemporal({old.provision_id: old})

    with pytest.raises(ValidationError, match="different physical versions"):
        await AmendmentPreviewService(temporal).preview(
            amendment_text="Sửa đổi Điều 5",
            old_provision_ids=[old.provision_id],
            new_provision_ids=[old.provision_id],
        )
    assert temporal.calls == []


@pytest.mark.anyio
async def test_temporal_loader_fails_closed_for_missing_physical_ids() -> None:
    old, _ = _pair()
    service = TemporalLawService(FixtureTemporalRepository([old]))

    with pytest.raises(TemporalLawNotFoundError) as exc_info:
        await service.load_versions_by_ids([old.provision_id, "fabricated"], audience="admin")

    assert exc_info.value.details["missing_provision_ids"] == ["fabricated"]


@pytest.mark.anyio
async def test_amendment_preview_api_is_hidden_while_flag_is_off() -> None:
    old, new = _pair()
    temporal = StubCanonicalTemporal({old.provision_id: old, new.provision_id: new})

    async def service_override() -> StubCanonicalTemporal:
        return temporal

    async def config_override() -> BE2Config:
        return BE2Config(legal_provision_v2_read=True, amendment_preview_v2=False)

    app.dependency_overrides[deps.get_temporal_law_service] = service_override
    app.dependency_overrides[get_config] = config_override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/admin/legal/amendments/preview",
                headers={"Authorization": "Bearer test-admin-phap-che"},
                json={
                    "amendment_text": "Sửa đổi điểm a khoản 2 Điều 5",
                    "old_provision_ids": [old.provision_id],
                    "new_provision_ids": [new.provision_id],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert temporal.calls == []


@pytest.mark.anyio
async def test_enabled_amendment_preview_api_returns_non_mutating_contract() -> None:
    old, new = _pair()
    temporal = StubCanonicalTemporal({old.provision_id: old, new.provision_id: new})

    async def service_override() -> StubCanonicalTemporal:
        return temporal

    async def config_override() -> BE2Config:
        return BE2Config(legal_provision_v2_read=True, amendment_preview_v2=True)

    app.dependency_overrides[deps.get_temporal_law_service] = service_override
    app.dependency_overrides[get_config] = config_override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/admin/legal/amendments/preview",
                headers={"Authorization": "Bearer test-admin-phap-che"},
                json={
                    "amendment_text": "Sửa đổi điểm a khoản 2 Điều 5",
                    "old_provision_ids": [old.provision_id],
                    "new_provision_ids": [new.provision_id],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "preview"
    assert data["commit_allowed"] is False
    assert data["matches"][0]["auto_approve_eligible"] is False
