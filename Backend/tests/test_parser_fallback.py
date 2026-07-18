import pytest
from unittest.mock import AsyncMock, MagicMock
from app.pipelines.legal.parser import LegalParser, ParsedLegalDocument
from app.exceptions import ParserFallbackError, ParserOutputValidationError, ParserFallbackUnavailableError

@pytest.mark.asyncio
async def test_fallback_llm_parse_success():
    llm_router = AsyncMock()
    llm_router.complete.return_value = {
        "dieu_list": [
            {
                "so": "1",
                "tieu_de": "Phạm vi điều chỉnh",
                "noi_dung": "Luật này quy định về...",
                "khoan_list": []
            }
        ]
    }
    parser = LegalParser()
    tree, needs_review = await parser.fallback_llm_parse("Điều 1. Phạm vi điều chỉnh\nLuật này quy định về...", llm_router=llm_router)
    
    assert not needs_review
    assert len(tree) == 1
    assert tree[0]["loai"] == "Dieu"
    assert tree[0]["so"] == "1"

@pytest.mark.asyncio
async def test_fallback_llm_parse_empty_result():
    llm_router = AsyncMock()
    llm_router.complete.return_value = {"dieu_list": []}
    parser = LegalParser()
    
    with pytest.raises(ParserOutputValidationError):
        await parser.fallback_llm_parse("Some text", llm_router=llm_router)

@pytest.mark.asyncio
async def test_fallback_llm_parse_disabled(monkeypatch):
    monkeypatch.setenv("PARSER_LLM_FALLBACK_ENABLED", "0")
    llm_router = AsyncMock()
    parser = LegalParser()
    
    with pytest.raises(ParserFallbackUnavailableError):
        await parser.fallback_llm_parse("Some text", llm_router=llm_router)
