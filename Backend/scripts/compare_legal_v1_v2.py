"""Read-only Neo4j/Qdrant identity parity report for LegalProvision v2."""
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


async def _run() -> dict[str, Any]:
    from app.api.deps import get_neo4j_driver, get_qdrant_client
    from app.pipelines.legal.provision_index import (
        LEGAL_PROVISION_COLLECTION,
        load_leaf_provisions_from_neo4j,
    )
    from app.services.legal_shadow_parity import build_shadow_parity_report

    driver = await get_neo4j_driver()
    qdrant = await get_qdrant_client()
    rows = await load_leaf_provisions_from_neo4j(driver)
    neo4j_ids = [str(row["provision_id"]) for row in rows if row.get("provision_id")]
    neo4j_checksums = {
        str(row["provision_id"]): str(row.get("text_checksum") or "")
        for row in rows
        if row.get("provision_id")
    }
    qdrant_checksums: dict[str, str] | None = None
    if hasattr(qdrant, "list_payload_records"):
        records = await qdrant.list_payload_records(
            LEGAL_PROVISION_COLLECTION,
            ["provision_id", "text_checksum"],
        )
        qdrant_ids = [
            str(record["provision_id"])
            for record in records
            if record.get("provision_id")
        ]
        qdrant_checksums = {
            str(record["provision_id"]): str(record.get("text_checksum") or "")
            for record in records
            if record.get("provision_id")
        }
    else:
        qdrant_ids = list(
            await qdrant.list_payload_values(
                LEGAL_PROVISION_COLLECTION,
                "provision_id",
            )
        )
    report = build_shadow_parity_report(
        neo4j_ids,
        qdrant_ids,
        neo4j_checksums=neo4j_checksums if qdrant_checksums is not None else None,
        qdrant_checksums=qdrant_checksums,
    )
    report["mutated"] = False
    report["collection"] = LEGAL_PROVISION_COLLECTION
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Neo4j and Qdrant LegalProvision IDs")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = asyncio.run(_run())
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("exact_match") else 1


if __name__ == "__main__":
    raise SystemExit(main())
