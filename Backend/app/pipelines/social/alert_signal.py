from __future__ import annotations

from collections import Counter
from typing import Any
from app.config import BE2Config, get_config
from app.schemas import NliLabel


class AlertSignalService:
    def __init__(self, repository: Any, config: BE2Config | None = None) -> None:
        self.repository = repository
        self.config = config or get_config()

    async def maybe_create_alert(self, *, signals: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any] | None:
        eligible = [
            s for s in signals
            if self._has_provenance(s)
            and s.get("label") in {NliLabel.MAU_THUAN, NliLabel.MAU_THUAN.value}
            and float(s.get("score", 0.0)) >= self.config.nli_confidence_threshold
        ]
        unique: dict[str, dict[str, Any]] = {}
        for signal in eligible:
            identity = str(signal.get("ykien_id") or "|".join((
                str(signal.get("bai_dang_id")),
                str(signal.get("khoan_id")),
                str(signal.get("claim_text")),
            )))
            unique.setdefault(identity, signal)
        eligible = list(unique.values())
        if len(eligible) < self.config.alert_volume_threshold or dry_run:
            return None
        keys = [(s.get("chu_de"), s.get("khoan_id")) for s in eligible]
        (chu_de, khoan_id), volume = Counter(keys).most_common(1)[0]
        if volume < self.config.alert_volume_threshold:
            return None
        dedupe_key = f"{chu_de}:{khoan_id}"
        if await self.repository.find_recent_alert(dedupe_key, self.config.alert_cooldown_s):
            return None
        grouped_signals = [s for s in eligible if (s.get("chu_de"), s.get("khoan_id")) == (chu_de, khoan_id)]
        alert = {"chu_de": chu_de, "khoan_ids": [khoan_id], "severity": self._severity(volume), "volume": volume, "status": "open", "dedupe_key": dedupe_key, "signals": grouped_signals, "provenance_status": "complete", "note": "Tín hiệu cần xem xét, không phải kết luận nội dung giả."}
        alert_id = await self.repository.save_alert(alert)
        return {"alert_id": alert_id, **alert}

    @staticmethod
    def _has_provenance(signal: dict[str, Any]) -> bool:
        required = ("bai_dang_id", "ykien_id", "claim_text", "evidence_span", "post_url", "khoan_id")
        if not all(isinstance(signal.get(key), str) and signal[key].strip() for key in required):
            return False
        post_content = signal.get("post_content")
        return isinstance(post_content, str) and signal["evidence_span"] in post_content

    def _severity(self, volume: int) -> str:
        if volume >= self.config.alert_volume_threshold * 3:
            return "high"
        if volume >= self.config.alert_volume_threshold * 2:
            return "medium"
        return "low"
