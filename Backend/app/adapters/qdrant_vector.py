from __future__ import annotations

from typing import Any
from app.exceptions import ContractMissingError, ValidationError


class QdrantVectorClient:
    """Thin adapter for Qdrant. Caller injects AsyncQdrantClient to avoid hard dependency in unit tests."""

    def __init__(self, client: Any, expected_dimensions: dict[str, int] | None = None, expected_distance: str | None = None) -> None:
        self.client = client
        self.expected_dimensions = expected_dimensions or {}
        self.expected_distance = expected_distance

    async def get_collection(self, collection: str) -> dict[str, Any]:
        info = await self.client.get_collection(collection)
        if hasattr(info, "model_dump"):
            return info.model_dump()
        if isinstance(info, dict):
            return info
        return info.__dict__

    async def validate_collection(self, collection: str, vector_size: int | None = None) -> None:
        info = await self.get_collection(collection)
        params = info.get("config", {}).get("params", {}).get("vectors") or info.get("vectors") or {}
        if not isinstance(params, dict) and hasattr(params, "model_dump"):
            params = params.model_dump()
        if isinstance(params, dict) and "params" in params and isinstance(params["params"], dict):
            params = params["params"]
        size = params.get("size") if isinstance(params, dict) else None
        distance = params.get("distance") if isinstance(params, dict) else None
        expected_size = vector_size or self.expected_dimensions.get(collection)
        if expected_size is not None and size is not None and int(size) != int(expected_size):
            raise ValidationError("Qdrant vector dimension mismatch", details={"collection": collection, "expected": expected_size, "actual": size})
        if self.expected_distance and distance and str(distance).lower() != self.expected_distance.lower():
            raise ValidationError("Qdrant distance mismatch", details={"collection": collection, "expected": self.expected_distance, "actual": distance})

    async def search(self, collection: str, vector: list[float], *, limit: int, query_filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValidationError("limit must be positive")
        await self.validate_collection(collection, len(vector))
        hits = await self.client.search(collection_name=collection, query_vector=vector, limit=limit, query_filter=query_filter)
        result: list[dict[str, Any]] = []
        for hit in hits:
            result.append({"id": getattr(hit, "id", None), "score": float(getattr(hit, "score", 0.0)), "payload": getattr(hit, "payload", {}) or {}})
        return result

    async def upsert(self, collection: str, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        first_vector = points[0].get("vector")
        if not isinstance(first_vector, list):
            raise ValidationError("point vector is required")
        await self.validate_collection(collection, len(first_vector))
        await self.client.upsert(collection_name=collection, points=points)

    async def upsert_baidang(self, *, point_id: str, vector: list[float], bai_dang_id: str, chu_de: str | None, platform: str) -> None:
        if not point_id or not bai_dang_id or not platform:
            raise ContractMissingError("baidang point_id, bai_dang_id, and platform are required")
        if platform not in {"facebook", "youtube", "forum"}:
            raise ValidationError("unsupported social platform", details={"platform": platform})
        await self.upsert("baidang", [{"id": point_id, "vector": vector, "payload": {"bai_dang_id": bai_dang_id, "chu_de": chu_de, "platform": platform}}])

    async def upsert_chude(self, *, slug: str, ten: str, vector: list[float]) -> None:
        if not slug or not ten:
            raise ContractMissingError("chude slug and ten are required")
        await self.upsert("chude", [{"id": slug, "vector": vector, "payload": {"slug": slug, "ten": ten}}])
