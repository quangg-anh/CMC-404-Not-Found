from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import TypeAdapter

from app.config import BE2Config, get_config
from app.exceptions import ExternalServiceError, ValidationError


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _extract_embedding_vectors(data: Any) -> list[list[float]]:
    """Parse OpenAI-compatible embedding payloads, including common gateway variants."""
    if not isinstance(data, dict):
        return []

    items = data.get("data")
    if isinstance(items, dict):
        items = [items]
    if isinstance(items, list) and items:
        keyed = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            emb = item.get("embedding")
            if emb is None:
                emb = item.get("embeddings") or item.get("vector")
            if isinstance(emb, list) and emb and isinstance(emb[0], (int, float)):
                keyed.append((item.get("index", i), [float(x) for x in emb]))
        if keyed:
            keyed.sort(key=lambda x: x[0])
            return [v for _, v in keyed]

    # Top-level single vector variants
    for key in ("embedding", "embeddings", "vector"):
        emb = data.get(key)
        if isinstance(emb, list) and emb and isinstance(emb[0], (int, float)):
            return [[float(x) for x in emb]]
        if isinstance(emb, list) and emb and isinstance(emb[0], list):
            return [[float(x) for x in row] for row in emb if isinstance(row, list)]

    return []


class Embedder:
    """OpenAI-compatible embeddings only (``POST {base}/embeddings``).

    Works against any provider that speaks the OpenAI embeddings API: Ollama ``/v1``, vLLM,
    LM Studio, OpenAI, 9router, etc. No in-process torch / sentence-transformers model.

    Some proxies only return one vector when ``input`` is an array — ``_embed_openai`` then
    retries one text at a time.
    """

    # Soft char cap: keeps requests under typical 8k-token embedding limits (VN text denser).
    _MAX_CHARS = 6000

    def __init__(
        self,
        config: BE2Config | None = None,
        model: Any | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or get_config()
        # ``model`` is ignored (kept for call-site compatibility with older tests).
        self._model = model
        self._http = http_client
        self._dimension: int | None = self.config.embedding_dimension
        provider = (self.config.embedding_provider or "openai").lower()
        if provider != "openai":
            raise ValidationError(
                "Only OpenAI-compatible embeddings are supported. "
                "Set BE2_EMBEDDING_PROVIDER=openai and BE2_EMBEDDING_BASE_URL to a /v1 endpoint.",
                details={"provider": provider},
            )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValidationError("texts must not be empty")
        normalized = [self._prep(t) for t in texts]
        if any(not t for t in normalized):
            raise ValidationError("text item must not be empty")
        vectors: list[list[float]] = []
        batch_size = max(1, int(self.config.embedding_batch_size or 1))
        for start in range(0, len(normalized), batch_size):
            batch = normalized[start : start + batch_size]
            # Timeout is per HTTP call inside _embed_openai_once (fallback may do N calls).
            vectors.extend(await self._embed_openai(batch))
        self._validate_vectors(vectors, len(normalized))
        return vectors

    @classmethod
    def _prep(cls, text: str) -> str:
        t = normalize_text(text)
        if len(t) > cls._MAX_CHARS:
            return t[: cls._MAX_CHARS]
        return t

    async def _embed_openai(self, batch: list[str]) -> list[list[float]]:
        if self.config.embedding_base_url is None:
            raise ValidationError("BE2_EMBEDDING_BASE_URL is required for openai embedding provider")
        try:
            return await self._embed_openai_once(batch)
        except ExternalServiceError as exc:
            # Proxies (e.g. some OpenAI-compatible gateways) often return 1 vector for an
            # array input — fall back to sequential single-text embeds.
            if len(batch) > 1 and (
                "count mismatch" in str(exc)
                or (exc.details.get("expected") is not None and exc.details.get("actual") != exc.details.get("expected"))
            ):
                out: list[list[float]] = []
                for text in batch:
                    out.extend(await self._embed_openai_once([text]))
                return out
            raise

    async def _embed_openai_once(self, batch: list[str]) -> list[list[float]]:
        client = self._http or httpx.AsyncClient(timeout=self.config.embedding_timeout_s)
        close = self._http is None
        headers = {"Content-Type": "application/json"}
        if self.config.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.config.embedding_api_key}"
        url = f"{str(self.config.embedding_base_url).rstrip('/')}/embeddings"
        # OpenAI accepts string | string[]; some proxies mishandle arrays — send scalar when n=1.
        payload_input: str | list[str] = batch[0] if len(batch) == 1 else batch
        try:
            response = await asyncio.wait_for(
                client.post(
                    url,
                    headers=headers,
                    json={"model": self.config.embedding_model, "input": payload_input},
                ),
                timeout=self.config.embedding_timeout_s,
            )
            if response.status_code >= 400:
                detail = (response.text or "")[:400]
                raise ExternalServiceError(
                    "OpenAI-compatible embedding request failed",
                    details={
                        "provider": "openai",
                        "url": url,
                        "model": self.config.embedding_model,
                        "status_code": response.status_code,
                        "body": detail,
                        "hint": (
                            "BE2_EMBEDDING_MODEL must be an embedding model id "
                            "(e.g. text-embedding-3-small), not a chat model."
                        ),
                    },
                )
            response.raise_for_status()
            data = response.json()
            # Some gateways (9router → OpenRouter) return HTTP 200 with {"error": ...}.
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                if isinstance(err, dict):
                    msg = str(err.get("message") or err)
                    code = err.get("code")
                else:
                    msg = str(err)
                    code = None
                raise ExternalServiceError(
                    f"OpenAI-compatible embedding error: {msg}",
                    details={
                        "provider": "openai",
                        "url": url,
                        "model": self.config.embedding_model,
                        "status_code": response.status_code,
                        "error_code": code,
                        "body": (response.text or "")[:400],
                    },
                )
            raw = _extract_embedding_vectors(data)
            if len(raw) != len(batch):
                raise ExternalServiceError(
                    "OpenAI-compatible embedding count mismatch",
                    details={
                        "expected": len(batch),
                        "actual": len(raw),
                        "body_keys": list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                        "body": (response.text or "")[:300],
                    },
                )
            return TypeAdapter(list[list[float]]).validate_python(raw)
        except ExternalServiceError:
            raise
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise ExternalServiceError(
                "OpenAI-compatible embedding request failed",
                details={"provider": "openai", "url": url, "model": self.config.embedding_model},
            ) from exc
        finally:
            if close:
                await client.aclose()

    def _validate_vectors(self, vectors: list[list[float]], expected_count: int) -> None:
        if len(vectors) != expected_count:
            raise ValidationError(
                "embedding vector count mismatch",
                details={"expected": expected_count, "actual": len(vectors)},
            )
        dims = {len(v) for v in vectors}
        if len(dims) != 1:
            raise ValidationError(
                "embedding vector dimension mismatch within batch",
                details={"dimensions": sorted(dims)},
            )
        dim = dims.pop()
        if self._dimension is None:
            self._dimension = dim
        elif self._dimension != dim:
            raise ValidationError(
                "embedding vector dimension mismatch",
                details={"expected": self._dimension, "actual": dim},
            )

    async def health(self) -> dict[str, Any]:
        probe = await self.embed_texts(["health check"])
        return {"ok": True, "provider": "openai", "dimension": len(probe[0])}


_default_embedder: Embedder | None = None


async def embed_texts(texts: list[str]) -> list[list[float]]:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return await _default_embedder.embed_texts(texts)
