from __future__ import annotations

import html
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import httpx

NEWS_URL = "https://phapluat.gov.vn/tin-tuc"
NEWS_SOURCE_URLS = (
    NEWS_URL,
    "https://phapluat.gov.vn/moi-nhat-new",
    "https://phapluat.gov.vn/tin-tuc/chinh-sach-moi",
    "https://phapluat.gov.vn/tin-tuc/thoi-su-phap-luat",
    "https://phapluat.gov.vn/tin-tuc/trung-tam-tai-chinh-quoc-te-tai-viet-nam",
    "https://phapluat.gov.vn/tin-tuc/cat-giam-thu-tuc-hanh-chinh",
)
TOPICS = ("thuế", "tài chính", "kinh doanh thương mại")
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "thuế": ("thuế", "hoàn thuế", "khấu trừ", "hóa đơn", "mã số thuế", "hải quan"),
    "tài chính": ("tài chính", "ngân sách", "chứng khoán", "trái phiếu", "vốn", "đầu tư", "tín dụng", "ngân hàng"),
    "kinh doanh thương mại": ("kinh doanh", "thương mại", "doanh nghiệp", "hộ kinh doanh", "điều kiện kinh doanh", "xuất khẩu", "nhập khẩu", "thị trường"),
}
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?\b")
_MD_LINK_RE = re.compile(r"\[([^\]]{10,240})\]\((https://phapluat\.gov\.vn/[^)]+)\)")
_MD_HEADING_LINK_RE = re.compile(
    r"#{3,6}\s+(.{10,500}?)\s+(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)\]\((https://phapluat\.gov\.vn/[^)]+)\)",
    re.S,
)
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    topic: str
    published_text: str | None = None
    body: str | None = None


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = _clean(" ".join(self._text))
            if text:
                self.links.append((self._href, text))
            self._href = None
            self._text = []


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", html.unescape(value or "")).strip()


def _topic_for(text: str) -> str | None:
    lower = text.lower()
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return topic
    return None


def _title_from_anchor(text: str) -> tuple[str, str | None]:
    clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    clean = re.sub(r"#{1,6}", " ", clean)
    clean = _clean(clean)
    match = _DATE_RE.search(clean)
    date_text = match.group(0) if match else None
    if match:
        clean = clean[: match.start()].strip()
    for cue in (" Cục ", " Trước ", " Trong ", " Theo ", " Đến ", " Bộ ", " Chính phủ ", " Thủ tướng "):
        pos = clean.find(cue)
        if pos >= 40:
            clean = clean[:pos].strip()
            break
    words = clean.split()
    # Site often renders title twice in one anchor. Fold exact repeated halves.
    if len(words) >= 6 and len(words) % 2 == 0:
        mid = len(words) // 2
        if words[:mid] == words[mid:]:
            clean = " ".join(words[:mid])
    return clean, date_text

async def _fetch_article_body(client: httpx.AsyncClient, url: str, *, max_chars: int = 1800) -> str | None:
    try:
        resp = await client.get(_reader_url(url), headers={"User-Agent": "LexSocialAI/1.0"})
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    text = resp.text
    marker = "Markdown Content:"
    if marker in text:
        text = text.split(marker, 1)[1]
    lines: list[str] = []
    for raw in text.splitlines():
        line = _clean(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw).strip("#>*- "))
        if not line or line.startswith(("Title:", "URL Source:")) or line.lower().startswith(("image:", "view original")):
            continue
        if line in {"Markdown Content:", "Tin liên quan", "Có thể bạn quan tâm"}:
            continue
        lines.append(line)
        if sum(len(item) for item in lines) >= max_chars:
            break
    body = "\n\n".join(lines).strip()
    if len(body) > max_chars:
        body = body[:max_chars].rsplit(" ", 1)[0].strip() + "..."
    return body or None


