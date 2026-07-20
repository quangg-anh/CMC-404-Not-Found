from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.adapters.neo4j_legal_v2 import prepare_legal_provision_rows
from app.adapters.qdrant_vector import QdrantVectorClient
from app.pipelines.legal.provision_index import (
    LEGAL_PROVISION_COLLECTION,
    build_legal_provision_points,
    deterministic_provision_point_id,
    legal_provision_payload,
    reindex_legal_provisions_from_neo4j,
    select_deepest_leaf_rows,
)
from app.services.legal_migration_inventory import build_migration_inventory
from app.services.legal_shadow_parity import build_shadow_parity_report


def _document() -> dict[str, Any]:
    return {
        "vb_id": "vb-source-1",
        "so_hieu": "01/2026/ND-CP",
        "logical_vb_id": "01/2026/ND-CP",
        "ngay_hieu_luc": "2026-07-01",
        "source_checksum": "a" * 64,
        "visibility": "public",
        "dieu_list": [
            {
                "dieu_id": "d1",
                "so": "1",
                "tieu_de": "Quy dinh chung",
                "noi_dung": "",
                "khoan_list": [
                    {
                        "khoan_id": "k1",
                        "so": "1",
                        "noi_dung": "Cac truong hop sau day.",
                        "diem_list": [
                            {"diem_id": "p-a", "ky_hieu": "a", "noi_dung": "Truong hop A."},
                            {"diem_id": "p-b", "ky_hieu": "b", "noi_dung": "Truong hop B."},
                        ],
                    }
                ],
            },
            {
                "dieu_id": "d2",
                "so": "2",
                "tieu_de": "Dieu doc lap",
                "noi_dung": "Dieu nay khong co khoan.",
                "khoan_list": [],
            },
        ],
    }


def test_deepest_leaf_selection_keeps_point_or_clause_or_article():
    leaves = select_deepest_leaf_rows(prepare_legal_provision_rows(_document()))

    assert len(leaves) == 3
    assert sorted(row["level"] for row in leaves) == ["diem", "diem", "dieu"]
    assert {row.get("point") for row in leaves if row["level"] == "diem"} == {"a", "b"}
    assert any(row["level"] == "dieu" and row["article"] == "2" for row in leaves)


def test_payload_is_id_only_and_point_id_is_stable():
    row = select_deepest_leaf_rows(prepare_legal_provision_rows(_document()))[0]
    payload = legal_provision_payload(row)
    points = build_legal_provision_points([row], [[0.1, 0.2]])

    assert "text" not in payload
    assert "noi_dung" not in payload
    assert "text_preview" not in payload
    assert payload["provision_id"] == row["provision_id"]
    assert payload["effective_from"] == "2026-07-01T00:00:00Z"
    assert payload["review_status"] == "approved"
    assert points[0]["id"] == deterministic_provision_point_id(row["provision_id"])
    assert deterministic_provision_point_id(row["provision_id"]) == deterministic_provision_point_id(row["provision_id"])


class _Record(dict):
    def data(self):
        return dict(self)


class _Result:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for row in self.rows:
            yield _Record(row)


class _Session:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def run(self, _query: str, **params: Any):
        rows = self.rows
        resume_from = params.get("resume_from")
        if resume_from:
            rows = [row for row in rows if row["provision_id"] > resume_from]
        return _Result(rows)


class _Driver:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def session(self):
        return _Session(self.rows)


class _Embedder:
    async def embed_texts(self, texts: list[str]):
        return [[float(index), 1.0] for index, _text in enumerate(texts)]


class _Qdrant:
    def __init__(self, existing: set[str] | None = None):
        self.existing = set(existing or set())
        self.checksums = {provision_id: provision_id * 8 for provision_id in self.existing}
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []

    async def list_payload_records(self, collection: str, keys: list[str]):
        assert collection == LEGAL_PROVISION_COLLECTION
        return [
            {"provision_id": provision_id, "text_checksum": self.checksums[provision_id]}
            for provision_id in sorted(self.existing)
        ]

    async def list_payload_values(self, collection: str, key: str):
        assert collection == LEGAL_PROVISION_COLLECTION
        assert key == "provision_id"
        return set(self.existing)

    async def upsert(self, collection: str, points: list[dict[str, Any]]):
        self.upserts.append((collection, points))
        for point in points:
            provision_id = str(point["payload"]["provision_id"])
            self.existing.add(provision_id)
            self.checksums[provision_id] = str(point["payload"]["text_checksum"])


def _leaf(provision_id: str) -> dict[str, Any]:
    return {
        "provision_id": provision_id,
        "lineage_id": f"lineage-{provision_id}",
        "level": "diem",
        "logical_vb_id": "law-1",
        "source_vb_id": "source-1",
        "effective_from": "2026-07-01",
        "effective_to": None,
        "visibility": "public",
        "text_checksum": provision_id * 8,
        "text": f"Noi dung {provision_id}",
    }


