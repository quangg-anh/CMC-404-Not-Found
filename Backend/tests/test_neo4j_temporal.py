from __future__ import annotations

from typing import Any

import pytest

from app.adapters.neo4j_temporal import Neo4jTemporalRepository
from app.exceptions import TemporalLawUnavailableError


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
        return Result([{"provision_id": "fixture"}])


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
async def test_effective_read_uses_managed_transaction_and_half_open_interval() -> None:
    driver = Driver()
    repository = Neo4jTemporalRepository(driver)

    rows = await repository.find_effective(
        as_of="2026-07-01",
        logical_vb_id="01/2026/ND-CP",
        lineage_ids=["01/2026/ND-CP::D5.K2.Pa"],
        public_only=True,
    )

    assert rows == [{"provision_id": "fixture"}]
    query, params = driver.calls[0]
    assert "temporal_v2_find_effective" in query
    assert "date(p.effective_from) <= date($as_of)" in query
    assert "date($as_of) < date(p.effective_to)" in query
    assert "coalesce(p.visibility, 'public') = 'public'" in query
    assert params == {
        "as_of": "2026-07-01",
        "logical_vb_id": "01/2026/ND-CP",
        "lineage_ids": ["01/2026/ND-CP::D5.K2.Pa"],
        "public_only": True,
    }


@pytest.mark.anyio
async def test_repository_deduplicates_exact_ids_and_uses_timeline_marker() -> None:
    driver = Driver()
    repository = Neo4jTemporalRepository(driver)

    await repository.find_by_provision_ids(["a", "a", "b"], public_only=False)
    await repository.timeline("law::D1", public_only=True)

    first_query, first_params = driver.calls[0]
    second_query, second_params = driver.calls[1]
    assert "temporal_v2_find_exact_ids" in first_query
    assert first_params["provision_ids"] == ["a", "b"]
    assert "temporal_v2_timeline" in second_query
    assert second_params == {"identifier": "law::D1", "public_only": True}


@pytest.mark.anyio
async def test_repository_fails_explicitly_without_neo4j_driver() -> None:
    repository = Neo4jTemporalRepository(None)

    with pytest.raises(TemporalLawUnavailableError, match="not available"):
        await repository.find_effective(as_of="2026-07-01", logical_vb_id="law")
