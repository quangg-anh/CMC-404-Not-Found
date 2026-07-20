from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.adapters.neo4j_retrieval import Neo4jLegalRetrievalRepository
from app.exceptions import LegalRetrievalUnavailableError


class Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for row in self.rows:
            yield row


class Transaction:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    async def run(self, query: str, **params: Any) -> Result:
        self.calls.append((query, params))
        return Result(
            [
                {
                    "provision_id": "law::D1@2026-01-01#123456789abc",
                    "lineage_id": "law::D1",
                    "raw_score": 0.8,
                }
            ]
        )


class Session:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute_read(self, callback: Any, *args: Any) -> Any:
        return await callback(Transaction(self.calls), *args)


class Driver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def session(self) -> Session:
        return Session(self.calls)


@pytest.mark.anyio
async def test_exact_and_lexical_queries_are_id_only_and_public_filtered() -> None:
    driver = Driver()
    repository = Neo4jLegalRetrievalRepository(driver)

    exact = await repository.exact_search(
        identifiers=["law::D1"],
        document_numbers=[],
        public_only=True,
        limit=10,
    )
    lexical = await repository.lexical_search("tax deadline", public_only=True, limit=20)

    assert exact[0]["lineage_id"] == "law::D1"
    exact_query, exact_params = driver.calls[0]
    lexical_query, lexical_params = driver.calls[1]
    assert "legal_retrieval_v2_exact" in exact_query
    assert "coalesce(p.visibility, 'public') = 'public'" in exact_query
    assert "noi_dung AS text" not in exact_query
    assert exact_params["identifiers"] == ["law::D1"]
    assert "legal_retrieval_v2_lexical" in lexical_query
    assert "db.index.fulltext.queryNodes" in lexical_query
    assert lexical_params["index_name"] == "legal_provision_text_ft"
    assert lexical_params["search_query"] == "tax deadline"


@pytest.mark.anyio
async def test_graph_expansion_is_bounded_and_relation_allowlisted() -> None:
    driver = Driver()
    repository = Neo4jLegalRetrievalRepository(driver)

    await repository.expand_graph(["seed"], public_only=False, limit=30)

    query, params = driver.calls[0]
    assert "legal_retrieval_v2_graph_expand" in query
    assert "SUPERSEDED_BY|CO_KHOAN|CO_DIEM*1..2" in query
    assert "*1..2" in query
    assert params["seed_ids"] == ["seed"]
    assert params["limit"] == 30


@pytest.mark.anyio
async def test_retrieval_repository_fails_with_structured_retryable_error() -> None:
    repository = Neo4jLegalRetrievalRepository(None)

    with pytest.raises(LegalRetrievalUnavailableError, match="not available"):
        await repository.lexical_search("tax", public_only=False, limit=5)


def test_fulltext_index_contract_is_declared_in_schema() -> None:
    schema = (
        Path(__file__).resolve().parents[2]
        / "Data"
        / "schema"
        / "neo4j_indexes.cypher"
    ).read_text(encoding="utf-8")

    assert "CREATE FULLTEXT INDEX legal_provision_text_ft IF NOT EXISTS" in schema
    assert "FOR (p:LegalProvision) ON EACH [p.noi_dung, p.tieu_de]" in schema