class PhapLuatNewsService:
    """Fetch phapluat.gov.vn legal news and create draft briefs for selected topics."""

    def __init__(self, pool: Any | None = None, base_url: str = NEWS_URL) -> None:
        self.pool = pool
        self.base_url = base_url

    async def fetch_items(self, limit_per_topic: int = 5) -> list[NewsItem]:
        source_urls = tuple(dict.fromkeys((self.base_url, *NEWS_SOURCE_URLS)))
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            responses = []
            for source_url in source_urls:
                resp = await client.get(_reader_url(source_url), headers={"User-Agent": "LexSocialAI/1.0"})
                resp.raise_for_status()
                responses.append((source_url, resp.text))

        seen: set[str] = set()
        counts = {topic: 0 for topic in TOPICS}
        items: list[NewsItem] = []
        for source_url, body in responses:
            parser = _LinkCollector()
            parser.feed(body)
            links = [
                *parser.links,
                *[(url, text) for text, url in _MD_LINK_RE.findall(body)],
                *[(url, f"{text} {date_text}") for text, date_text, url in _MD_HEADING_LINK_RE.findall(body)],
            ]
            for href, anchor_text in links:
                url = urljoin(source_url, href)
                if not _is_article_url(url):
                    continue
                title, published_text = _title_from_anchor(anchor_text)
                if len(title) < 20:
                    continue
                topic = _topic_for(f"{title} {url}")
                if not topic or counts[topic] >= limit_per_topic or url in seen:
                    continue
                seen.add(url)
                counts[topic] += 1
                body_text = await _fetch_article_body(client, url)
                items.append(NewsItem(title=title, url=url, topic=topic, published_text=published_text, body=body_text))
                if all(count >= limit_per_topic for count in counts.values()):
                    break
            if all(count >= limit_per_topic for count in counts.values()):
                break
        return items

    async def sync_briefs(self, *, user_id: str | None = None, limit_per_topic: int = 5) -> dict[str, Any]:
        items = await self.fetch_items(limit_per_topic=limit_per_topic)
        created: list[dict[str, Any]] = []
        skipped = 0
        if not self.pool or not hasattr(self.pool, "acquire"):
            return {"source": self.base_url, "created": created, "skipped": len(items), "items": [item.__dict__ for item in items]}

        async with self.pool.acquire() as conn:
            for item in items:
                exists = await conn.fetchval(
                    "SELECT id FROM briefs WHERE citations @> $1::jsonb LIMIT 1",
                    json.dumps([{"source_url": item.url}], ensure_ascii=False),
                )
                if exists:
                    skipped += 1
                    continue
                brief_id = str(uuid.uuid4())
                citations = [
                    {
                        "source": "phapluat.gov.vn",
                        "source_url": item.url,
                        "topic": item.topic,
                        "published_text": item.published_text,
                        "quote": item.title,
                        "summary": item.body,
                    }
                ]
                title = f"[{item.topic}] {item.title}"
                await conn.execute(
                    """
                    INSERT INTO briefs (id, tieu_de, media_type, status, citations, created_by)
                    VALUES ($1::uuid, $2, 'text', 'draft', $3::jsonb, $4::uuid)
                    """,
                    brief_id,
                    title,
                    json.dumps(citations, ensure_ascii=False),
                    user_id if _is_uuid(user_id) else None,
                )
                created.append({"id": brief_id, "tieu_de": title, "citations": citations, "status": "draft"})
        return {"source": self.base_url, "created": created, "created_count": len(created), "skipped": skipped, "items_count": len(items)}


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _is_article_url(url: str) -> bool:
    if not url.startswith("https://phapluat.gov.vn/") or "/tin-tuc/" not in url:
        return False
    path = url.split("https://phapluat.gov.vn/", 1)[1].split("?", 1)[0].strip("/")
    return len(path.split("/")) >= 3


def _reader_url(url: str) -> str:
    return f"https://r.jina.ai/http://{url}"
