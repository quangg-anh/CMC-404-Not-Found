"""Sync Qdrant ``khoan`` payloads' noi_dung from Neo4j (no re-embed).

Use after OCR text repair so RAG citations show cleaned text without waiting for a full reindex.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_ENV = Path(__file__).resolve().parents[1] / ".env"


def _load_env() -> None:
    if not _ENV.exists():
        return
    for raw in _ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


async def main_async(prefix: str | None) -> int:
    from neo4j import AsyncGraphDatabase
    from qdrant_client import AsyncQdrantClient, models

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    driver = AsyncGraphDatabase.driver(
        uri, auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "neo4j"))
    )
    qurl = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant = AsyncQdrantClient(url=qurl)

    updated = 0
    try:
        async with driver.session() as session:
            if prefix:
                res = await session.run(
                    "MATCH (k:Khoan) WHERE k.khoan_id STARTS WITH $p "
                    "RETURN k.khoan_id AS id, k.noi_dung AS nd",
                    p=prefix,
                )
            else:
                res = await session.run(
                    "MATCH (k:Khoan) RETURN k.khoan_id AS id, k.noi_dung AS nd"
                )
            rows = [dict(r) async for r in res]

        for row in rows:
            kid = row["id"]
            nd = row["nd"] or ""
            # Point id in this project is typically a hash or the khoan_id string —
            # update by filter on payload.khoan_id so either scheme works.
            await qdrant.set_payload(
                collection_name="khoan",
                payload={"noi_dung": nd},
                points=models.Filter(
                    must=[models.FieldCondition(key="khoan_id", match=models.MatchValue(value=kid))]
                ),
            )
            updated += 1
            if updated % 50 == 0:
                print(f"… {updated} payloads synced")
        print(f"Done. Synced noi_dung for {updated} Khoan into Qdrant.")
    finally:
        await driver.close()
        await qdrant.close()
    return 0


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default=None)
    args = ap.parse_args()
    return asyncio.run(main_async(args.prefix))


if __name__ == "__main__":
    raise SystemExit(main())
