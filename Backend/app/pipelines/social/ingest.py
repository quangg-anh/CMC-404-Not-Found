from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any
from app.config import BE2Config, get_config
from app.exceptions import ValidationError
from app.schemas import SocialPost


def pseudonymize_author(author_id: str, secret: str | None) -> str:
    if not author_id:
        raise ValidationError("author_id must not be empty")
    if secret:
        return hmac.new(secret.encode(), author_id.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(("be2-dev-pepper:" + author_id).encode()).hexdigest()


def normalize_social_payload(payload: dict[str, Any], config: BE2Config | None = None) -> SocialPost:
    cfg = config or get_config()
    platform = str(payload.get("platform", "")).strip().lower()
    external_id = str(payload.get("external_id", payload.get("id", ""))).strip()
    content = str(payload.get("content", payload.get("noi_dung", ""))).strip()
    if not platform or not external_id or not content:
        raise ValidationError("platform, external_id, and content are required")
    published_at = payload.get("published_at") or payload.get("thoi_gian")
    thoi_gian: datetime | None = None
    if isinstance(published_at, str):
        try:
            thoi_gian = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            thoi_gian = None
    elif published_at is not None:
        thoi_gian = published_at
    if thoi_gian is None:
        thoi_gian = datetime.now(timezone.utc)
    author_raw = payload.get("author_id") or payload.get("author")
    author_hash = pseudonymize_author(str(author_raw), cfg.author_hmac_secret) if author_raw else None
    return SocialPost(platform=platform, external_id=external_id, noi_dung=content, tac_gia_hash=author_hash, url=payload.get("url"), thoi_gian=thoi_gian, source_metadata={k: v for k, v in payload.items() if k not in {"author_id", "author", "content", "noi_dung"}})


class SocialIngestService:
    def __init__(self, repository: Any, config: BE2Config | None = None) -> None:
        self.repository = repository
        self.config = config or get_config()

    async def ingest(self, payload: dict[str, Any]) -> SocialPost:
        post = normalize_social_payload(payload, self.config)
        await self.repository.upsert_post(post)
        return post
