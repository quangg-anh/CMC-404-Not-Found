"""Resumable LegalProvision v2 reindex from Neo4j to Qdrant.

Dry-run is the default. ``--apply --yes`` is required before any vector upsert.
Create the additive collection first with ``bootstrap_qdrant_v2.py``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _read_checkpoint(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get("checkpoint")
    return str(value) if value else None


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    from app.api.deps import get_embedder, get_neo4j_driver, get_qdrant_client
    from app.config import get_config
    from app.pipelines.legal.provision_index import (
        LEGAL_PROVISION_COLLECTION,
        load_leaf_provisions_from_neo4j,
        reindex_legal_provisions_from_neo4j,
    )

    driver = await get_neo4j_driver()
    qdrant = await get_qdrant_client()
    resume_from = args.resume_from or _read_checkpoint(args.checkpoint_file)
    if not args.apply:
        rows = await load_leaf_provisions_from_neo4j(
            driver,
            document_id=args.document,
            resume_from=resume_from,
        )
        rows_by_id = {
            str(row["provision_id"]): row
            for row in rows
            if row.get("provision_id")
            and str(row.get("text") or "").strip()
            and row.get("text_checksum")
            and row.get("effective_from")
        }
        skipped_invalid = len(rows) - len(rows_by_id)
        already_indexed = 0
        checksum_mismatches = 0
        would_index = len(rows_by_id)
        collection_status = "available"
        try:
            if hasattr(qdrant, "list_payload_records"):
                records = await qdrant.list_payload_records(
                    LEGAL_PROVISION_COLLECTION,
                    ["provision_id", "text_checksum"],
                )
                existing_checksums = {
                    str(record["provision_id"]): str(record.get("text_checksum") or "")
                    for record in records
                    if record.get("provision_id")
                }
                already_indexed = sum(
                    1
                    for provision_id, row in rows_by_id.items()
                    if existing_checksums.get(provision_id)
                    == str(row.get("text_checksum") or "")
                )
                checksum_mismatches = sum(
                    1
                    for provision_id, row in rows_by_id.items()
                    if provision_id in existing_checksums
                    and existing_checksums[provision_id]
                    != str(row.get("text_checksum") or "")
                )
                would_index = len(rows_by_id) - already_indexed
            else:
                existing = await qdrant.list_payload_values(
                    LEGAL_PROVISION_COLLECTION,
                    "provision_id",
                )
                already_indexed = len(set(rows_by_id) & existing)
                would_index = len(set(rows_by_id) - existing)
        except Exception as exc:  # noqa: BLE001 - dry-run must remain diagnostic
            collection_status = f"unavailable: {exc}"
        return {
            "status": "dry_run",
            "mutated": False,
            "document_id": args.document,
            "resume_from": resume_from,
            "neo4j_leaf_count": len(rows_by_id),
            "skipped_invalid": skipped_invalid,
            "already_indexed": already_indexed,
            "checksum_mismatches": checksum_mismatches,
            "would_index": would_index,
            "qdrant_collection": collection_status,
        }

    if not args.yes:
        raise SystemExit("--apply requires --yes; no vectors were written.")
    embedder = await get_embedder(get_config())
    if embedder is None:
        raise SystemExit("Embedding service is unavailable; no vectors were written.")
    return await reindex_legal_provisions_from_neo4j(
        driver,
        qdrant,
        embedder,
        document_id=args.document,
        resume_from=resume_from,
        batch_size=args.batch_size,
        skip_existing=not args.no_skip_existing,
        include_debug_preview=args.debug_preview,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex immutable legal provisions")
    parser.add_argument("--document", help="Limit to logical_vb_id/source_vb_id")
    parser.add_argument("--resume-from", help="Resume after this provision_id")
    parser.add_argument("--checkpoint-file", type=Path, help="Read/write JSON checkpoint")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--debug-preview", action="store_true", help="Include 200-char non-canonical preview")
    parser.add_argument("--apply", action="store_true", help="Upsert vectors")
    parser.add_argument("--yes", action="store_true", help="Confirm vector upserts")
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.checkpoint_file and args.apply:
        args.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        args.checkpoint_file.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("status") in {"success", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
