"""Safely create the additive Qdrant ``legal_provision`` collection.

The command is dry-run by default. It never deletes or recreates a collection.
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

_KEYWORD_FIELDS = (
    "provision_id",
    "lineage_id",
    "level",
    "logical_vb_id",
    "source_vb_id",
    "visibility",
    "review_status",
    "text_checksum",
)
_DATETIME_FIELDS = ("effective_from", "effective_to")


async def _run(*, apply: bool, yes: bool) -> dict[str, Any]:
    from app.api.deps import get_qdrant_client
    from app.config import get_config
    from app.pipelines.legal.provision_index import LEGAL_PROVISION_COLLECTION

    config = get_config()
    dimension = int(config.embedding_dimension or 1536)
    qdrant = await get_qdrant_client()
    raw = qdrant.client
    collections = {item.name for item in (await raw.get_collections()).collections}
    exists = LEGAL_PROVISION_COLLECTION in collections
    present_indexes: set[str] = set()
    if exists:
        await qdrant.validate_collection(LEGAL_PROVISION_COLLECTION, dimension)
        info = await qdrant.get_collection(LEGAL_PROVISION_COLLECTION)
        schema = info.get("payload_schema") or {}
        if isinstance(schema, dict):
            present_indexes = set(schema)

    required_indexes = set(_KEYWORD_FIELDS) | set(_DATETIME_FIELDS)
    missing_indexes = sorted(required_indexes - present_indexes)
    if not apply:
        return {
            "status": "exists" if exists else "would_create",
            "mutated": False,
            "collection": LEGAL_PROVISION_COLLECTION,
            "vector_size": dimension,
            "missing_payload_indexes": missing_indexes,
        }
    if not yes:
        raise SystemExit("--apply requires --yes; Qdrant was not changed.")

    from qdrant_client.http import models

    created = False
    if not exists:
        await raw.create_collection(
            collection_name=LEGAL_PROVISION_COLLECTION,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
        created = True
    for field in missing_indexes:
        schema_type = (
            models.PayloadSchemaType.DATETIME
            if field in _DATETIME_FIELDS
            else models.PayloadSchemaType.KEYWORD
        )
        await raw.create_payload_index(
            collection_name=LEGAL_PROVISION_COLLECTION,
            field_name=field,
            field_schema=schema_type,
        )
    return {
        "status": "created" if created else "indexes_ensured",
        "mutated": created or bool(missing_indexes),
        "collection": LEGAL_PROVISION_COLLECTION,
        "vector_size": dimension,
        "payload_indexes_created": missing_indexes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Qdrant LegalProvision v2 collection")
    parser.add_argument("--apply", action="store_true", help="Create/ensure additive resources")
    parser.add_argument("--yes", action="store_true", help="Confirm the additive change")
    args = parser.parse_args()
    report = asyncio.run(_run(apply=args.apply, yes=args.yes))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())