"""Reindex Qdrant ``khoan`` vectors from Neo4j on Railway (public TCP proxies).

Does NOT load Backend/.env (avoids localhost Neo4j/Qdrant). Set Railway proxy +
embedding credentials in the shell before running.

Required env:
  NEO4J_PASSWORD
  BE2_OPENAI_API_KEY          (or BE2_EMBEDDING_API_KEY)
  BE2_OPENAI_BASE_URL         (or BE2_EMBEDDING_BASE_URL)  e.g. https://…/v1

Optional env (defaults match other Railway scripts):
  NEO4J_BOLT_HOST             default tokaido.proxy.rlwy.net
  NEO4J_BOLT_PORT             default 20113
  NEO4J_USER                  default neo4j
  QDRANT_URL                  default http://tokaido.proxy.rlwy.net:30541
  BE2_EMBEDDING_MODEL         default text-embedding-3-small
  BE2_EMBEDDING_DIMENSION     default 1536 (must match model: small=1536, large=3072)
  EMBEDDING_DIM               alias for dimension

Usage (from repo root):
  python Backend/scripts/reindex_railway.py --dry-run
  python Backend/scripts/reindex_railway.py --yes --batch-size 1

  # Đổi model large (3072) khi collection đang 1536:
  $env:BE2_EMBEDDING_MODEL = "lao/dg/text-embedding-3-large"
  $env:BE2_EMBEDDING_DIMENSION = "3072"
  python Backend/scripts/reindex_railway.py --yes --batch-size 1 --recreate-khoan
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_KHOAN_COLLECTION = "khoan"


def _require(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        raise SystemExit(f"Set {name} first (Railway public proxy / embedding).")
    return val


def _apply_railway_env() -> None:
    host = os.environ.get("NEO4J_BOLT_HOST", "tokaido.proxy.rlwy.net").strip()
    port = os.environ.get("NEO4J_BOLT_PORT", "20113").strip()
    os.environ["NEO4J_URI"] = f"bolt://{host}:{port}"
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ["NEO4J_PASSWORD"] = _require("NEO4J_PASSWORD")

    os.environ.setdefault("QDRANT_URL", "http://tokaido.proxy.rlwy.net:30541")

    dim = os.environ.get("EMBEDDING_DIM") or os.environ.get("BE2_EMBEDDING_DIMENSION") or "1536"
    os.environ["BE2_EMBEDDING_DIMENSION"] = dim
    os.environ["EMBEDDING_DIM"] = dim

    emb_base = (
        os.environ.get("BE2_EMBEDDING_BASE_URL") or os.environ.get("BE2_OPENAI_BASE_URL") or ""
    ).strip()
    emb_key = (
        os.environ.get("BE2_EMBEDDING_API_KEY") or os.environ.get("BE2_OPENAI_API_KEY") or ""
    ).strip()
    if not emb_base:
        raise SystemExit("Set BE2_EMBEDDING_BASE_URL or BE2_OPENAI_BASE_URL (…/v1).")
    if not emb_key:
        raise SystemExit("Set BE2_EMBEDDING_API_KEY or BE2_OPENAI_API_KEY.")
    os.environ.setdefault("BE2_OPENAI_BASE_URL", emb_base)
    os.environ.setdefault("BE2_OPENAI_API_KEY", emb_key)
    os.environ.setdefault("BE2_EMBEDDING_BASE_URL", emb_base)
    os.environ.setdefault("BE2_EMBEDDING_API_KEY", emb_key)
    os.environ.setdefault("BE2_EMBEDDING_PROVIDER", "openai")
    os.environ.setdefault("BE2_EMBEDDING_MODEL", "text-embedding-3-small")
    # Many OpenAI-compatible proxies only return 1 vector per request when input is an array.
    os.environ.setdefault("BE2_EMBEDDING_BATCH_SIZE", "1")


def _collection_dim(info: Any) -> int | None:
    try:
        cfg = getattr(info, "config", None)
        params = getattr(cfg, "params", None) if cfg else None
        vectors = getattr(params, "vectors", None) if params else None
        if vectors is None and isinstance(info, dict):
            vectors = (
                info.get("config", {}).get("params", {}).get("vectors")
                or info.get("vectors")
            )
        if vectors is None:
            return None
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, dict):
            if "size" in vectors:
                return int(vectors["size"])
            for v in vectors.values():
                size = getattr(v, "size", None) if not isinstance(v, dict) else v.get("size")
                if size is not None:
                    return int(size)
    except Exception:
        return None
    return None


async def _recreate_khoan(dim: int) -> None:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models as qmodels

    url = os.environ["QDRANT_URL"]
    client = AsyncQdrantClient(url=url, timeout=60.0)
    try:
        existing = {c.name for c in (await client.get_collections()).collections}
        old_count = None
        old_dim = None
        if _KHOAN_COLLECTION in existing:
            info = await client.get_collection(_KHOAN_COLLECTION)
            old_count = getattr(info, "points_count", None)
            old_dim = _collection_dim(info)
            await client.delete_collection(collection_name=_KHOAN_COLLECTION)
        await client.create_collection(
            collection_name=_KHOAN_COLLECTION,
            vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
        )
        print(
            f"  Recreated collection '{_KHOAN_COLLECTION}': "
            f"was points={old_count} dim={old_dim} → now empty dim={dim}"
        )
    finally:
        await client.close()


async def _ensure_dim_compatible(*, embedder: Any, recreate: bool) -> int:
    """Probe one embedding, compare to Qdrant collection; recreate if requested."""
    from qdrant_client import AsyncQdrantClient

    probe = await embedder.embed_texts(["kiểm tra chiều embedding pháp luật"])
    actual_dim = len(probe[0])
    configured = int(os.environ.get("BE2_EMBEDDING_DIMENSION") or actual_dim)
    if actual_dim != configured:
        print(f"  WARN: BE2_EMBEDDING_DIMENSION={configured} nhưng model trả dim={actual_dim} → dùng {actual_dim}")
        os.environ["BE2_EMBEDDING_DIMENSION"] = str(actual_dim)
        os.environ["EMBEDDING_DIM"] = str(actual_dim)
        embedder.config.embedding_dimension = actual_dim
        embedder._dimension = actual_dim

    url = os.environ["QDRANT_URL"]
    client = AsyncQdrantClient(url=url, timeout=30.0)
    try:
        existing = {c.name for c in (await client.get_collections()).collections}
        coll_dim: int | None = None
        if _KHOAN_COLLECTION in existing:
            info = await client.get_collection(_KHOAN_COLLECTION)
            coll_dim = _collection_dim(info)
            print(f"  Qdrant '{_KHOAN_COLLECTION}' dim={coll_dim} points={getattr(info, 'points_count', '?')}")
        else:
            print(f"  Qdrant '{_KHOAN_COLLECTION}' chưa tồn tại")
    finally:
        await client.close()

    if coll_dim is not None and coll_dim != actual_dim:
        msg = (
            f"Dimension lệch: embedding={actual_dim}, collection={coll_dim}. "
            f"Dùng --recreate-khoan (XÓA toàn bộ vector khoan) hoặc đổi model khớp dim {coll_dim}."
        )
        if not recreate:
            raise SystemExit(msg)
        print(f"  {msg}")
        await _recreate_khoan(actual_dim)
    elif coll_dim is None:
        print(f"  Tạo collection '{_KHOAN_COLLECTION}' dim={actual_dim}")
        await _recreate_khoan(actual_dim)
    elif recreate:
        print(f"  --recreate-khoan: xoá và tạo lại collection dim={actual_dim}")
        await _recreate_khoan(actual_dim)

    return actual_dim


async def _resolve_van_ban_id(driver, needle: str | None) -> str | None:
    if not needle:
        return None
    query = """
    MATCH (v:VanBanPhapLuat)
    WHERE v.vb_id = $id OR v.so_hieu = $id
    RETURN coalesce(v.vb_id, v.so_hieu) AS id
    LIMIT 1
    """
    async with driver.session() as session:
        res = await session.run(query, id=needle)
        record = await res.single()
        if not record or not record.get("id"):
            raise SystemExit(f"Không tìm thấy văn bản: {needle}")
        return str(record["id"])


async def _count_khoan(driver, van_ban_id: str | None) -> int:
    where = "WHERE v.vb_id = $vb_id" if van_ban_id else ""
    query = f"""
    MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan)
    {where}
    RETURN count(k) AS c
    """
    async with driver.session() as session:
        res = await session.run(query, vb_id=van_ban_id) if van_ban_id else await session.run(query)
        record = await res.single()
        return int((record or {}).get("c") or 0)


async def main_async(
    *,
    van_ban_id: str | None,
    batch_size: int,
    dry_run: bool,
    recreate_khoan: bool,
) -> int:
    from app.api.deps import get_embedder, get_neo4j_driver, get_qdrant_client
    from app.config import get_config
    from app.pipelines.legal.pipeline import reindex_khoan_from_neo4j

    get_config.cache_clear()

    print("\n=== REINDEX RAILWAY (Neo4j → Qdrant) ===")
    print(f"  Neo4j     {os.environ.get('NEO4J_URI')}")
    print(f"  Qdrant    {os.environ.get('QDRANT_URL')}")
    print(f"  Embed     {os.environ.get('BE2_EMBEDDING_BASE_URL')}")
    print(f"  Model     {os.environ.get('BE2_EMBEDDING_MODEL')} dim={os.environ.get('BE2_EMBEDDING_DIMENSION')}")
    print(f"  filter    {van_ban_id or '(all)'}")
    print(f"  batch     {batch_size}")
    print(f"  recreate  {recreate_khoan}")

    driver = await get_neo4j_driver()
    resolved = await _resolve_van_ban_id(driver, van_ban_id)
    if resolved and resolved != van_ban_id:
        print(f"  resolved  {van_ban_id} → vb_id={resolved}")

    total = await _count_khoan(driver, resolved)
    print(f"  Khoản     {total}")

    if dry_run:
        print("\nDry-run: không embed / không ghi Qdrant.")
        return 0

    if total == 0:
        print("Không có Khoản nào để reindex.")
        return 1

    # Fresh clients after possible collection recreate
    import app.api.deps as deps

    deps._qdrant_client = None
    deps._embedder = None
    get_config.cache_clear()

    embedder = await get_embedder(get_config())
    if not embedder:
        print("FAIL: embedder unavailable (check BE2_EMBEDDING_* / BE2_OPENAI_*).")
        return 1

    try:
        actual_dim = await _ensure_dim_compatible(embedder=embedder, recreate=recreate_khoan)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FAIL: không kiểm tra được embedding/Qdrant dim: {exc}")
        return 1

    print(f"  Using dim={actual_dim}")

    deps._qdrant_client = None
    qdrant = await get_qdrant_client()

    print("\nĐang reindex… (có thể rất lâu trên full corpus)")
    result = await reindex_khoan_from_neo4j(
        driver,
        qdrant,
        embedder,
        van_ban_id=resolved,
        batch_size=batch_size,
    )
    print(result)
    ok = result.get("status") == "success" and int(result.get("indexed") or 0) > 0
    if ok:
        print(
            "\nNhớ set trên Railway (API + Worker): "
            f"BE2_EMBEDDING_MODEL={os.environ.get('BE2_EMBEDDING_MODEL')} "
            f"BE2_EMBEDDING_DIMENSION={actual_dim}"
        )
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Reindex Railway Qdrant from Neo4j via public proxies.")
    ap.add_argument("--van-ban-id", default=None, help="Chỉ 1 văn bản (vb_id hoặc so_hieu)")
    ap.add_argument("--batch-size", type=int, default=1, help="Số Khoản / lần gọi embed (default 1)")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ đếm Khoản, không ghi Qdrant")
    ap.add_argument(
        "--recreate-khoan",
        action="store_true",
        help="XÓA collection khoan rồi tạo lại đúng dim embedding (bắt buộc khi đổi 1536↔3072)",
    )
    ap.add_argument("--yes", action="store_true", help="Bỏ qua xác nhận")
    args = ap.parse_args()

    if args.batch_size < 1 or args.batch_size > 64:
        raise SystemExit("--batch-size must be 1..64")

    _apply_railway_env()

    if not args.dry_run and not args.yes:
        scope = args.van_ban_id or "ALL"
        print(f"Sắp embed + upsert Qdrant từ Neo4j Railway (scope={scope}).")
        if args.recreate_khoan:
            print("CẢNH BÁO: --recreate-khoan sẽ XÓA hết vector trong collection khoan.")
        print("Tốn quota embedding API; chạy lâu nếu corpus lớn.")
        if input("Gõ 'reindex' để xác nhận: ").strip() != "reindex":
            print("Đã hủy.")
            return 1

    try:
        return asyncio.run(
            main_async(
                van_ban_id=args.van_ban_id,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                recreate_khoan=args.recreate_khoan,
            )
        )
    except KeyboardInterrupt:
        print("\nĐã dừng.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
