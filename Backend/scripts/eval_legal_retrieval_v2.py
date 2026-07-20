"""Read-only ablation runner for LegalProvision v2 retrieval."""
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

from app.domain.legal_retrieval import RetrievalProfile
from app.services.legal_retrieval_eval import (
    DEFAULT_ABLATION_PROFILES,
    RetrievalGoldCase,
    run_retrieval_ablation,
)


def load_gold_cases(path: Path) -> list[RetrievalGoldCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("gold file must contain a non-empty list or {'cases': [...]}")
    return [RetrievalGoldCase.model_validate(row) for row in rows]


def parse_profiles(value: str | None) -> list[RetrievalProfile]:
    if not value:
        return list(DEFAULT_ABLATION_PROFILES)
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        raise ValueError("profiles must not be empty")
    return list(dict.fromkeys(RetrievalProfile(name) for name in names))


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from app.adapters.neo4j_retrieval import Neo4jLegalRetrievalRepository
    from app.adapters.neo4j_temporal import Neo4jTemporalRepository
    from app.api.deps import get_embedder, get_neo4j_driver, get_qdrant_client
    from app.config import get_config
    from app.services.legal_retrieval_service import LegalRetrievalService
    from app.services.temporal_law_service import TemporalLawService

    cases = load_gold_cases(args.gold)
    profiles = parse_profiles(args.profiles)
    dependency_warnings: list[str] = []
    driver = await get_neo4j_driver()
    if driver is None:
        raise RuntimeError("Neo4j driver is unavailable")

    qdrant = None
    embedder = None
    if any(profile != RetrievalProfile.LEXICAL for profile in profiles):
        try:
            qdrant = await get_qdrant_client()
        except Exception as exc:
            dependency_warnings.append(f"qdrant_unavailable: {type(exc).__name__}: {exc}")
        try:
            embedder = await get_embedder(get_config())
        except Exception as exc:
            dependency_warnings.append(f"embedder_unavailable: {type(exc).__name__}: {exc}")

    temporal = TemporalLawService(Neo4jTemporalRepository(driver))
    service = LegalRetrievalService(
        Neo4jLegalRetrievalRepository(driver),
        temporal,
        qdrant=qdrant,
        embedder=embedder,
    )
    try:
        report = await run_retrieval_ablation(
            service,
            cases,
            profiles=profiles,
            k=args.k,
        )
        output = report.model_dump(mode="json")
        output["dependency_warnings"] = dependency_warnings
        output["gold_path"] = str(args.gold.resolve())
        return output
    finally:
        if embedder is not None and hasattr(embedder, "aclose"):
            await embedder.aclose()
        if hasattr(driver, "close"):
            await driver.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run read-only lexical/vector/hybrid/graph/reranker ablations. "
            "No metrics are emitted without a supplied gold set."
        )
    )
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--profiles",
        help=(
            "Comma-separated profiles. Defaults to lexical,vector,hybrid,"
            "hybrid_graph,hybrid_graph_rerank."
        ),
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive")

    payload = asyncio.run(run(args))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
