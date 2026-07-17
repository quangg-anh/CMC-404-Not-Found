from __future__ import annotations

import asyncio
from typing import Any
import httpx
from pydantic import TypeAdapter
from app.config import BE2Config, get_config
from app.exceptions import ExternalServiceError, ValidationError

def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


class Embedder:
    def __init__(self, config: BE2Config | None = None, model: Any | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config or get_config()
        self._model = model
        self._http = http_client
        self._dimension: int | None = self.config.embedding_dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValidationError("texts must not be empty")
        normalized = [normalize_text(t) for t in texts]
        if any(not t for t in normalized):
            raise ValidationError("text item must not be empty")
        vectors: list[list[float]] = []
        for start in range(0, len(normalized), self.config.embedding_batch_size):
            batch = normalized[start : start + self.config.embedding_batch_size]
            batch_vectors = await asyncio.wait_for(self._embed_batch(batch), timeout=self.config.embedding_timeout_s)
            vectors.extend(batch_vectors)
        self._validate_vectors(vectors, len(normalized))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        if self.config.embedding_provider == "tei":
            return await self._embed_tei(batch)
        if self.config.embedding_provider == "openai":
            return await self._embed_openai(batch)
        return await self._embed_local(batch)

    async def _embed_openai(self, batch: list[str]) -> list[list[float]]:
        """Embed via an OpenAI-compatible ``/embeddings`` endpoint (Ollama /v1, vLLM, OpenAI, ...).

        This replaces the local torch/sentence-transformers path so no model runs in-process.
        """
        if self.config.embedding_base_url is None:
            raise ValidationError("BE2_EMBEDDING_BASE_URL is required for openai embedding provider")
        client = self._http or httpx.AsyncClient(timeout=self.config.embedding_timeout_s)
        close = self._http is None
        headers = {"Content-Type": "application/json"}
        if self.config.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.config.embedding_api_key}"
        url = f"{str(self.config.embedding_base_url).rstrip('/')}/embeddings"
        try:
            response = await client.post(
                url,
                headers=headers,
                json={"model": self.config.embedding_model, "input": batch},
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            # Preserve request order (OpenAI returns an `index` per item).
            items_sorted = sorted(items, key=lambda x: x.get("index", 0))
            raw = [item["embedding"] for item in items_sorted]
            if len(raw) != len(batch):
                raise ExternalServiceError(
                    "OpenAI-compatible embedding count mismatch",
                    details={"expected": len(batch), "actual": len(raw)},
                )
            return TypeAdapter(list[list[float]]).validate_python(raw)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise ExternalServiceError(
                "OpenAI-compatible embedding request failed",
                details={"provider": "openai", "url": url},
            ) from exc
        finally:
            if close:
                await client.aclose()

    async def _embed_tei(self, batch: list[str]) -> list[list[float]]:
        if self.config.tei_url is None:
            raise ValidationError("BE2_TEI_URL is required for TEI embedding provider")
        client = self._http or httpx.AsyncClient(timeout=self.config.embedding_timeout_s)
        close = self._http is None
        try:
            response = await client.post(str(self.config.tei_url), json={"inputs": batch})
            response.raise_for_status()
            data = response.json()
            raw = data.get("embeddings", data)
            return TypeAdapter(list[list[float]]).validate_python(raw)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise ExternalServiceError("TEI embedding request failed", details={"provider": "tei"}) from exc
        finally:
            if close:
                await client.aclose()

    async def _embed_local(self, batch: list[str]) -> list[list[float]]:
        # The local torch/sentence-transformers embedder has been removed. If an injected model was
        # provided (tests), use it; otherwise instruct the operator to use the OpenAI-compatible API.
        if self._model is not None:
            vectors = await asyncio.to_thread(self._model.encode, batch, normalize_embeddings=True)
            return TypeAdapter(list[list[float]]).validate_python(
                vectors.tolist() if hasattr(vectors, "tolist") else vectors
            )
        raise ExternalServiceError(
            "The local torch embedder was removed; set BE2_EMBEDDING_PROVIDER=openai "
            "(OpenAI-compatible /v1/embeddings, e.g. Ollama bge-m3).",
            details={"provider": "local"},
        )

    def _validate_vectors(self, vectors: list[list[float]], expected_count: int) -> None:
        if len(vectors) != expected_count:
            raise ValidationError("embedding vector count mismatch", details={"expected": expected_count, "actual": len(vectors)})
        dims = {len(v) for v in vectors}
        if len(dims) != 1:
            raise ValidationError("embedding vector dimension mismatch within batch", details={"dimensions": sorted(dims)})
        dim = dims.pop()
        if self._dimension is None:
            self._dimension = dim
        elif self._dimension != dim:
            raise ValidationError("embedding vector dimension mismatch", details={"expected": self._dimension, "actual": dim})

    async def health(self) -> dict[str, Any]:
        probe = await self.embed_texts(["health check"])
        return {"ok": True, "provider": self.config.embedding_provider, "dimension": len(probe[0])}


_default_embedder: Embedder | None = None


async def embed_texts(texts: list[str]) -> list[list[float]]:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return await _default_embedder.embed_texts(texts)
