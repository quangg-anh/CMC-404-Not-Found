import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.qa_service import QAService

@pytest.mark.asyncio
async def test_graph_paths_disabled():
    service = QAService()
    status, reason, paths = await service._graph_paths_for_citations([{"khoan_id": "D1.K1"}], enabled=False)
    assert status == "disabled"
    assert paths == []

@pytest.mark.asyncio
async def test_graph_paths_no_citations():
    service = QAService()
    status, reason, paths = await service._graph_paths_for_citations([], enabled=True)
    assert status == "not_requested"
    assert paths == []

@pytest.mark.asyncio
async def test_graph_paths_success():
    driver_mock = MagicMock()
    session_mock = AsyncMock()
    
    class MockResult:
        async def __aiter__(self):
            yield {
                "kid": "D1.K1", "vb_id": "VB1", "so_hieu": "123", "ten_van_ban": "Luật 1",
                "dieu_id": "D1", "so_dieu": "1", "tieu_de_dieu": "Điều 1",
                "khoan_id": "D1.K1", "noi_dung": "Nội dung khoản 1"
            }
    
    session_mock.run.return_value = MockResult()
    driver_mock.session.return_value.__aenter__.return_value = session_mock
    
    service = QAService(neo4j_driver=driver_mock)
    status, reason, paths = await service._graph_paths_for_citations([{"khoan_id": "D1.K1"}], enabled=True)
    
    assert status == "available"
    assert reason is None
    assert len(paths) == 1
    assert paths[0]["khoan_id"] == "D1.K1"
    assert len(paths[0]["nodes"]) == 3
