from __future__ import annotations

from typing import Any
from app.schemas import CandidateKhoan


class Neo4jLegalRepository:
    """Read-only legal repository over Neo4j Khoan nodes (source of truth for canonical text).

    Implements the LegalRepository protocol used by brief/suggest generation pipelines.
    """

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    @staticmethod
    def _to_candidate(record: Any) -> CandidateKhoan:
        return CandidateKhoan(
            khoan_id=str(record["khoan_id"]),
            noi_dung=str(record["noi_dung"] or ""),
            score=1.0,
        )

    async def get_khoan(self, khoan_id: str) -> CandidateKhoan | None:
        if not self.driver or not hasattr(self.driver, "session"):
            return None
        query = "MATCH (k:Khoan {khoan_id: $id}) RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung"
        async with self.driver.session() as session:
            res = await session.run(query, id=khoan_id)
            record = await res.single()
        if not record or not record["khoan_id"] or not record["noi_dung"]:
            return None
        return self._to_candidate(record)

    async def get_khoan_many(self, khoan_ids: list[str]) -> list[CandidateKhoan]:
        if not khoan_ids or not self.driver or not hasattr(self.driver, "session"):
            return []
        query = (
            "MATCH (k:Khoan) WHERE k.khoan_id IN $ids "
            "RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung"
        )
        out: list[CandidateKhoan] = []
        async with self.driver.session() as session:
            res = await session.run(query, ids=list(khoan_ids))
            async for record in res:
                if record["khoan_id"] and record["noi_dung"]:
                    out.append(self._to_candidate(record))
        return out

    async def upsert_van_ban(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Write/merge a legal document tree (VanBanPhapLuat -> Dieu -> Khoan) into Neo4j.

        `doc` must contain metadata plus `dieu_list`, where each Dieu carries `dieu_id`,
        `so`, `tieu_de`, and `khoan_list` (each with `khoan_id`, `so`, `noi_dung`).
        Merge keys match Data/schema/neo4j_constraints.cypher (vb_id/dieu_id/khoan_id).
        """
        if not self.driver or not hasattr(self.driver, "session"):
            return {"written": False, "reason": "neo4j_unavailable"}

        dieu_list = doc.get("dieu_list", [])
        query = """
        MERGE (v:VanBanPhapLuat {vb_id: $vb_id})
        SET v.so_hieu = $so_hieu, v.ten = $ten, v.loai = $loai,
            v.ngay_ban_hanh = $ngay_ban_hanh, v.ngay_hieu_luc = $ngay_hieu_luc,
            v.trang_thai = $trang_thai, v.visibility = $visibility,
            v.co_quan_ban_hanh = $co_quan_ban_hanh,
            v.source_filename = $source_filename
        WITH v
        UNWIND $dieu_list AS d
          MERGE (dieu:Dieu {dieu_id: d.dieu_id})
          SET dieu.so = d.so, dieu.so_dieu = d.so, dieu.tieu_de = d.tieu_de,
              dieu.van_ban_id = $vb_id, dieu.visibility = $visibility
          MERGE (v)-[:CO_DIEU]->(dieu)
          WITH v, dieu, d
          UNWIND d.khoan_list AS k
            MERGE (kh:Khoan {khoan_id: k.khoan_id})
            SET kh.so = k.so, kh.so_khoan = k.so, kh.noi_dung = k.noi_dung, kh.van_ban_id = $vb_id,
                kh.dieu_id = d.dieu_id, kh.visibility = $visibility
            MERGE (dieu)-[:CO_KHOAN]->(kh)
        """
        params = {
            "vb_id": doc.get("vb_id"),
            "so_hieu": doc.get("so_hieu"),
            "ten": doc.get("ten"),
            "loai": doc.get("loai"),
            "ngay_ban_hanh": doc.get("ngay_ban_hanh"),
            "ngay_hieu_luc": doc.get("ngay_hieu_luc"),
            "trang_thai": doc.get("trang_thai", "hieu_luc"),
            "visibility": doc.get("visibility", "public"),
            "co_quan_ban_hanh": doc.get("co_quan_ban_hanh"),
            "source_filename": doc.get("source_filename"),
            "dieu_list": dieu_list,
        }
        async with self.driver.session() as session:
            await session.run(query, **params)

        khoan_count = sum(len(d.get("khoan_list", [])) for d in dieu_list)
        return {"written": True, "vb_id": doc.get("vb_id"), "dieu_count": len(dieu_list), "khoan_count": khoan_count}

    # Category -> (Neo4j label, relationship type from Khoan to the entity).
    _ENTITY_MAP = {
        "chu_the": ("ChuThe", "AP_DUNG_CHO"),
        "nghia_vu": ("NghiaVu", "CO_NGHIA_VU"),
        "quyen_loi": ("QuyenLoi", "CO_QUYEN_LOI"),
        "hanh_vi_cam": ("HanhViCam", "CAM"),
        "thoi_han": ("ThoiHan", "CO_THOI_HAN"),
        "che_tai": ("CheTai", "CO_CHE_TAI"),
    }

    async def upsert_khoan_entities(self, khoan_id: str, entities: dict[str, Any]) -> int:
        """Persist NER-extracted legal entities for a Khoản and mark it ner_done.

        Idempotent: entity nodes are MERGEd on (khoan_id, mo_ta) so re-running NER for the same
        Khoản overwrites rather than duplicates. Returns the number of entity nodes written.
        """
        if not self.driver or not hasattr(self.driver, "session"):
            return 0
        written = 0
        async with self.driver.session() as session:
            for category, (label, rel) in self._ENTITY_MAP.items():
                items = entities.get(category) or []
                rows = [{"mo_ta": (it.get("mo_ta") if isinstance(it, dict) else str(it))} for it in items]
                rows = [r for r in rows if (r["mo_ta"] or "").strip()]
                if not rows:
                    continue
                # Label + rel are from a fixed internal map (never user input), safe to interpolate.
                query = (
                    "MATCH (k:Khoan {khoan_id: $kid}) "
                    "UNWIND $rows AS it "
                    f"MERGE (e:{label} {{khoan_id: $kid, mo_ta: it.mo_ta}}) "
                    f"MERGE (k)-[:{rel}]->(e)"
                )
                await session.run(query, kid=khoan_id, rows=rows)
                written += len(rows)
            await session.run(
                "MATCH (k:Khoan {khoan_id: $kid}) SET k.ner_done = true", kid=khoan_id
            )
        return written

    async def list_khoan_needing_ner(self, van_ban_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        """Return Khoản that have not been NER-processed yet (ner_done is null/false)."""
        if not self.driver or not hasattr(self.driver, "session"):
            return []
        where_vb = "AND k.van_ban_id = $vb" if van_ban_id else ""
        query = (
            f"MATCH (k:Khoan) WHERE coalesce(k.ner_done, false) = false {where_vb} "
            "AND k.noi_dung IS NOT NULL AND trim(k.noi_dung) <> '' "
            "RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung LIMIT $limit"
        )
        out: list[dict[str, Any]] = []
        async with self.driver.session() as session:
            res = await session.run(query, vb=van_ban_id, limit=limit)
            async for record in res:
                out.append({"khoan_id": record["khoan_id"], "noi_dung": record["noi_dung"]})
        return out

    async def count_khoan_needing_ner(self, van_ban_id: str | None = None) -> int:
        if not self.driver or not hasattr(self.driver, "session"):
            return 0
        where_vb = "AND k.van_ban_id = $vb" if van_ban_id else ""
        query = (
            f"MATCH (k:Khoan) WHERE coalesce(k.ner_done, false) = false {where_vb} "
            "AND k.noi_dung IS NOT NULL AND trim(k.noi_dung) <> '' RETURN count(k) AS c"
        )
        async with self.driver.session() as session:
            res = await session.run(query, vb=van_ban_id)
            record = await res.single()
        return int(record["c"]) if record else 0

    async def list_khoan_for_van_ban(self, van_ban_id: str) -> list[CandidateKhoan]:
        if not van_ban_id or not self.driver or not hasattr(self.driver, "session"):
            return []
        # Ưu tiên traversal cấu trúc; fallback theo thuộc tính van_ban_id trên Khoan.
        query = (
            "MATCH (v:VanBanPhapLuat) WHERE v.vb_id = $vb OR v.so_hieu = $vb "
            "MATCH (v)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan) "
            "RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung "
            "UNION "
            "MATCH (k:Khoan {van_ban_id: $vb}) "
            "RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung"
        )
        out: list[CandidateKhoan] = []
        seen: set[str] = set()
        async with self.driver.session() as session:
            res = await session.run(query, vb=van_ban_id)
            async for record in res:
                kid = record["khoan_id"]
                if kid and record["noi_dung"] and kid not in seen:
                    seen.add(str(kid))
                    out.append(self._to_candidate(record))
        return out
