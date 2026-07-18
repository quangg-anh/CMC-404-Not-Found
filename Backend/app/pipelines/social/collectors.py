from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Iterable
from urllib.parse import quote
import xml.etree.ElementTree as ET

import httpx

from app.config import BE2Config, get_config
from app.exceptions import ExternalServiceError

FACEBOOK_GRAPH_BASE = "https://graph.facebook.com"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
YOUTUBE_TOPIC_EXPANSIONS = {
    "thuế": ["thuế doanh nghiệp", "thuế thu nhập cá nhân", "hóa đơn điện tử", "hộ kinh doanh thuế"],
    "tài chính": ["bảo hiểm bắt buộc", "lãi suất", "chứng khoán", "vay tiêu dùng", "bộ tài chính"],
    "kinh doanh thương mại": ["sàn thương mại điện tử", "hợp đồng mua bán", "bảo vệ người tiêu dùng", "đăng ký kinh doanh"],
}
VIETNAMESE_MARKERS = re.compile(r"[ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.IGNORECASE)
VIETNAMESE_WORDS = {"thuế", "doanh", "nghiệp", "tài", "chính", "kinh", "thương", "mại", "pháp", "luật", "bảo", "hiểm", "người", "dùng"}
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)


def _since_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _stable_external_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _contains_topic(text: str, topic: str) -> bool:
    return topic.casefold() in text.casefold()


