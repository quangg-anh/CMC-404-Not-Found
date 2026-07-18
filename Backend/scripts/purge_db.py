"""Purge the knowledge stores so you can reload clean data.

Clears data across Neo4j, Qdrant, PostgreSQL, MinIO (+ optional Redis ARQ keys).
NEVER touches Postgres `users` / `system_config` so you stay logged in.

SCOPES
  legal   (default)  VanBanPhapLuat/Dieu/Khoan/Diem/VanBanFile + NER entities,
                     `khoan` vectors, van_ban_files/lineage/legal jobs, MinIO legal bucket.
  social             BaiDang/YKien/AlertMeta/ChuDe, baidang/chude vectors,
                     alerts/suggestions + social jobs.
  content            BaiTomTat / DeXuatDinhChinh + briefs / suggestions / audit_log
                     (suggestions also cleared under social).
  all                Everything above (all graph labels + all content tables + all jobs).

USAGE (from repo root, backend interpreter):
    python Backend/scripts/purge_db.py
    python Backend/scripts/purge_db.py --scope all --yes
    python Backend/scripts/purge_db.py --scope legal --dry-run
    python Backend/scripts/purge_db.py --scope all --yes --redis

Connection settings are read from Backend/.env (real env vars win).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and key not in os.environ:
            # Strip optional surrounding quotes
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            os.environ[key] = val


# ---------------------------------------------------------------------------
# Scope maps — keep in sync with Data/schema/neo4j_constraints.cypher
# ---------------------------------------------------------------------------
_NEO4J_LABELS: dict[str, list[str]] = {
    "legal": [
        "VanBanPhapLuat",
        "Chuong",
        "Dieu",
        "Khoan",
        "Diem",
        "VanBanFile",
        "ChuThe",
        "NghiaVu",
        "QuyenLoi",
        "HanhViCam",
        "ThoiHan",
        "CheTai",
    ],
    "social": ["BaiDang", "YKien", "AlertMeta", "ChuDe"],
    "content": ["BaiTomTat", "DeXuatDinhChinh"],
}

_QDRANT_COLLECTIONS: dict[str, list[str]] = {
    "legal": ["khoan"],
    "social": ["baidang", "chude"],
    "content": [],
}

# Delete order matters for FK-ish tables when not using TRUNCATE CASCADE.
_PG_DELETE: dict[str, list[str]] = {
    "legal": [
        "DELETE FROM job_events WHERE job_id IN ("
        "  SELECT id FROM jobs WHERE type IN ("
        "    'legal_ingest','parse','extract','diff','run_ner','reindex','legal_reindex'"
        "  ) OR type ILIKE 'legal%'"
        ")",
        "DELETE FROM jobs WHERE type IN ("
        "  'legal_ingest','parse','extract','diff','run_ner','reindex','legal_reindex'"
        ") OR type ILIKE 'legal%'",
        "TRUNCATE van_ban_files, lineage RESTART IDENTITY CASCADE",
    ],
    "social": [
        "DELETE FROM job_events WHERE job_id IN ("
        "  SELECT id FROM jobs WHERE type IN ("
        "    'social_ingest','social_crawl','social_monitor','daily_social_monitor'"
        "  ) OR type ILIKE 'social%'"
        ")",
        "DELETE FROM jobs WHERE type IN ("
        "  'social_ingest','social_crawl','social_monitor','daily_social_monitor'"
        ") OR type ILIKE 'social%'",
        "TRUNCATE suggestions, alerts RESTART IDENTITY CASCADE",
    ],
    "content": [
        "DELETE FROM job_events WHERE job_id IN ("
        "  SELECT id FROM jobs WHERE type IN ("
        "    'brief_generate','suggest_generate','content_brief','content_suggest'"
        "  ) OR type ILIKE 'brief%' OR type ILIKE 'suggest%' OR type ILIKE 'content%'"
        ")",
        "DELETE FROM jobs WHERE type IN ("
        "  'brief_generate','suggest_generate','content_brief','content_suggest'"
        ") OR type ILIKE 'brief%' OR type ILIKE 'suggest%' OR type ILIKE 'content%'",
        "TRUNCATE briefs, suggestions, audit_log RESTART IDENTITY CASCADE",
    ],
    "all": [
        # Keep users + system_config only.
        "TRUNCATE van_ban_files, lineage, job_events, jobs, briefs, suggestions, alerts, audit_log "
        "RESTART IDENTITY CASCADE",
    ],
}


def _labels_for(scope: str) -> list[str]:
    if scope == "all":
        seen: list[str] = []
        for key in ("legal", "social", "content"):
            for label in _NEO4J_LABELS[key]:
                if label not in seen:
                    seen.append(label)
        return seen
    return list(_NEO4J_LABELS.get(scope, []))


def _collections_for(scope: str) -> list[str]:
    if scope == "all":
        return _QDRANT_COLLECTIONS["legal"] + _QDRANT_COLLECTIONS["social"]
    return list(_QDRANT_COLLECTIONS.get(scope, []))


def _pg_statements_for(scope: str) -> list[str]:
    return list(_PG_DELETE.get(scope, []))


def _embedding_dim() -> int:
    for key in ("BE2_EMBEDDING_DIMENSION", "EMBEDDING_DIM", "EMBEDDING_DIMENSION"):
        raw = os.getenv(key)
        if raw and raw.isdigit():
            return int(raw)
    return 1536


# --------------------------------------------------------------------------------------
# Neo4j
# --------------------------------------------------------------------------------------
async def purge_neo4j(scope: str, dry_run: bool) -> None:
    try:
        from neo4j import AsyncGraphDatabase
    except Exception:
        print("  [neo4j] SKIP - thiếu 'neo4j' package")
        return

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "neo4j")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))

    try:
        async with driver.session() as session:
            if scope == "all":
                cnt_res = await session.run("MATCH (n) RETURN count(n) AS c")
                rec = await cnt_res.single()
                total = int(rec["c"]) if rec else 0
                if dry_run:
                    print(f"  [neo4j] ALL nodes: {total} -> would DETACH DELETE")
                else:
                    deleted = 0
                    while True:
                        res = await session.run(
                            "MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c"
                        )
                        r = await res.single()
                        n = int(r["c"]) if r else 0
                        deleted += n
                        if n == 0:
                            break
                    print(f"  [neo4j] ALL nodes: deleted {deleted}")
            else:
                labels = _labels_for(scope)
                for label in labels:
                    cnt_res = await session.run(f"MATCH (n:`{label}`) RETURN count(n) AS c")
                    rec = await cnt_res.single()
                    total = int(rec["c"]) if rec else 0
                    if dry_run:
                        print(f"  [neo4j] {label}: {total} node(s) -> would delete")
                        continue
                    deleted = 0
                    while True:
                        res = await session.run(
                            f"MATCH (n:`{label}`) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c"
                        )
                        r = await res.single()
                        n = int(r["c"]) if r else 0
                        deleted += n
                        if n == 0:
                            break
                    print(f"  [neo4j] {label}: deleted {deleted} node(s)")

            # Report leftovers.
            leftover = await session.run(
                """
                CALL db.labels() YIELD label
                MATCH (n) WHERE label IN labels(n)
                RETURN label AS label, count(n) AS c
                ORDER BY label
                """
            )
            rows = [r async for r in leftover]
            if rows:
                print("  [neo4j] remaining labels:")
                for r in rows:
                    print(f"           - {r['label']}: {r['c']}")
            else:
                print("  [neo4j] remaining labels: (none)")
    finally:
        await driver.close()


# --------------------------------------------------------------------------------------
# Qdrant — recreate collections (FilterSelector empty often leaves points behind)
# --------------------------------------------------------------------------------------
def _vector_size_from_info(info: object) -> int | None:
    try:
        cfg = getattr(info, "config", None)
        params = getattr(cfg, "params", None) if cfg else None
        vectors = getattr(params, "vectors", None) if params else None
        if vectors is None:
            return None
        # Named vectors dict or single VectorParams
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, dict):
            for v in vectors.values():
                size = getattr(v, "size", None)
                if size is not None:
                    return int(size)
    except Exception:
        return None
    return None


async def purge_qdrant(scope: str, dry_run: bool) -> None:
    collections = _collections_for(scope)
    if not collections:
        print("  [qdrant] (no collections for this scope)")
        return
    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.http import models as qmodels
    except Exception:
        print("  [qdrant] SKIP - thiếu 'qdrant-client' package")
        return

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = AsyncQdrantClient(url=url)
    fallback_dim = _embedding_dim()

    try:
        existing = {c.name for c in (await client.get_collections()).collections}
        for col in collections:
            if col not in existing:
                print(f"  [qdrant] {col}: không tồn tại - tạo mới (dim={fallback_dim})")
                if dry_run:
                    continue
                await client.create_collection(
                    collection_name=col,
                    vectors_config=qmodels.VectorParams(
                        size=fallback_dim,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                print(f"  [qdrant] {col}: created empty")
                continue

            info = await client.get_collection(col)
            count = getattr(info, "points_count", None)
            dim = _vector_size_from_info(info) or fallback_dim
            if dry_run:
                print(f"  [qdrant] {col}: {count} point(s), dim={dim} -> would recreate empty")
                continue

            # Recreate = guaranteed empty (delete-all filter is unreliable).
            await client.delete_collection(collection_name=col)
            await client.create_collection(
                collection_name=col,
                vectors_config=qmodels.VectorParams(
                    size=dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            print(f"  [qdrant] {col}: recreated empty (was {count} point(s), dim={dim})")
    finally:
        await client.close()


# --------------------------------------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------------------------------------
async def purge_postgres(scope: str, dry_run: bool) -> None:
    statements = _pg_statements_for(scope)
    if not statements:
        print("  [postgres] (no statements for this scope)")
        return
    try:
        import asyncpg
    except Exception:
        print("  [postgres] SKIP - thiếu 'asyncpg' package")
        return

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("  [postgres] SKIP - thiếu DATABASE_URL")
        return
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        for stmt in statements:
            compact = " ".join(stmt.split())
            if dry_run:
                print(f"  [postgres] would run: {compact[:100]}{'…' if len(compact) > 100 else ''}")
                continue
            try:
                status = await conn.execute(stmt)
                print(f"  [postgres] {status}  :: {compact[:72]}{'…' if len(compact) > 72 else ''}")
            except Exception as exc:
                print(f"  [postgres] FAIL {compact[:60]}… -> {exc}")

        if not dry_run:
            # Sanity: count rows left in purgeable tables.
            tables = [
                "jobs",
                "job_events",
                "van_ban_files",
                "lineage",
                "alerts",
                "suggestions",
                "briefs",
                "audit_log",
            ]
            parts = []
            for t in tables:
                try:
                    n = await conn.fetchval(f"SELECT count(*) FROM {t}")
                    if n:
                        parts.append(f"{t}={n}")
                except Exception:
                    pass
            if parts:
                print(f"  [postgres] remaining rows: {', '.join(parts)}")
            else:
                print("  [postgres] remaining purgeable rows: 0")
            users = await conn.fetchval("SELECT count(*) FROM users")
            print(f"  [postgres] users kept: {users}")
    finally:
        await conn.close()


# --------------------------------------------------------------------------------------
# MinIO
# --------------------------------------------------------------------------------------
async def purge_minio(scope: str, dry_run: bool) -> None:
    if scope not in ("legal", "all"):
        print("  [minio] (skip — only legal/all)")
        return
    try:
        from minio import Minio
        from minio.deleteobjects import DeleteObject
    except Exception:
        print("  [minio] SKIP - thiếu 'minio' package")
        return

    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    parsed = urlparse(endpoint)
    secure = parsed.scheme == "https"
    host = parsed.netloc or parsed.path
    buckets = [
        os.getenv("MINIO_BUCKET_LEGAL", "legal-raw"),
    ]
    extra = os.getenv("MINIO_BUCKET_EXTRA", "").strip()
    if extra:
        buckets.extend(b.strip() for b in extra.split(",") if b.strip())

    access = os.getenv("MINIO_ROOT_USER") or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret = os.getenv("MINIO_ROOT_PASSWORD") or os.getenv("MINIO_SECRET_KEY", "minioadmin")
    client = Minio(host, access_key=access, secret_key=secret, secure=secure)

    def _purge_bucket(bucket: str) -> str:
        if not client.bucket_exists(bucket):
            return f"bucket '{bucket}' không tồn tại - bỏ qua"
        objects = list(client.list_objects(bucket, recursive=True))
        if dry_run:
            return f"bucket '{bucket}': {len(objects)} object(s) -> would delete"
        if not objects:
            return f"bucket '{bucket}': đã trống"

        total_deleted = 0
        for _ in range(5):
            objects = list(client.list_objects(bucket, recursive=True))
            if not objects:
                break
            errors = list(
                client.remove_objects(
                    bucket,
                    (DeleteObject(o.object_name) for o in objects if o.object_name),
                )
            )
            for e in errors:
                print(f"    [minio] lỗi xóa {getattr(e, 'object_name', e)}: {e}")
            total_deleted += max(0, len(objects) - len(errors))
        leftover = list(client.list_objects(bucket, recursive=True))
        if leftover:
            return f"bucket '{bucket}': deleted ~{total_deleted}, STILL HAS {len(leftover)} object(s)"
        return f"bucket '{bucket}': deleted {total_deleted} object(s), now empty"

    for bucket in buckets:
        msg = await asyncio.to_thread(_purge_bucket, bucket)
        print(f"  [minio] {msg}")


# --------------------------------------------------------------------------------------
# Redis (optional ARQ / queue leftover keys)
# --------------------------------------------------------------------------------------
async def purge_redis(dry_run: bool) -> None:
    try:
        import redis.asyncio as redis
    except Exception:
        print("  [redis] SKIP - thiếu 'redis' package")
        return

    url = os.getenv("BE2_REDIS_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(url)
    try:
        # ARQ / common job key prefixes used by this project.
        patterns = ["arq:*", "job:*", "legal:*", "social:*", "be2:*"]
        keys: list[bytes] = []
        for pat in patterns:
            cursor = 0
            while True:
                cursor, batch = await client.scan(cursor=cursor, match=pat, count=500)
                keys.extend(batch)
                if cursor == 0:
                    break
        # Dedup
        uniq = list(dict.fromkeys(keys))
        if dry_run:
            print(f"  [redis] {len(uniq)} key(s) matching {patterns} -> would delete")
            return
        if not uniq:
            print("  [redis] no matching keys")
            return
        deleted = await client.delete(*uniq)
        print(f"  [redis] deleted {deleted} key(s)")
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close:
            result = close()
            if asyncio.iscoroutine(result):
                await result


async def main_async(scope: str, dry_run: bool, do_redis: bool) -> int:
    print(f"\n=== PURGE scope='{scope}'{' (DRY RUN)' if dry_run else ''} ===")
    print("[1/5] Neo4j")
    await purge_neo4j(scope, dry_run)
    print("[2/5] Qdrant")
    await purge_qdrant(scope, dry_run)
    print("[3/5] Postgres")
    await purge_postgres(scope, dry_run)
    print("[4/5] MinIO")
    await purge_minio(scope, dry_run)
    print("[5/5] Redis")
    if do_redis or scope == "all":
        await purge_redis(dry_run)
    else:
        print("  [redis] skipped (pass --redis or --scope all)")
    print("\nHoàn tất." + ("" if dry_run else " users/system_config được giữ nguyên."))
    return 0


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser(description="Purge knowledge stores (Neo4j/Qdrant/Postgres/MinIO/Redis).")
    ap.add_argument("--scope", choices=["legal", "social", "content", "all"], default="legal")
    ap.add_argument("--yes", action="store_true", help="Bỏ qua xác nhận")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê, không xóa")
    ap.add_argument("--redis", action="store_true", help="Xóa thêm key ARQ/Redis (mặc định bật với --scope all)")
    args = ap.parse_args()

    if not args.dry_run and not args.yes:
        print(f"Sắp XÓA dữ liệu scope='{args.scope}' khỏi Neo4j/Qdrant/Postgres/MinIO.")
        print("users & system_config sẽ được giữ. Hành động KHÔNG THỂ hoàn tác.")
        if input(f"Gõ '{args.scope}' để xác nhận: ").strip() != args.scope:
            print("Đã hủy.")
            return 1

    try:
        return asyncio.run(main_async(args.scope, args.dry_run, args.redis))
    except KeyboardInterrupt:
        print("\nĐã dừng.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
