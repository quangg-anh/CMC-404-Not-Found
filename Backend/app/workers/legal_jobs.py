import logging
from typing import Dict, Any

# Giả lập môi trường job queue (Redis + Arq/Celery)
logger = logging.getLogger(__name__)

async def legal_ingest(ctx, payload: Dict[str, Any]):
    """
    Job Worker xử lý Ingest (Trigger sau khi file được upload).
    Sẽ gọi module parser.py và lưu vào Neo4j.
    """
    logger.info(f"Worker 'legal_ingest' đang xử lý payload với checksum: {payload.get('checksum')}")
    # TODO: Gọi LegalParser
    pass

async def legal_parse(ctx, file_id: str):
    """
    Job Worker gọi Parser nếu được tách riêng thành queue độc lập.
    """
    logger.info(f"Worker 'legal_parse' đang chạy cho file: {file_id}")
    pass

async def legal_extract(ctx, khoan_id: str, khoan_text: str):
    """
    Job Worker gọi Extractor (NER).
    """
    logger.info(f"Worker 'legal_extract' đang chạy trích xuất thực thể cho khoản: {khoan_id}")
    # TODO: Gọi LegalExtractor.extract_entities_from_khoan(khoan_id, khoan_text)
    pass

async def legal_diff(ctx, old_vb_id: str, new_vb_id: str):
    """
    Job Worker gọi VersionDiff. 
    Thường được trigger thủ công bởi Admin qua `/admin/legal/diff`.
    """
    logger.info(f"Worker 'legal_diff' đang so sánh 2 văn bản: {old_vb_id} và {new_vb_id}")
    # TODO: Gọi VersionDiff
    pass
