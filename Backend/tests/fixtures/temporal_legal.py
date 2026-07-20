from __future__ import annotations

import hashlib
from datetime import date

from app.domain.legal_provision import (
    LegalProvisionVersion,
    ProvisionLevel,
    build_provision_version,
)

LOGICAL_VB_ID = "FIXTURE-LAW"
V1_DATE = date(2020, 1, 1)
V2_DATE = date(2026, 7, 1)
V3_DATE = date(2027, 1, 1)


def _source_checksum(source_id: str) -> str:
    return hashlib.sha256(source_id.encode("utf-8")).hexdigest()


def temporal_legal_fixture() -> list[LegalProvisionVersion]:
    """Fixture covering partial amendment, three versions, future and repeal."""
    shared = {
        "logical_vb_id": LOGICAL_VB_ID,
        "visibility": "public",
    }
    return [
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.DIEU,
            article="5",
            text="Điều về ngưỡng áp dụng.",
            effective_from=V1_DATE,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.KHOAN,
            article="5",
            clause="2",
            text="Ngưỡng áp dụng được quy định như sau:",
            effective_from=V1_DATE,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.DIEM,
            article="5",
            clause="2",
            point="a",
            text="Ngưỡng áp dụng là 200 triệu đồng.",
            effective_from=V1_DATE,
            effective_to=V2_DATE,
            version_no=1,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V2",
            source_checksum=_source_checksum("FIXTURE-LAW-V2"),
            level=ProvisionLevel.DIEM,
            article="5",
            clause="2",
            point="a",
            text="Ngưỡng áp dụng là 500 triệu đồng.",
            effective_from=V2_DATE,
            effective_to=V3_DATE,
            version_no=2,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V3",
            source_checksum=_source_checksum("FIXTURE-LAW-V3"),
            level=ProvisionLevel.DIEM,
            article="5",
            clause="2",
            point="a",
            text="Ngưỡng áp dụng là 700 triệu đồng.",
            effective_from=V3_DATE,
            version_no=3,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.DIEM,
            article="5",
            clause="2",
            point="b",
            text="Điểm b tiếp tục có hiệu lực và không bị sửa đổi.",
            effective_from=V1_DATE,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.KHOAN,
            article="5",
            clause="3",
            text="Khoản này không có Điểm.",
            effective_from=V1_DATE,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.DIEU,
            article="6",
            text="Điều này không có Khoản.",
            effective_from=V1_DATE,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V3",
            source_checksum=_source_checksum("FIXTURE-LAW-V3"),
            level=ProvisionLevel.DIEU,
            article="7",
            text="Điều này có hiệu lực trong tương lai.",
            effective_from=V3_DATE,
        ),
        build_provision_version(
            **shared,
            source_vb_id="FIXTURE-LAW-V1",
            source_checksum=_source_checksum("FIXTURE-LAW-V1"),
            level=ProvisionLevel.DIEU,
            article="8",
            text="Điều này bị bãi bỏ từ ngày 01 tháng 07 năm 2026.",
            effective_from=V1_DATE,
            effective_to=V2_DATE,
        ),
    ]


def active_versions(as_of: date) -> list[LegalProvisionVersion]:
    return [item for item in temporal_legal_fixture() if item.is_effective_on(as_of)]


def deepest_leaf_versions(as_of: date) -> list[LegalProvisionVersion]:
    """Reference implementation for expected fixture behavior, not production query code."""
    active = active_versions(as_of)
    parent_lineages = {
        item.parent_lineage_id
        for item in active
        if item.parent_lineage_id is not None
    }
    return [item for item in active if item.lineage_id not in parent_lineages]
