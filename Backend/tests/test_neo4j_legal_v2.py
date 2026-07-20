from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest

from app.adapters.neo4j_legal import Neo4jLegalRepository
from app.adapters.neo4j_legal_v2 import prepare_legal_provision_rows
from app.api.admin.legal import IngestLegalRequest
from app.config import BE2Config
from app.pipelines.legal.normalize import normalize_so_hieu
from app.pipelines.legal.parser import LegalParser
from app.pipelines.legal.pipeline import _build_tree, run_legal_ingest


LEGAL_TEXT = """Điều 5. Ngưỡng áp dụng
2. Ngưỡng áp dụng được quy định như sau:
a) Ngưỡng áp dụng là 500 triệu đồng.
b) Điểm b tiếp tục có hiệu lực.
Điều 6. Điều độc lập
Điều này không có Khoản và phải được giữ ở cấp Điều.
"""


class _Result:
    def __init__(self, records: list[dict[str, Any]] | None = None):
        self.records = records or []

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for record in self.records:
            yield record

    async def single(self):
        return self.records[0] if self.records else None

    async def consume(self):
        return None


class _Store:
    def __init__(self):
        self.nodes_by_compatibility: dict[str, dict[str, Any]] = {}
        self.nodes_by_provision: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, dict[str, Any]] = {}
        self.relationships: set[tuple[str, str, str]] = set()
        self.write_query_count = 0


class _Transaction:
    def __init__(self, store: _Store):
        self.store = store

    async def run(self, query: str, **params: Any):
        marker = query.lower()
        if "legal_v2_preflight_" in marker:
            return _Result([self._preflight(row) for row in params["rows"]])
        if "legal_v2_write_document" in marker:
            self.store.documents[str(params["vb_id"])] = dict(params)
            self.store.write_query_count += 1
            return _Result()
        for level in ("dieu", "khoan", "diem"):
            if f"legal_v2_write_{level}" in marker:
                count = 0
                for row in params["rows"]:
                    if self._write_row(level, row):
                        count += 1
                self.store.write_query_count += 1
                return _Result([{"written_count": count}])
        raise AssertionError(f"Unexpected Cypher marker: {query[:80]}")

    def _preflight(self, row: dict[str, Any]) -> dict[str, Any]:
        legacy = self.store.nodes_by_compatibility.get(row["compatibility_id"])
        version = self.store.nodes_by_provision.get(row["provision_id"])
        return {
            "requested_id": row["provision_id"],
            "compatibility_id": row["compatibility_id"],
            "legacy_found": legacy is not None,
            "legacy_provision_id": legacy.get("provision_id") if legacy else None,
            "legacy_checksum": legacy.get("text_checksum") if legacy else None,
            "legacy_text": legacy.get("legacy_text") if legacy else None,
            "version_found": version is not None,
            "version_provision_id": version.get("provision_id") if version else None,
            "version_checksum": version.get("text_checksum") if version else None,
            "version_lineage_id": version.get("lineage_id") if version else None,
            "version_level": version.get("level") if version else None,
            "existing_effective_from": (
                version.get("effective_from") if version else legacy.get("effective_from") if legacy else None
            ),
            "existing_effective_to": (
                version.get("effective_to") if version else legacy.get("effective_to") if legacy else None
            ),
            "existing_source_vb_id": (
                version.get("source_vb_id") if version else legacy.get("source_vb_id") if legacy else None
            ),
            "existing_source_checksum": (
                version.get("source_checksum") if version else legacy.get("source_checksum") if legacy else None
            ),
            "existing_version_no": (
                version.get("version_no") if version else legacy.get("version_no") if legacy else None
            ),
        }

    def _write_row(self, level: str, row: dict[str, Any]) -> bool:
        existing = self.store.nodes_by_compatibility.get(row["compatibility_id"])
        if existing and existing.get("provision_id"):
            immutable_fields = (
                "provision_id",
                "text_checksum",
                "lineage_id",
                "level",
                "version_no",
                "source_vb_id",
                "source_checksum",
                "effective_from",
                "effective_to",
            )
            if any(existing.get(field) != row.get(field) for field in immutable_fields):
                return False

        node = dict(row)
        node["legacy_text"] = row["title"] if level == "dieu" else row["text"]
        self.store.nodes_by_compatibility[row["compatibility_id"]] = node
        self.store.nodes_by_provision[row["provision_id"]] = node
        if row.get("parent_provision_id"):
            relation = "CO_KHOAN" if level == "khoan" else "CO_DIEM"
            self.store.relationships.add(
                (row["parent_provision_id"], relation, row["provision_id"])
            )
        else:
            self.store.relationships.add((row["source_vb_id"], "CO_DIEU", row["provision_id"]))
        return True


