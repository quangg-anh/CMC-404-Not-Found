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
        # qdrant-client >=1.10 replaced `.search()` with `.query_points()`; prefer the new API
        # and fall back to the legacy method for older client versions.
        if hasattr(self.client, "query_points"):
            response = await self.client.query_points(
                collection_name=collection,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            hits = getattr(response, "points", response)
        else:
            hits = await self.client.search(
                collection_name=collection, query_vector=vector, limit=limit, query_filter=query_filter
            )
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

    async def list_payload_records(
        self,
        collection: str,
        keys: list[str],
    ) -> list[dict[str, Any]]:
        """Scroll payload fields while preserving duplicates for parity checks."""
        out: list[dict[str, Any]] = []
        if not hasattr(self.client, "scroll"):
            return out
        offset: Any = None
        while True:
            result = await self.client.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=keys,
                with_vectors=False,
            )
            if isinstance(result, tuple):
                points, offset = result
            else:
                points, offset = result, None
            for point in points or []:
                payload = getattr(point, "payload", None) or {}
                if isinstance(payload, dict):
                    out.append({key: payload.get(key) for key in keys})
            if offset is None:
                break
        return out

    async def list_payload_field_values(self, collection: str, key: str) -> list[str]:
        """Scroll one payload field and preserve values, including duplicates."""
        records = await self.list_payload_records(collection, [key])
        return [str(record[key]) for record in records if record.get(key)]

    async def list_payload_values(self, collection: str, key: str = "khoan_id") -> set[str]:
        """Scroll all points and collect unique payload values for resume checks."""
        return set(await self.list_payload_field_values(collection, key))
    async def delete_by_payload(self, collection: str, key: str, value: str) -> None:
        if not key or not value:
            return
        try:
            from qdrant_client import models

            await self.client.delete(
                collection_name=collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[models.FieldCondition(key=key, match=models.MatchValue(value=value))]
                    )
                ),
            )
        except Exception:
            return

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
