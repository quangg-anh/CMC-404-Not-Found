"""Backfill: re-clean Vietnamese OCR typos already stored in Neo4j Khoản/Điều text.

Uses the same ``clean_text`` / OCR repair as ingest so old bad OCR (e.g. "công bồ MƠng",
"đâu giá") becomes readable without re-uploading PDFs.

USAGE:
    python Backend/scripts/repair_ocr_text.py
    python Backend/scripts/repair_ocr_text.py --dry-run
    python Backend/scripts/repair_ocr_text.py --prefix 11/2022/TT-BCT
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


async def main_async(prefix: str | None, dry_run: bool) -> int:
    from neo4j import AsyncGraphDatabase

    # Import after env load so config/embedder side-effects stay out of the way.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.pipelines.legal.extract_text import clean_text

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "neo4j")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))

    khoan_updated = 0
    dieu_updated = 0
    try:
        async with driver.session() as session:
            # --- Khoản ---
            if prefix:
                q = (
                    "MATCH (k:Khoan) WHERE k.khoan_id STARTS WITH $prefix "
                    "RETURN k.khoan_id AS id, k.noi_dung AS text"
                )
                res = await session.run(q, prefix=prefix)
            else:
                res = await session.run("MATCH (k:Khoan) RETURN k.khoan_id AS id, k.noi_dung AS text")
            rows = [dict(r) async for r in res]
            for row in rows:
                kid = row["id"]
                original = row["text"] or ""
                cleaned = clean_text(original)
                if cleaned == original:
                    continue
                if dry_run:
                    print(f"[dry] Khoan {kid}")
                    print(f"  OLD: {original[:120]}")
                    print(f"  NEW: {cleaned[:120]}")
                    khoan_updated += 1
                    continue
                await session.run(
                    "MATCH (k:Khoan {khoan_id: $id}) SET k.noi_dung = $txt",
                    id=kid,
                    txt=cleaned,
                )
                khoan_updated += 1
                print(f"Khoan fixed: {kid}")

            # --- Điều titles ---
            if prefix:
                q2 = (
                    "MATCH (d:Dieu) WHERE d.dieu_id STARTS WITH $prefix "
                    "RETURN d.dieu_id AS id, d.tieu_de AS text, d.so AS so"
                )
                res2 = await session.run(q2, prefix=prefix)
            else:
                res2 = await session.run(
                    "MATCH (d:Dieu) RETURN d.dieu_id AS id, d.tieu_de AS text, d.so AS so"
                )
            for row in [dict(r) async for r in res2]:
                did = row["id"]
                original = row["text"] or ""
                cleaned = clean_text(original)
                # Also backfill so_dieu from ::D{n} when missing.
                so = row.get("so")
                if not so:
                    import re

                    m = re.search(r"::D(\d+)", did or "")
                    so = m.group(1) if m else None
                if cleaned == original and so is None:
                    continue
                if dry_run:
                    print(f"[dry] Dieu {did} so={so}")
                    if cleaned != original:
                        print(f"  OLD: {original[:100]}")
                        print(f"  NEW: {cleaned[:100]}")
                    dieu_updated += 1
                    continue
                await session.run(
                    """
                    MATCH (d:Dieu {dieu_id: $id})
                    SET d.tieu_de = $txt,
                        d.so = coalesce(d.so, $so),
                        d.so_dieu = coalesce(d.so_dieu, d.so, $so)
                    """,
                    id=did,
                    txt=cleaned,
                    so=so,
                )
                dieu_updated += 1
                print(f"Dieu fixed: {did}")

            # Backfill so_khoan from khoan_id when missing.
            if not dry_run:
                import re

                res3 = await session.run(
                    "MATCH (k:Khoan) WHERE k.so IS NULL OR k.so_khoan IS NULL "
                    "RETURN k.khoan_id AS id"
                )
                async for r in res3:
                    kid = r["id"]
                    m = re.search(r"\.K(\d+)", kid or "")
                    if not m:
                        continue
                    num = m.group(1)
                    await session.run(
                        "MATCH (k:Khoan {khoan_id: $id}) "
                        "SET k.so = coalesce(k.so, $n), k.so_khoan = coalesce(k.so_khoan, $n)",
                        id=kid,
                        n=num,
                    )
    finally:
        await driver.close()

    print(f"\nDone. Khoan changed={khoan_updated} Dieu changed={dieu_updated}"
          f"{' (dry-run)' if dry_run else ''}")
    return 0


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser(description="Repair OCR typos in Neo4j legal text.")
    ap.add_argument("--prefix", default=None, help="Only repair IDs starting with this prefix")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return asyncio.run(main_async(args.prefix, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
