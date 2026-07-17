from __future__ import annotations

from typing import Any


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
                query = f"""
                MATCH path = (seed)-[r*1..{bounded_depth}]-(neighbor)
                WHERE seed.vb_id = $seed_id OR seed.khoan_id = $seed_id OR seed.slug = $seed_id OR id(seed) = $seed_id
                RETURN nodes(path) AS ns, relationships(path) AS rels
                LIMIT {bounded_limit}
                """
                async with self.driver.session() as session:
                    res = await session.run(query, seed_id=seed_id)
                    async for record in res:
                        for node in record["ns"]:
                            if node is None:
                                continue
                            nid = str(node.get("vb_id") or node.get("khoan_id") or node.get("slug") or node.get("id") or id(node))
                            labels = list(node.labels) if hasattr(node, "labels") else ["Node"]
                            node_type = labels[0] if labels else "Node"
                            label_str = str(node.get("so_hieu") or node.get("tieu_de") or node.get("noi_dung") or node.get("ten") or nid)[:60]
                            nodes_map[nid] = {"id": nid, "type": node_type, "label": label_str, "properties": dict(node)}

                        for rel in record["rels"]:
                            if rel is None:
                                continue
                            start_node = rel.start_node
                            end_node = rel.end_node
                            sid = str(start_node.get("vb_id") or start_node.get("khoan_id") or start_node.get("slug") or id(start_node))
                            eid = str(end_node.get("vb_id") or end_node.get("khoan_id") or end_node.get("slug") or id(end_node))
                            rel_type = type(rel).__name__ if hasattr(rel, "__class__") else "REL"
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