class _Session:
    def __init__(self, store: _Store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute_write(self, callback, *args):
        staged = copy.deepcopy(self.store)
        result = await callback(_Transaction(staged), *args)
        self.store.nodes_by_compatibility = staged.nodes_by_compatibility
        self.store.nodes_by_provision = staged.nodes_by_provision
        self.store.documents = staged.documents
        self.store.relationships = staged.relationships
        self.store.write_query_count = staged.write_query_count
        return result


class _Driver:
    def __init__(self):
        self.store = _Store()

    def session(self):
        return _Session(self.store)


def _document(text: str = LEGAL_TEXT) -> dict[str, Any]:
    so_hieu = normalize_so_hieu("01/2026/NĐ-CP")
    tree, needs_review = LegalParser().parse_text(text)
    assert needs_review is False
    return {
        "vb_id": "source-v1",
        "so_hieu": so_hieu,
        "logical_vb_id": so_hieu,
        "ten": "Văn bản fixture",
        "ngay_ban_hanh": "2026-01-01",
        "ngay_hieu_luc": "2026-07-01",
        "visibility": "public",
        "source_checksum": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "dieu_list": _build_tree(so_hieu, tree),
    }


def test_ingest_request_accepts_temporal_metadata_for_v2():
    request = IngestLegalRequest(
        so_hieu="01/2026/NĐ-CP",
        ngay_ban_hanh="2026-01-01",
        ngay_hieu_luc="2026-07-01",
        logical_vb_id="BASE-LAW",
        version_no=2,
    )

    payload = request.model_dump()
    assert payload["ngay_hieu_luc"] == "2026-07-01"
    assert payload["logical_vb_id"] == "BASE-LAW"
    assert payload["version_no"] == 2


def test_parser_keeps_real_article_without_synthetic_clause():
    tree, needs_review = LegalParser().parse_text(LEGAL_TEXT)

    assert needs_review is False
    article = tree[1]
    assert article["so"] == "6"
    assert article["khoan_list"] == []
    assert "không có Khoản" in article["noi_dung"]


def test_prepare_rows_preserves_all_levels_and_parent_versions():
    rows = prepare_legal_provision_rows(_document())
    by_level = {level: [row for row in rows if row["level"] == level] for level in ("dieu", "khoan", "diem")}

    assert {level: len(items) for level, items in by_level.items()} == {
        "dieu": 2,
        "khoan": 1,
        "diem": 2,
    }
    article_6 = next(row for row in by_level["dieu"] if row["article"] == "6")
    assert "không có Khoản" in article_6["text"]
    clause = by_level["khoan"][0]
    assert clause["parent_provision_id"] in {row["provision_id"] for row in by_level["dieu"]}
    assert all(row["parent_provision_id"] == clause["provision_id"] for row in by_level["diem"])


@pytest.mark.asyncio
async def test_v2_writer_is_idempotent_and_writes_every_level_once():
    driver = _Driver()
    repo = Neo4jLegalRepository(driver)

    first = await repo.upsert_van_ban_v2(_document())
    second = await repo.upsert_van_ban_v2(_document())

    assert first["status"] == "written"
    assert first["counts"]["created"] == {"dieu": 2, "khoan": 1, "diem": 2}
    assert second["status"] == "idempotent"
    assert second["counts"]["idempotent"] == {"dieu": 2, "khoan": 1, "diem": 2}
    assert len(driver.store.nodes_by_provision) == 5
    assert len(driver.store.relationships) == 5


@pytest.mark.asyncio
async def test_v2_writer_rejects_changed_point_without_mutating_sibling():
    driver = _Driver()
    repo = Neo4jLegalRepository(driver)
    original = _document()
    await repo.upsert_van_ban_v2(original)
    point_b = next(
        node for node in driver.store.nodes_by_provision.values() if node.get("point") == "b"
    )
    point_b_snapshot = copy.deepcopy(point_b)
    node_count = len(driver.store.nodes_by_provision)
    write_count = driver.store.write_query_count

    changed = _document(LEGAL_TEXT.replace("500 triệu", "700 triệu"))
    report = await repo.upsert_van_ban_v2(changed)

    assert report["status"] == "conflict"
    assert any(
        conflict["reason"] == "compatibility_id_already_bound_to_another_version"
        and conflict["level"] == "diem"
        for conflict in report["conflicts"]
    )
    assert len(driver.store.nodes_by_provision) == node_count
    assert driver.store.write_query_count == write_count
    assert driver.store.nodes_by_provision[point_b_snapshot["provision_id"]] == point_b_snapshot


@pytest.mark.asyncio
async def test_normal_ingest_cannot_close_an_existing_effective_interval():
    driver = _Driver()
    repo = Neo4jLegalRepository(driver)
    doc = _document()
    await repo.upsert_van_ban_v2(doc)
    write_count = driver.store.write_query_count

    attempted_close = copy.deepcopy(doc)
    attempted_close["effective_to"] = "2027-01-01"
    report = await repo.upsert_van_ban_v2(attempted_close)

    assert report["status"] == "conflict"
    assert any(
        conflict["reason"] == "immutable_node_effective_to_mismatch"
        for conflict in report["conflicts"]
    )
    assert driver.store.write_query_count == write_count
    assert all(node["effective_to"] is None for node in driver.store.nodes_by_provision.values())


@pytest.mark.asyncio
async def test_v2_writer_rejects_changed_source_checksum_for_same_version():
    driver = _Driver()
    repo = Neo4jLegalRepository(driver)
    doc = _document()
    await repo.upsert_van_ban_v2(doc)
    write_count = driver.store.write_query_count

    same_text_different_source = copy.deepcopy(doc)
    same_text_different_source["source_checksum"] = "f" * 64
    report = await repo.upsert_van_ban_v2(same_text_different_source)

    assert report["status"] == "conflict"
    assert any(
        conflict["reason"] == "immutable_node_source_checksum_mismatch"
        for conflict in report["conflicts"]
    )
    assert driver.store.write_query_count == write_count


@pytest.mark.asyncio
async def test_v2_dry_run_reports_counts_without_mutation():
    driver = _Driver()
    report = await Neo4jLegalRepository(driver).upsert_van_ban_v2(_document(), dry_run=True)

    assert report["status"] == "dry_run"
    assert report["dry_run"] is True
    assert report["counts"]["created"] == {"dieu": 2, "khoan": 1, "diem": 2}
    assert driver.store.nodes_by_provision == {}
    assert driver.store.documents == {}


@pytest.mark.asyncio
async def test_v2_writer_upgrades_matching_legacy_node():
    driver = _Driver()
    doc = _document()
    article = doc["dieu_list"][0]
    driver.store.nodes_by_compatibility[article["dieu_id"]] = {
        "legacy_text": article["tieu_de"],
        "provision_id": None,
    }

    report = await Neo4jLegalRepository(driver).upsert_van_ban_v2(doc)

    assert report["status"] == "written"
    assert report["counts"]["upgraded"]["dieu"] == 1
    assert report["counts"]["created"]["dieu"] == 1


@pytest.mark.asyncio
async def test_v2_writer_rejects_missing_effective_date_before_transaction():
    driver = _Driver()
    doc = _document()
    doc["ngay_hieu_luc"] = None
    doc["ngay_ban_hanh"] = None

    report = await Neo4jLegalRepository(driver).upsert_van_ban_v2(doc)

    assert report["status"] == "invalid"
    assert "effective_from is required" in report["reason"]
    assert driver.store.write_query_count == 0


@pytest.mark.asyncio
async def test_ingest_uses_v2_atomic_writer_only_when_flag_is_enabled():
    driver = _Driver()
    result = await run_legal_ingest(
        driver,
        {
            "so_hieu": "01/2026/NĐ-CP",
            "ten": "Văn bản fixture",
            "ngay_ban_hanh": "2026-01-01",
            "ngay_hieu_luc": "2026-07-01",
            "url_or_content": LEGAL_TEXT,
        },
        run_ner=False,
        config=BE2Config(legal_provision_v2_write=True),
    )

    assert result["status"] == "success"
    assert result["write_mode"] == "legal_provision_v2"
    assert result["v2_write_report"]["status"] == "written"
    assert result["dieu_count"] == 2
    assert result["khoan_count"] == 1
    assert result["diem_count"] == 2

class _VectorSink:
    def __init__(self):
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def upsert(self, collection: str, points: list[dict[str, Any]]) -> None:
        self.calls.append((collection, points))


class _DeterministicEmbedder:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), 1.0] for index, _text in enumerate(texts)]


@pytest.mark.asyncio
async def test_v2_ingest_dual_indexes_leaf_nodes_without_switching_legacy_read_path():
    driver = _Driver()
    qdrant = _VectorSink()

    result = await run_legal_ingest(
        driver,
        {
            "so_hieu": "01/2026/ND-CP",
            "ten": "Van ban fixture",
            "ngay_ban_hanh": "2026-01-01",
            "ngay_hieu_luc": "2026-07-01",
            "url_or_content": LEGAL_TEXT,
        },
        qdrant=qdrant,
        embedder=_DeterministicEmbedder(),
        run_ner=False,
        config=BE2Config(legal_provision_v2_write=True, legal_provision_v2_read=False),
    )

    by_collection = {collection: points for collection, points in qdrant.calls}
    assert result["indexed_count"] == 1
    assert result["v2_indexed_count"] == 3
    assert set(by_collection) == {"khoan", "legal_provision"}
    assert len(by_collection["legal_provision"]) == 3
    assert all("text" not in point["payload"] for point in by_collection["legal_provision"])
    assert all("noi_dung" not in point["payload"] for point in by_collection["legal_provision"])