def _expanded_youtube_queries(topics: Iterable[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for topic in topics:
        queries = [topic, *YOUTUBE_TOPIC_EXPANSIONS.get(topic.casefold(), [])]
        for query in queries:
            key = (topic, query.casefold())
            if key in seen:
                continue
            seen.add(key)
            pairs.append((topic, query))
    return pairs

def _youtube_search_orders(configured: str) -> list[str]:
    orders = ["date", "viewCount", configured]
    return list(dict.fromkeys(orders))


def _looks_vietnamese(text: str) -> bool:
    lowered = text.casefold()
    return bool(VIETNAMESE_MARKERS.search(text)) or any(word in lowered for word in VIETNAMESE_WORDS)


def _useful_comment(text: str, min_length: int) -> bool:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < min_length:
        return False
    if re.fullmatch(r"[\W_]+", cleaned, flags=re.UNICODE):
        return False
    return True


class FacebookGraphCollector:
    def __init__(self, config: BE2Config | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config or get_config()
        self._http = http_client

    async def collect(self, topics: list[str], *, limit_per_topic: int | None = None) -> list[dict[str, Any]]:
        if not self.config.facebook_access_token or not self.config.facebook_page_ids:
            return []
        limit = limit_per_topic or self.config.social_monitor_limit_per_topic
        client = self._http or httpx.AsyncClient(timeout=20.0)
        close = self._http is None
        try:
            posts: list[dict[str, Any]] = []
            for page_id in self.config.facebook_page_ids:
                url = f"{FACEBOOK_GRAPH_BASE}/{self.config.facebook_api_version}/{quote(page_id)}/posts"
                params = {
                    "access_token": self.config.facebook_access_token,
                    "fields": "id,message,permalink_url,created_time,from",
                    "since": _since_iso(self.config.social_monitor_lookback_hours),
                    "limit": min(100, max(limit * max(1, len(topics)), limit)),
                }
                response = await client.get(url, params=params)
                response.raise_for_status()
                for item in response.json().get("data", []):
                    message = str(item.get("message") or "").strip()
                    if not message:
                        continue
                    matched = [topic for topic in topics if _contains_topic(message, topic)] or topics[:1]
                    if not matched:
                        continue
                    posts.append({
                        "platform": "facebook",
                        "external_id": str(item.get("id")),
                        "content": message,
                        "url": item.get("permalink_url"),
                        "published_at": item.get("created_time"),
                        "author_id": (item.get("from") or {}).get("id"),
                        "source_topic": matched[0],
                    })
            return posts[: limit * max(1, len(topics))]
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise ExternalServiceError("Facebook Graph API collection failed", details={"provider": "facebook"}) from exc
        finally:
            if close:
                await client.aclose()


class YouTubeDataCollector:
    def __init__(self, config: BE2Config | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config or get_config()
        self._http = http_client

    def _api_keys(self) -> list[str]:
        raw_keys = [*self.config.youtube_api_keys]
        if self.config.youtube_api_key:
            raw_keys.append(self.config.youtube_api_key)
        keys: list[str] = []
        for raw in raw_keys:
            for key in str(raw).replace(";", ",").replace("\n", ",").split(","):
                key = key.strip()
                if key and not key.startswith("change_me"):
                    keys.append(key)
        return list(dict.fromkeys(keys))

    async def collect(self, topics: list[str], *, limit_per_topic: int | None = None) -> list[dict[str, Any]]:
        api_keys = self._api_keys()
        if not api_keys:
            return []
        limit = limit_per_topic or self.config.social_monitor_limit_per_topic
        client = self._http or httpx.AsyncClient(timeout=20.0)
        close = self._http is None
        try:
            last_status_code: int | None = None
            for api_key in api_keys:
                try:
                    return await self._collect_with_key(client, topics, limit, api_key)
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if status_code in {403, 429}:
                        last_status_code = status_code
                        continue
                    raise ExternalServiceError(
                        "YouTube Data API collection failed",
                        details={"provider": "youtube", "status_code": status_code},
                    ) from None
            raise ExternalServiceError(
                "YouTube Data API collection failed",
                details={"provider": "youtube", "status_code": last_status_code, "attempted_keys": len(api_keys)},
            ) from None
        except (httpx.TimeoutException, httpx.HTTPError):
            raise ExternalServiceError("YouTube Data API collection failed", details={"provider": "youtube"}) from None
        finally:
            if close:
                await client.aclose()

    async def _collect_with_key(self, client: httpx.AsyncClient, topics: list[str], limit: int, api_key: str) -> list[dict[str, Any]]:
            posts: list[dict[str, Any]] = []
            seen_posts: set[str] = set()
            seen_videos: set[str] = set()
            topic_video_counts: dict[str, int] = {topic: 0 for topic in topics}
            topic_comment_counts: dict[str, int] = {topic: 0 for topic in topics}
            channel_ids = self.config.youtube_channel_ids or [None]
            for topic, query in _expanded_youtube_queries(topics):
                if topic_comment_counts.get(topic, 0) >= self.config.youtube_comments_per_topic and topic_video_counts.get(topic, 0) >= limit:
                    continue
                for channel_id in channel_ids:
                    for order in _youtube_search_orders(self.config.youtube_search_order):
                        params: dict[str, Any] = {
                            "key": api_key,
                            "part": "snippet",
                            "q": query,
                            "type": "video",
                            "order": order,
                            "publishedAfter": _since_iso(self.config.social_monitor_lookback_hours),
                            "maxResults": min(50, max(limit, self.config.youtube_search_results_per_topic)),
                        }
                        if self.config.youtube_region_code:
                            params["regionCode"] = self.config.youtube_region_code
                        if self.config.youtube_relevance_language:
                            params["relevanceLanguage"] = self.config.youtube_relevance_language
                        if channel_id:
                            params["channelId"] = channel_id
                        response = await client.get(YOUTUBE_SEARCH_URL, params=params)
                        response.raise_for_status()
                        for item in response.json().get("items", []):
                            if topic_comment_counts.get(topic, 0) >= self.config.youtube_comments_per_topic and topic_video_counts.get(topic, 0) >= limit:
                                break
                            video_id = (item.get("id") or {}).get("videoId")
                            snippet = item.get("snippet") or {}
                            title = str(snippet.get("title") or "").strip()
                            description = str(snippet.get("description") or "").strip()
                            content = "\n".join(part for part in (title, description) if part)
                            if not video_id or not content:
                                continue
                            if video_id in seen_videos:
                                continue
                            seen_videos.add(video_id)
                            if self.config.youtube_filter_vietnamese and not _looks_vietnamese(content):
                                continue
                            comments = await self._collect_comments(client, video_id, topic, api_key) if self.config.youtube_comments_enabled else []
                            if self.config.youtube_skip_videos_without_comments and not comments:
                                continue
                            if comments and not self.config.youtube_comments_as_posts:
                                content = f"{content}\n\nBình luận công khai:\n" + "\n".join(comment["text"] for comment in comments)
                            video_post = {
                                "platform": "youtube",
                                "external_id": video_id,
                                "content": content,
                                "url": f"https://www.youtube.com/watch?v={video_id}",
                                "published_at": snippet.get("publishedAt"),
                                "author_id": snippet.get("channelId"),
                                "source_topic": topic,
                                "source_query": query,
                                "youtube_kind": "video",
                                "youtube_search_order": order,
                                "comments": comments,
                                "comment_count": len(comments),
                            }
                            if video_id not in seen_posts and topic_video_counts.get(topic, 0) < limit:
                                seen_posts.add(video_id)
                                posts.append(video_post)
                                topic_video_counts[topic] = topic_video_counts.get(topic, 0) + 1
                            if self.config.youtube_comments_as_posts:
                                for comment_post in self._comment_posts(video_id, snippet, topic, query, comments):
                                    if topic_comment_counts.get(topic, 0) >= self.config.youtube_comments_per_topic:
                                        break
                                    external_id = str(comment_post["external_id"])
                                    if external_id in seen_posts:
                                        continue
                                    seen_posts.add(external_id)
                                    posts.append(comment_post)
                                    topic_comment_counts[topic] = topic_comment_counts.get(topic, 0) + 1
            return posts

    async def _collect_comments(self, client: httpx.AsyncClient, video_id: str, topic: str, api_key: str) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        seen_text: set[str] = set()
        page_token: str | None = None
        target = self.config.youtube_comments_per_video
        while len(comments) < target:
            params = {
                "key": api_key,
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(100, target - len(comments)),
                "textFormat": "plainText",
                "order": "relevance",
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                response = await client.get(YOUTUBE_COMMENTS_URL, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {400, 403, 404}:
                    return []
                raise
            payload = response.json()
            for item in payload.get("items", []):
                top_comment = (item.get("snippet") or {}).get("topLevelComment") or {}
                snippet = top_comment.get("snippet") or {}
                text = unescape(str(snippet.get("textDisplay") or "")).strip()
                normalized = re.sub(r"\s+", " ", text).casefold()
                if self.config.youtube_skip_comment_urls and URL_PATTERN.search(text):
                    continue
                if not _useful_comment(text, self.config.youtube_min_comment_length):
                    continue
                if self.config.youtube_filter_vietnamese and not _looks_vietnamese(text):
                    continue
                if self.config.youtube_require_topic_in_comments and not _contains_topic(text, topic):
                    continue
                if normalized in seen_text:
                    continue
                seen_text.add(normalized)
                comments.append({
                    "comment_id": top_comment.get("id"),
                    "author_id": snippet.get("authorChannelId", {}).get("value") if isinstance(snippet.get("authorChannelId"), dict) else None,
                    "author_name": snippet.get("authorDisplayName"),
                    "author_profile_url": snippet.get("authorChannelUrl"),
                    "text": text,
                    "published_at": snippet.get("publishedAt"),
                    "updated_at": snippet.get("updatedAt"),
                    "like_count": snippet.get("likeCount", 0),
                })
                if len(comments) >= target:
                    break
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return comments

    def _comment_posts(self, video_id: str, video_snippet: dict[str, Any], topic: str, query: str, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        for comment in comments:
            comment_id = str(comment.get("comment_id") or _stable_external_id("youtube-comment", f"{video_id}:{comment.get('text', '')}"))
            comment_url = f"{video_url}&lc={quote(comment_id)}"
            author_name = comment.get("author_name") or "unknown"
            display_content = (
                f"Người bình luận: {author_name}\n"
                f"Link video: {video_url}\n"
                f"Link bình luận: {comment_url}\n"
                f"Tiêu đề video: {video_snippet.get('title') or ''}\n\n"
                f"{comment['text']}"
            )
            posts.append({
                "platform": "youtube",
                "external_id": f"{video_id}:{comment_id}",
                "content": display_content,
                "url": comment_url,
                "published_at": comment.get("published_at") or video_snippet.get("publishedAt"),
                "author_id": comment.get("author_id") or comment.get("author_name"),
                "source_topic": topic,
                "source_query": query,
                "youtube_kind": "comment",
                "video_id": video_id,
                "video_url": video_url,
                "comment_url": comment_url,
                "comment_id": comment_id,
                "comment_author_name": comment.get("author_name"),
                "comment_author_profile_url": comment.get("author_profile_url"),
                "comment_like_count": comment.get("like_count", 0),
                "comment_published_at": comment.get("published_at"),
                "comment_updated_at": comment.get("updated_at"),
                "video_title": video_snippet.get("title"),
                "video_channel_id": video_snippet.get("channelId"),
                "video_channel_title": video_snippet.get("channelTitle"),
            })
        return posts


class ForumFeedCollector:
    def __init__(self, config: BE2Config | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config or get_config()
        self._http = http_client

    async def collect(self, topics: list[str], *, limit_per_topic: int | None = None) -> list[dict[str, Any]]:
        if not self.config.forum_feed_urls:
            return []
        limit = limit_per_topic or self.config.social_monitor_limit_per_topic
        client = self._http or httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        close = self._http is None
        try:
            posts: list[dict[str, Any]] = []
            for feed_url in self.config.forum_feed_urls:
                response = await client.get(feed_url)
                response.raise_for_status()
                posts.extend(_parse_feed(response.text, feed_url, topics))
            return posts[: limit * max(1, len(topics))]
        except (httpx.TimeoutException, httpx.HTTPError, ET.ParseError) as exc:
            raise ExternalServiceError("Forum feed collection failed", details={"provider": "forum"}) from exc
        finally:
            if close:
                await client.aclose()


def _parse_feed(xml_text: str, feed_url: str, topics: Iterable[str]) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    posts: list[dict[str, Any]] = []
    for item in items:
        title = _node_text(item, "title")
        description = _node_text(item, "description") or _node_text(item, "summary")
        content = "\n".join(part for part in (title, description) if part).strip()
        if not content:
            continue
        matched = [topic for topic in topics if _contains_topic(content, topic)]
        if not matched:
            continue
        link = _node_text(item, "link") or _atom_link(item)
        published = _node_text(item, "pubDate") or _node_text(item, "published") or _node_text(item, "updated")
        posts.append({
            "platform": "forum",
            "external_id": _stable_external_id("forum", link or content),
            "content": content,
            "url": link or feed_url,
            "published_at": _parse_feed_date(published),
            "author_id": _node_text(item, "author") or None,
            "source_topic": matched[0],
        })
    return posts


def _node_text(item: ET.Element, name: str) -> str | None:
    node = item.find(name)
    if node is None:
        node = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
    if node is None or node.text is None:
        return None
    return node.text.strip()


def _atom_link(item: ET.Element) -> str | None:
    node = item.find("{http://www.w3.org/2005/Atom}link")
    return node.attrib.get("href") if node is not None else None


def _parse_feed_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


class SocialDailyMonitor:
    def __init__(self, collectors: list[Any]) -> None:
        self.collectors = collectors

    async def collect(self, topics: list[str], *, limit_per_topic: int | None = None) -> list[dict[str, Any]]:
        if not topics:
            return []
        results = await asyncio.gather(
            *(collector.collect(topics, limit_per_topic=limit_per_topic) for collector in self.collectors),
            return_exceptions=True,
        )
        posts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for result in results:
            if isinstance(result, Exception):
                continue
            for post in result:
                key = (str(post.get("platform")), str(post.get("external_id")))
                if key in seen:
                    continue
                seen.add(key)
                posts.append(post)
        return posts


def build_default_monitor(config: BE2Config | None = None) -> SocialDailyMonitor:
    cfg = config or get_config()
    return SocialDailyMonitor([
        FacebookGraphCollector(cfg),
        YouTubeDataCollector(cfg),
        ForumFeedCollector(cfg),
    ])