@pytest.mark.asyncio
async def test_reindex_is_resumable_and_idempotent():
    driver = _Driver([_leaf("p1"), _leaf("p2"), _leaf("p3")])
    qdrant = _Qdrant(existing={"p2"})

    first = await reindex_legal_provisions_from_neo4j(
        driver,
        qdrant,
        _Embedder(),
        batch_size=1,
    )
    second = await reindex_legal_provisions_from_neo4j(
        driver,
        qdrant,
        _Embedder(),
        batch_size=2,
    )

    assert first["status"] == "success"
    assert first["indexed"] == 2
    assert first["skipped_existing"] == 1
    assert first["checkpoint"] == "p3"
    assert second["indexed"] == 0
    assert second["skipped_existing"] == 3
    assert all("text" not in point["payload"] for _, points in qdrant.upserts for point in points)

@pytest.mark.asyncio
async def test_reindex_repairs_existing_id_when_checksum_is_stale():
    qdrant = _Qdrant(existing={"p1"})
    qdrant.checksums["p1"] = "stale"

    report = await reindex_legal_provisions_from_neo4j(
        _Driver([_leaf("p1")]),
        qdrant,
        _Embedder(),
    )

    assert report["indexed"] == 1
    assert report["checksum_mismatches"] == 1
    assert qdrant.checksums["p1"] == _leaf("p1")["text_checksum"]

def test_inventory_reports_source_gap_without_guessing_point_loss():
    rows = [
        {
            "vb_id": "safe",
            "so_hieu": "01/2026",
            "ngay_hieu_luc": "2026-07-01",
            "source_checksum": "a" * 64,
            "source_filename": "safe.pdf",
            "dieu_id": "d1",
            "dieu_text": "Dieu 1",
            "khoan_id": "k1",
            "khoan_text": "Khoan 1",
            "diem_id": "p1",
            "diem_text": "Diem a",
        },
        {
            "vb_id": "needs-source",
            "so_hieu": "02/2026",
            "ngay_ban_hanh": "2026-01-01",
            "dieu_id": "d2",
            "dieu_text": "Dieu 2",
            "khoan_id": "k2",
            "khoan_text": "Khoan 2",
        },
    ]

    report = build_migration_inventory(rows)
    by_id = {doc["vb_id"]: doc for doc in report["documents"]}

    assert report["mutated"] is False
    assert by_id["safe"]["status"] == "eligible_dry_run_upgrade"
    assert by_id["needs-source"]["status"] == "requires_reingest"
    assert by_id["needs-source"]["point_coverage_unverified"] is True
    assert "raw_source_required_to_verify_points" in by_id["needs-source"]["reasons"]


def test_shadow_parity_detects_missing_extra_and_duplicate_ids():
    report = build_shadow_parity_report(
        ["p1", "p2", "p2"],
        ["p1", "p3"],
        neo4j_checksums={"p1": "new"},
        qdrant_checksums={"p1": "stale"},
    )

    assert report["status"] == "mismatch"
    assert report["missing_in_qdrant"] == ["p2"]
    assert report["extra_in_qdrant"] == ["p3"]
    assert report["duplicate_neo4j_ids"] == ["p2"]
    assert report["checksum_mismatch_ids"] == ["p1"]

class _Point:
    def __init__(self, provision_id: str):
        self.payload = {"provision_id": provision_id}


class _RawQdrant:
    async def scroll(self, *, offset: str | None, **_kwargs: Any):
        if offset is None:
            return [_Point("p1"), _Point("p1")], "next"
        return [_Point("p2")], None


@pytest.mark.asyncio
async def test_qdrant_adapter_can_preserve_duplicates_for_parity():
    adapter = QdrantVectorClient(_RawQdrant())

    values = await adapter.list_payload_field_values("legal_provision", "provision_id")
    unique = await adapter.list_payload_values("legal_provision", "provision_id")

    assert values == ["p1", "p1", "p2"]
    assert unique == {"p1", "p2"}


def test_qdrant_collection_contract_excludes_canonical_legal_text():
    spec_path = Path(__file__).resolve().parents[2] / "Data" / "schema" / "qdrant" / "collections.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    collection = next(item for item in spec["collections"] if item["name"] == "legal_provision")

    assert spec["version"] == "2.0.0"
    assert {"provision_id", "lineage_id", "effective_from", "effective_to"} <= set(collection["payload_schema"])
    assert not ({"text", "noi_dung", "quote"} & set(collection["payload_schema"]))

def test_inventory_does_not_accept_broken_v2_nodes_as_complete():
    report = build_migration_inventory(
        [
            {
                "vb_id": "broken-v2",
                "ngay_hieu_luc": "2026-07-01",
                "source_checksum": "a" * 64,
                "source_filename": "broken.pdf",
                "dieu_id": "d1",
                "dieu_provision_id": "provision-d1",
                "dieu_text": "",
            }
        ]
    )

    assert report["documents"][0]["status"] == "requires_reingest"
    assert "missing_canonical_text" in report["documents"][0]["reasons"]