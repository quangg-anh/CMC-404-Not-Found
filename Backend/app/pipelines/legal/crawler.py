import httpx
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class LegalCrawler:
    """
    Module phụ trợ (optional) để tải các văn bản pháp luật từ các URL công khai.
    Thực hiện nhiệm vụ tải file PDF/DOCX/HTML để chuyển cho ingest pipeline.
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        
    async def download_file(self, url: str) -> Optional[bytes]:
        """
        Tải file pháp lý từ một URL cụ thể.
        Trả về bytes của file nếu thành công, None nếu thất bại.
        """
        if not self.is_valid_url(url):
            logger.error(f"URL không hợp lệ: {url}")
            return None
            
        try:
            # Sử dụng httpx để hỗ trợ async/await chuẩn xác theo stack BE3
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as e:
            logger.error(f"Lỗi mạng khi tải file từ {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Lỗi không xác định khi tải {url}: {e}")
            return None

    def is_valid_url(self, url: str) -> bool:
        """Kiểm tra URL có đúng định dạng không."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False
