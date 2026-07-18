import pytest
from unittest.mock import AsyncMock
from app.services.diff_facade import LegalDiffFacade
from app.exceptions import QueueUnavailableError

@pytest.mark.asyncio
async def test_enqueue_arq_success():
    facade = LegalDiffFacade()
    pool_mock = AsyncMock()
    pool_mock.enqueue_job.return_value = True
    facade._redis_pool = pool_mock

    result = await facade._enqueue_arq("legal_ingest", "job1", {})
    assert result is True

@pytest.mark.asyncio
async def test_enqueue_arq_already_exists():
    facade = LegalDiffFacade()
    pool_mock = AsyncMock()
    pool_mock.enqueue_job.return_value = None  # None indicates job already exists
    facade._redis_pool = pool_mock

    result = await facade._enqueue_arq("legal_ingest", "job1", {})
    assert result is True

@pytest.mark.asyncio
async def test_enqueue_arq_fails():
    facade = LegalDiffFacade()
    pool_mock = AsyncMock()
    pool_mock.enqueue_job.side_effect = Exception("Redis connection refused")
    facade._redis_pool = pool_mock

    with pytest.raises(QueueUnavailableError) as exc_info:
        await facade._enqueue_arq("legal_ingest", "job1", {})

    assert "Hệ thống hàng đợi đang bảo trì" in str(exc_info.value)
