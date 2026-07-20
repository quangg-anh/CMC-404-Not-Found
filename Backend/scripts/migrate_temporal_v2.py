"""Read-only inventory for the additive LegalProvision v2 migration.

This command never writes Neo4j. It identifies documents that can be reviewed for
an additive upgrade and documents that need source recovery/re-ingestion first.
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


def _json_default(value: Any) -> str:
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(value)


async def _run(document_id: str | None) -> dict[str, Any]:
    from app.api.deps import get_neo4j_driver
    from app.services.legal_migration_inventory import inspect_temporal_v2_migration

    driver = await get_neo4j_driver()
    if driver is None:
        raise SystemExit("Neo4j is unavailable; inventory was not run.")
    return await inspect_temporal_v2_migration(driver, document_id=document_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run LegalProvision v2 migration inventory")
    parser.add_argument("--dry-run", action="store_true", help="Explicit no-op; inventory is always read-only")
    parser.add_argument("--document", help="Limit inventory to vb_id or so_hieu")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    report = asyncio.run(_run(args.document))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
