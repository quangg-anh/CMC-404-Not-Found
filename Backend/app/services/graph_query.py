from __future__ import annotations

from typing import Any

def _node_key(node: Any) -> str:
    return str(
        node.get("vb_id")
        or node.get("khoan_id")
        or node.get("dieu_id")
        or node.get("bai_dang_id")
        or node.get("slug")
        or node.get("id")
        or id(node)
    )

def _node_label(node: Any) -> str:
    return str(
        node.get("so_hieu")
        or node.get("tieu_de")
        or node.get("noi_dung")
        or node.get("ten")
        or node.get("text")
        or _node_key(node)
    )[:90]


class GraphQueryService:
    """Service querying Neo4j neighborhood graph structure (`depth <= 2`) directly without mock data."""

    def __init__(self, driver: Any | None = None) -> None:
        self.driver = driver

    async def get_neighborhood(self, seed_id: str, depth: int = 1, limit: int = 200) -> dict[str, Any]:
        """Fetch real graph neighborhood (`depth <= 2`). Returns only actual nodes and relationships."""
        bounded_depth = max(1, min(depth, 2))
        bounded_limit = max(1, min(limit, 300))
        nodes_map: dict[str, dict[str, Any]] = {}
        edges_set: set[tuple[str, str, str]] = set()

        if self.driver and hasattr(self.driver, "session"):
            try:
                # Match a seed by any natural key: internal id, khoản/điều id, slug, OR the human
                # document number (so_hieu). Also match by prefix so typing just the số hiệu
                # ("01/2016/NQ-HDND") seeds the whole document tree (its Điều/Khoản), not only the
                # exact "01/2016/NQ-HDND::D1.K2".
                query = f"""
                MATCH path = (seed)-[r*1..{bounded_depth}]-(neighbor)
                WHERE seed.vb_id = $seed_id OR seed.khoan_id = $seed_id OR seed.dieu_id = $seed_id
                         OR seed.bai_dang_id = $seed_id OR seed.id = $seed_id
                         OR seed.so_hieu = $seed_id OR seed.so_hieu_norm = $seed_id OR seed.slug = $seed_id
                   OR seed.khoan_id STARTS WITH ($seed_id + '::')
                   OR seed.dieu_id STARTS WITH ($seed_id + '::')
                RETURN nodes(path) AS ns, relationships(path) AS rels
                LIMIT {bounded_limit}
                """
                async with self.driver.session() as session:
                    res = await session.run(query, seed_id=seed_id)
                    async for record in res:
                        for node in record["ns"]:
                            if node is None:
                                continue
                            nid = _node_key(node)
                            labels = list(node.labels) if hasattr(node, "labels") else ["Node"]
                            node_type = labels[0] if labels else "Node"
                            label_str = _node_label(node)
                            nodes_map[nid] = {"id": nid, "type": node_type, "label": label_str, "properties": dict(node)}

                        for rel in record["rels"]:
                            if rel is None:
                                continue
                            start_node = rel.start_node
                            end_node = rel.end_node
                            sid = _node_key(start_node)
                            eid = _node_key(end_node)
                            rel_type = getattr(rel, "type", None) or type(rel).__name__
                            edges_set.add((sid, eid, rel_type))
            except Exception:
                pass

        edges_list = [{"source": s, "target": t, "type": r} for s, t, r in edges_set]
        return {
            "seed_id": seed_id,
            "depth": bounded_depth,
            "nodes": list(nodes_map.values()),
            "edges": edges_list,
        }

    async def seed_suggestions(self, limit: int = 20) -> dict[str, Any]:
        """Return useful starting nodes so the graph page is usable without memorized IDs."""
        bounded_limit = max(1, min(limit, 50))
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = """
                MATCH (n)
                WHERE n.vb_id IS NOT NULL OR n.khoan_id IS NOT NULL OR n.dieu_id IS NOT NULL OR n.bai_dang_id IS NOT NULL
                WITH n, labels(n) AS labels, size([(n)--() | 1]) AS degree
                RETURN coalesce(n.vb_id, n.khoan_id, n.dieu_id, n.bai_dang_id, n.slug, n.id) AS id,
                       labels[0] AS type,
                       coalesce(n.so_hieu, n.tieu_de, n.noi_dung, n.ten, n.text, n.khoan_id, n.dieu_id, n.vb_id) AS label,
                       degree
                ORDER BY degree DESC, type ASC
                LIMIT $limit
                """
                async with self.driver.session() as session:
                    res = await session.run(query, limit=bounded_limit)
                    async for r in res:
                        items.append(
                            {
                                "id": str(r.get("id")),
                                "type": r.get("type") or "Node",
                                "label": str(r.get("label") or r.get("id"))[:120],
                                "degree": int(r.get("degree") or 0),
                            }
                        )
            except Exception:
                pass
        return {"items": items, "total": len(items)}

    async def clarity_index(self, min_volume: int = 5, limit: int = 50) -> dict[str, Any]:
        """Idea 02 — Legal Clarity Index.

        Aggregates the DOI_CHIEU edges (citizen opinions cross-checked against a Khoản) to find which
        provisions are most often misunderstood. High ``clarity_risk`` (share of mâu_thuẫn/khong_ro)
        combined with high volume signals a clause that may be written or communicated unclearly.
        This is a communication signal, NOT a legal judgement that the law is wrong.
        """
        bounded_min = max(1, min(min_volume, 1000))
        bounded_limit = max(1, min(limit, 200))
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = """
                MATCH (y:YKien)-[d:DOI_CHIEU]->(k:Khoan)
                WITH k,
                     count(CASE WHEN d.label = 'mau_thuan' THEN 1 END) AS mau_thuan,
                     count(CASE WHEN d.label = 'khong_ro'  THEN 1 END) AS khong_ro,
                     count(*) AS tong
                WHERE tong >= $min_volume
                RETURN k.khoan_id AS khoan_id, k.noi_dung AS noi_dung,
                       mau_thuan AS mau_thuan, khong_ro AS khong_ro, tong AS volume,
                       toFloat(mau_thuan + khong_ro) / tong AS clarity_risk
                ORDER BY clarity_risk * log(volume + 1) DESC
                LIMIT $limit
                """
                async with self.driver.session() as session:
                    res = await session.run(query, min_volume=bounded_min, limit=bounded_limit)
                    async for r in res:
                        items.append(
                            {
                                "khoan_id": r.get("khoan_id"),
                                "noi_dung": r.get("noi_dung"),
                                "mau_thuan": int(r.get("mau_thuan") or 0),
                                "khong_ro": int(r.get("khong_ro") or 0),
                                "volume": int(r.get("volume") or 0),
                                "clarity_risk": round(float(r.get("clarity_risk") or 0.0), 3),
                            }
                        )
            except Exception:
                pass
        return {"min_volume": bounded_min, "items": items, "total": len(items)}
